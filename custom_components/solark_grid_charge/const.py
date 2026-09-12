DOMAIN = "solark_grid_charge"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_PLANT_ID = "plant_id"
CONF_BASE_URL = "base_url"
CONF_API_URL = "api_url"
CONF_AUTO_DISCOVER_API = "auto_discover_api"
CONF_SCAN_INTERVAL = "scan_interval"

# Portal host used for login Origin/Referer and for API discovery.
DEFAULT_BASE_URL = "https://www.solarkcloud.com"
# Last-known-good fallback when discovery is off or fails.
DEFAULT_API_URL = "https://p2.api.solarkcloud.com"
DEFAULT_AUTO_DISCOVER_API = True
# How often the inverter settings are polled. Settings change rarely and the
# read returns ~338 fields, so this is deliberately unhurried.
DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 30  # seconds

# Battery-tab "Grid Charge" switch in the SolArk portal. The read returns an
# int; the portal's own switch posts the string "1" / "0".
GRID_CHARGE_FIELD = "sdChargeOn"

# Work Mode / Time-of-Use table. The inverter has six time slots; each has a
# start time, a retained battery SOC, and its own grid-charge flag.
TIME_SLOT_COUNT = 6
SLOT_SOC_FIELD = "cap{n}"            # retained battery capacity, 0-100 %
SLOT_START_FIELD = "sellTime{n}"     # slot start time, "HH:MM"
SLOT_GRID_CHARGE_FIELD = "time{n}on"  # per-slot grid charge flag

# Whether capN applies depends on how the inverter tracks battery level. The
# portal validates capN as 0-100 only when battMode is -1 or 1, and treats
# any other value as voltage mode, where the slot uses sellTimeNVolt instead.
BATT_MODE_FIELD = "battMode"
SOC_MODE_VALUES = (-1, 1, "-1", "1")

# How long to trust our own optimistic state after issuing a command. The API
# only acknowledges that a command was queued — the inverter applies it over
# the dongle a few seconds later, so a read before then still shows the old
# value and would otherwise snap the switch back. Measured propagation on a
# 12K was 3-15s, so 30s leaves comfortable headroom.
COMMAND_SETTLE_SECONDS = 30

# Older hosts that Sol-Ark retired / redirected away from.
OBSOLETE_BASE_URLS = {
    "https://www.mysolark.com": DEFAULT_BASE_URL,
    "https://mysolark.com": DEFAULT_BASE_URL,
}
OBSOLETE_API_URLS = {
    "https://ecsprod-api-new.solarkcloud.com": DEFAULT_API_URL,
    "https://ecsprod-api.solarkcloud.com": DEFAULT_API_URL,
}

PLATFORMS = ["switch", "number"]


def normalize_solark_urls(base_url: str, api_url: str) -> tuple[str, str]:
    """Rewrite retired SolArk hosts to the current defaults."""
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    api = (api_url or DEFAULT_API_URL).rstrip("/")
    base = OBSOLETE_BASE_URLS.get(base, base)
    api = OBSOLETE_API_URLS.get(api, api)
    return base, api
