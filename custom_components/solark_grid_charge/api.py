"""API client for Sol-Ark Cloud (SolArk 12K, using energy/flow SOC)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import re
from typing import Any, Dict, Optional

import aiohttp

from .const import GRID_CHARGE_FIELD

_LOGGER = logging.getLogger(__name__)

_REDACTED = "***REDACTED***"
_SENSITIVE_KEYS = {
    "password",
    "username",
    "access_token",
    "refresh_token",
    "token",
    "authorization",
    "client_secret",
}
_SECRET_STRING_PATTERNS = (
    re.compile(r'(?i)("password"\s*:\s*")([^"]*)(")'),
    re.compile(r'(?i)("username"\s*:\s*")([^"]*)(")'),
    re.compile(r'(?i)("access_token"\s*:\s*")([^"]*)(")'),
    re.compile(r'(?i)("refresh_token"\s*:\s*")([^"]*)(")'),
    re.compile(r'(?i)("token"\s*:\s*")([^"]*)(")'),
    re.compile(r"(?i)(Bearer\s+)\S+"),
)


def _redact_secrets(value: Any) -> Any:
    """Recursively redact credentials/tokens for safe logging."""
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in _SENSITIVE_KEYS:
                redacted[key] = _REDACTED
            else:
                redacted[key] = _redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _redact_secret_text(value)
    return value


def _redact_secret_text(text: str) -> str:
    """Redact credential/token patterns from free-form log text."""
    if not text:
        return text
    sanitized = text
    for pattern in _SECRET_STRING_PATTERNS:
        if pattern.groups == 3:
            sanitized = pattern.sub(rf"\1{_REDACTED}\3", sanitized)
        else:
            sanitized = pattern.sub(rf"\1{_REDACTED}", sanitized)
    return sanitized


class SolArkCloudAPIError(Exception):
    """Exception for Sol-Ark Cloud API errors."""

class SolArkCloudAPI:
    """Sol-Ark Cloud API client."""

    def __init__(
        self,
        username: str,
        password: str,
        plant_id: str,
        base_url: str,
        api_url: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self.username = username
        self.password = password
        self.plant_id = plant_id

        self.base_url = base_url.rstrip("/")
        self.api_url = api_url.rstrip("/")

        self._session = session

        self._token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

        # Cached inverter serial. Settings reads/writes are addressed per-SN,
        # so resolve it once instead of on every poll.
        self._inverter_sn: Optional[str] = None

        _LOGGER.debug(
            "SolArkCloudAPI initialized for plant_id=%s, base_url=%s, api_url=%s",
            self.plant_id,
            self.base_url,
            self.api_url,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _get_headers(self, strict: bool = True) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if strict:
            headers.update(
                {
                    "Origin": self.base_url,
                    "Referer": f"{self.base_url}/",
                }
            )
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _ensure_token(self) -> None:
        if self._token and self._token_expiry and datetime.utcnow() < self._token_expiry:
            return
        _LOGGER.debug("Token missing or expired, logging in again")
        await self.login()

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        auth_required: bool = True,
    ) -> Dict[str, Any]:
        if auth_required:
            await self._ensure_token()

        url = f"{self.api_url}{endpoint}"
        headers = self._get_headers(strict=True)

        json_body = None
        params = None
        if method.upper() in ("GET", "DELETE"):
            params = data
        else:
            json_body = data

        _LOGGER.debug(
            "Requesting %s %s with params=%s json=%s",
            method,
            url,
            _redact_secrets(params),
            _redact_secrets(json_body),
        )

        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                text = await resp.text()
                _LOGGER.debug(
                    "Response %s %s -> HTTP %s, body: %s",
                    method,
                    url,
                    resp.status,
                    _redact_secret_text(text[:1000]),
                )
                try:
                    resp.raise_for_status()
                except aiohttp.ClientResponseError as e:
                    raise SolArkCloudAPIError(
                        f"HTTP {resp.status} for {endpoint}: "
                        f"{_redact_secret_text(text[:500])}"
                    ) from e

                try:
                    result = await resp.json()
                except Exception as e:  # noqa: BLE001
                    raise SolArkCloudAPIError(
                        f"Invalid JSON response from {endpoint}: "
                        f"{_redact_secret_text(text[:200])}"
                    ) from e
        except asyncio.TimeoutError as e:  # noqa: BLE001
            raise SolArkCloudAPIError(f"Timeout for {endpoint}") from e
        except aiohttp.ClientError as e:  # noqa: BLE001
            raise SolArkCloudAPIError(f"Client error for {endpoint}: {e}") from e

        if isinstance(result, dict):
            code = result.get("code")
            if code not in (0, "0", None):
                msg = result.get("msg", "Unknown error")
                raise SolArkCloudAPIError(
                    f"API error for {endpoint}: {msg} (code={code})"
                )

        return result

    # ------------------------------------------------------------------
    # auth
    # ------------------------------------------------------------------

    async def _oauth_login(self) -> None:
        url = f"{self.api_url}/oauth/token"
        headers = self._get_headers(strict=True)
        headers["Content-Type"] = "application/json;charset=UTF-8"

        payload = {
            "username": self.username,
            "password": self.password,
            "grant_type": "password",
            "client_id": "csp-web",
        }

        # Never log username/password — only the endpoint and redacted shape.
        _LOGGER.debug(
            "Attempting OAuth login at %s payload_keys=%s",
            url,
            sorted(payload.keys()),
        )

        try:
            async with self._session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                text = await resp.text()
                _LOGGER.debug(
                    "OAuth login response HTTP %s, body: %s",
                    resp.status,
                    _redact_secret_text(text[:1000]),
                )
                try:
                    resp.raise_for_status()
                except aiohttp.ClientResponseError as e:
                    raise SolArkCloudAPIError(
                        f"OAuth login HTTP {resp.status}: "
                        f"{_redact_secret_text(text[:500])}"
                    ) from e

                try:
                    result = await resp.json()
                except Exception as e:  # noqa: BLE001
                    raise SolArkCloudAPIError(
                        f"OAuth login invalid JSON: "
                        f"{_redact_secret_text(text[:200])}"
                    ) from e
        except asyncio.TimeoutError as e:  # noqa: BLE001
            raise SolArkCloudAPIError("OAuth login timeout") from e
        except aiohttp.ClientError as e:  # noqa: BLE001
            raise SolArkCloudAPIError(f"OAuth login client error: {e}") from e

        if not isinstance(result, dict):
            raise SolArkCloudAPIError("OAuth login response not JSON object")

        code = result.get("code")
        if code not in (0, "0"):
            raise SolArkCloudAPIError(
                f"OAuth login failed: {result.get('msg', 'Unknown error')} (code={code})"
            )

        data = result.get("data") or {}
        token = data.get("access_token") or data.get("token")
        if not token:
            raise SolArkCloudAPIError("OAuth login succeeded but no access_token")

        self._token = token
        self._refresh_token = data.get("refresh_token")
        expires_in = int(data.get("expires_in", 3600))
        self._token_expiry = datetime.utcnow() + timedelta(seconds=expires_in - 60)

        _LOGGER.debug(
            "OAuth login successful, token expires in %s seconds (at %s)",
            expires_in,
            self._token_expiry,
        )

    async def _legacy_login(self) -> None:
        # Fallback path on the same API host the portal uses today.
        url = f"{self.api_url}/rest/account/login"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
        }
        payload = {"username": self.username, "password": self.password}

        _LOGGER.debug(
            "Attempting legacy login at %s payload_keys=%s",
            url,
            sorted(payload.keys()),
        )

        try:
            async with self._session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                text = await resp.text()
                _LOGGER.debug(
                    "Legacy login response HTTP %s, body: %s",
                    resp.status,
                    _redact_secret_text(text[:1000]),
                )
                try:
                    resp.raise_for_status()
                except aiohttp.ClientResponseError as e:
                    raise SolArkCloudAPIError(
                        f"Legacy login HTTP {resp.status}: "
                        f"{_redact_secret_text(text[:500])}"
                    ) from e

                try:
                    result = await resp.json()
                except Exception as e:  # noqa: BLE001
                    raise SolArkCloudAPIError(
                        f"Legacy login invalid JSON: "
                        f"{_redact_secret_text(text[:200])}"
                    ) from e
        except asyncio.TimeoutError as e:  # noqa: BLE001
            raise SolArkCloudAPIError("Legacy login timeout") from e
        except aiohttp.ClientError as e:  # noqa: BLE001
            raise SolArkCloudAPIError(f"Legacy login client error: {e}") from e

        if not isinstance(result, dict):
            raise SolArkCloudAPIError("Legacy login response not JSON object")

        token = (
            result.get("token")
            or result.get("access_token")
            or (result.get("data") or {}).get("token")
            or (result.get("data") or {}).get("access_token")
        )
        if not token:
            raise SolArkCloudAPIError("Legacy login succeeded but no token")

        self._token = token
        self._token_expiry = datetime.utcnow() + timedelta(minutes=30)

        _LOGGER.debug("Legacy login successful, temporary token set")

    async def login(self) -> bool:
        errors: list[str] = []

        try:
            await self._oauth_login()
            return True
        except SolArkCloudAPIError as e:
            safe = _redact_secret_text(str(e))
            _LOGGER.debug("OAuth login failed: %s", safe)
            errors.append(f"oauth: {safe}")

        try:
            await self._legacy_login()
            return True
        except SolArkCloudAPIError as e:
            safe = _redact_secret_text(str(e))
            _LOGGER.debug("Legacy login failed: %s", safe)
            errors.append(f"legacy: {safe}")

        raise SolArkCloudAPIError(
            "All login methods failed: " + " | ".join(errors)
        )

    # ------------------------------------------------------------------
    # inverter discovery
    # ------------------------------------------------------------------

    async def _get_inverters(self) -> list[Dict[str, Any]]:
        """Fetch the plant's inverter list."""
        await self._ensure_token()
        _LOGGER.debug("Getting inverter list for plant_id=%s", self.plant_id)

        inv_params = {
            "page": 1,
            "limit": 10,
            "stationId": self.plant_id,
            "status": -1,
            "sn": "",
            "type": -2,
        }
        _LOGGER.debug("Requesting inverter list with params=%s", inv_params)
        inv_resp = await self._request(
            "GET",
            f"/api/v1/plant/{self.plant_id}/inverters",
            inv_params,
        )
        _LOGGER.debug("Raw inverter response: %s", inv_resp)

        inv_data = inv_resp.get("data") or {}
        inverters = (
            inv_data.get("infos")
            or inv_data.get("list")
            or inv_data.get("records")
            or []
        )
        _LOGGER.debug("Parsed inverters list length: %s", len(inverters))
        return inverters

    async def async_get_inverter_sn(self) -> Optional[str]:
        """Return the plant's first inverter SN, resolving and caching it once."""
        if self._inverter_sn:
            return self._inverter_sn

        inverters = await self._get_inverters()
        if not inverters:
            _LOGGER.warning("No inverters found for plant %s", self.plant_id)
            return None

        first = inverters[0]
        sn = first.get("sn") or first.get("deviceSn")
        if not sn:
            _LOGGER.warning("First inverter for plant %s has no SN", self.plant_id)
            return None

        self._inverter_sn = sn
        _LOGGER.debug("Resolved inverter SN=%s for plant %s", sn, self.plant_id)
        return sn

    async def test_connection(self) -> bool:
        """Verify credentials, plant, and that settings are readable."""
        try:
            await self.login()
            await self.async_read_settings()
            return True
        except SolArkCloudAPIError as e:
            _LOGGER.error(
                "SolArk test_connection failed: %s", _redact_secret_text(str(e))
            )
            return False

    # ------------------------------------------------------------------
    # inverter settings (read / write)
    # ------------------------------------------------------------------

    async def async_read_settings(self) -> Dict[str, Any]:
        """Read the inverter's settings object.

        The portal's settings UI (a separate app at settings.solarkcloud.com)
        builds every tab — Battery, Work Mode, Grid, Advanced — from this one
        endpoint. A 12K returns ~338 fields.
        """
        sn = await self.async_get_inverter_sn()
        if not sn:
            raise SolArkCloudAPIError("No inverter SN available for settings read")

        resp = await self._request("GET", f"/api/v1/common/setting/{sn}/read")
        data = resp.get("data") if isinstance(resp, dict) else None
        if not isinstance(data, dict):
            raise SolArkCloudAPIError(
                f"Settings read for SN={sn} returned no data object"
            )

        _LOGGER.debug("Read %s settings fields for SN=%s", len(data), sn)
        return data

    async def async_write_settings(self, **fields: Any) -> None:
        """Write one or more inverter settings.

        The portal posts a sparse body — the SN plus only the fields being
        changed (its factory-reset button sends {"sn": ..., "reset": "1"} and
        its arc-fault toggle sends {"sn": ..., "arcOn": "1"}) — so the backend
        merges by key. We do the same rather than reading and re-posting all
        338 fields, which would risk writing back stale or derived values.

        The API acknowledges that the command was *issued* (code 0,
        "Settings Update sent successfully"); the inverter applies it
        asynchronously via the dongle, so a read immediately after may still
        report the old value. Measured propagation on a 12K was 3-15s.
        """
        if not fields:
            raise SolArkCloudAPIError("async_write_settings called with no fields")

        sn = await self.async_get_inverter_sn()
        if not sn:
            raise SolArkCloudAPIError("No inverter SN available for settings write")

        payload: Dict[str, Any] = {"sn": sn, **fields}
        _LOGGER.debug("Writing settings for SN=%s: %s", sn, fields)

        # _request raises on any non-zero code, which covers the portal's
        # code=1 "Command issued failed".
        await self._request("POST", f"/api/v1/common/setting/{sn}/set", payload)
        _LOGGER.info("Issued settings command for SN=%s: %s", sn, fields)

    @staticmethod
    def parse_grid_charge(settings: Dict[str, Any]) -> Optional[bool]:
        """Read the Grid Charge flag out of a settings payload.

        `sdChargeOn` is the Battery-tab "Grid Charge" switch ("sd" being the
        portal's shorthand for mains/grid). The read returns it as an int,
        while the portal's own switch posts it as the string "1" / "0".
        Returns None when the inverter did not report the field.
        """
        if GRID_CHARGE_FIELD not in settings:
            return None
        value = settings.get(GRID_CHARGE_FIELD)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return int(value) == 1
        if isinstance(value, str):
            return value.strip() in ("1", "true", "True")
        return None

    async def async_set_grid_charge(self, enabled: bool) -> None:
        """Enable or disable charging the battery from the grid."""
        await self.async_write_settings(
            **{GRID_CHARGE_FIELD: "1" if enabled else "0"}
        )
