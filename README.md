# SolArk Grid Charge for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/andrewjfreyer/solark-grid-charge.svg)](https://github.com/andrewjfreyer/solark-grid-charge/releases)

A Home Assistant custom integration that exposes a single control for Sol-Ark inverter
systems via the SolArk Cloud API: **whether the inverter may charge the battery from the
grid**.

This integration is deliberately narrow. It provides one switch and no sensors.

It uses its own domain (`solark_grid_charge`) and its own directory, so it installs and
runs alongside the upstream monitoring integration without conflicting with it.

## 🎛️ What You Get

| Entity ID | Description |
|-----------|-------------|
| `switch.solark_grid_charge` | Whether the inverter may charge the battery from the grid |

`switch.solark_grid_charge` mirrors the **Grid Charge** toggle on the Sol-Ark portal's
*Battery Setting* page (settings field `sdChargeOn`). Turning it off stops the inverter
from pulling grid power to charge the battery. Solar and generator charging are
unaffected, as are Gen Charge and the per-timeslot Time-of-Use settings.

The switch exposes the related thresholds as attributes for use in templates and
automations:

| Attribute | Portal field | Setting |
|-----------|--------------|---------|
| `grid_start_soc` | `sdStartCap` | Grid Start % |
| `grid_start_voltage` | `sdStartVolt` | Grid Start V |
| `grid_charge_current` | `sdBatteryCurrent` | Grid Start A |

## 📋 Requirements

- Home Assistant 2023.5.0 or newer
- Sol-Ark inverter (12K, 15K, 8K, 5K models)
- Active Sol-Ark Cloud account
- Your Plant ID from the Sol-Ark portal

## 🚀 Installation

### Via HACS (Recommended)

1. Open **HACS** → **Integrations**
2. Click **⋮** → **Custom repositories**
3. Add: `https://github.com/andrewjfreyer/solark-grid-charge`
4. Category: **Integration**
5. Find "SolArk Grid Charge" and click **Download**
6. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Copy `custom_components/solark_grid_charge` to your `/config/custom_components/` directory
3. Restart Home Assistant

## ⚙️ Configuration

### 1. Get Your Plant ID

1. Log into [solarkcloud.com](https://www.solarkcloud.com)
2. Navigate to your system
3. Check the URL: `https://www.solarkcloud.com/plants/overview/12345/...`
4. Your Plant ID is `12345`

### 2. Add Integration

1. **Settings** → **Devices & Services** → **+ ADD INTEGRATION**
2. Search "SolArk Grid Charge"
3. Enter:
   - **Username**: Your Sol-Ark email
   - **Password**: Your Sol-Ark password
   - **Plant ID**: From step 1
   - **Auto-discover API URL**: enabled by default (reads the live API host from the portal)
   - **Portal base URL** / **API URL**: optional overrides (defaults: `https://www.solarkcloud.com` and `https://p2.api.solarkcloud.com`)
   - **Settings poll interval**: 60 (seconds)
4. Click **SUBMIT**

After install you can change discovery, URLs, and the poll interval under **Configure**
on the integration.

### 3. Verify

- Go to **Developer Tools** → **States**
- Search `solark`
- You should see `switch.solark_grid_charge` reflecting the current portal setting

## 🤖 Automation Examples

### Only charge from grid on cheap overnight rates

```yaml
automation:
  - alias: "Grid charge during off-peak"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.solark_grid_charge

  - alias: "Stop grid charge at peak"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.solark_grid_charge
```

### Grid charge only when a price sensor is cheap

```yaml
automation:
  - alias: "Grid charge follows energy price"
    trigger:
      - platform: state
        entity_id: sensor.electricity_price
    action:
      - service: >
          {% if states('sensor.electricity_price') | float(99) < 0.10 %}
            switch.turn_on
          {% else %}
            switch.turn_off
          {% endif %}
        target:
          entity_id: switch.solark_grid_charge
```

## 🔧 Troubleshooting

### Integration won't connect

- Confirm the same credentials work at [solarkcloud.com](https://www.solarkcloud.com)
- Confirm the Plant ID matches the number in the portal URL
- Leave **Auto-discover API URL** enabled so host changes are picked up automatically

### Switch shows "unavailable"

- The inverter did not report `sdChargeOn` in its settings payload. Three-phase models
  use a different settings family and are not currently supported.
- Check **Settings** → **System** → **Logs** for API errors (credentials are redacted)
- Download diagnostics from the integration page to see the full settings payload

### Switch flips back after toggling

The cloud API confirms only that a command was *queued*; the inverter applies it over
the dongle a few seconds later (3–15s measured on a 12K). The switch holds your
requested state for 30s to cover this. If it still reverts, the inverter rejected the
command — check the logs for a warning naming the reported value.

### Enable debug logging

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.solark_grid_charge: debug
```

## 🏗️ Technical Details

### Architecture

- **Auth**: OAuth password grant against the discovered API host, with a legacy
  `/rest/account/login` fallback. Tokens are refreshed automatically and redacted from
  all logs.
- **API host discovery**: reads `VUE_APP_BASE_API` from the portal frontend so Sol-Ark
  host migrations do not break the integration.
- **Settings read**: `GET /api/v1/common/setting/{sn}/read` — the same endpoint that
  backs every tab of the portal's settings UI (~338 fields on a 12K).
- **Settings write**: `POST /api/v1/common/setting/{sn}/set` with a sparse body
  (`{sn, sdChargeOn}`). The portal posts sparse bodies for its own toggles, and the
  backend merges by key, so neighbouring settings are left untouched.
- **Polling**: one coordinator, default 60s, 30s minimum.

### Why only one control?

The settings endpoint exposes hundreds of writable fields, including grid protection
limits and battery voltage thresholds where a bad value can damage hardware or violate
interconnection rules. Grid Charge is a safe, reversible, genuinely useful toggle. Other
fields are intentionally not exposed.

## 🤝 Contributing

Issues and pull requests are welcome at
[GitHub Issues](https://github.com/andrewjfreyer/solark-grid-charge/issues).

## 📞 Support

- **Bugs**: [GitHub Issues](https://github.com/andrewjfreyer/solark-grid-charge/issues)
- **Logs**: **Settings** → **System** → **Logs** (credentials are redacted)
- **Community**: [Home Assistant Forums](https://community.home-assistant.io/)

## ⚠️ Disclaimer

This is an unofficial integration, not affiliated with or endorsed by Sol-Ark. It
changes a real setting on real hardware. Use at your own risk.

## 📄 License

MIT — see [LICENSE](LICENSE).

This is a fork. The original work is MIT-licensed, copyright (c) 2024 dev-slax,
by way of [HammondAutomationHub/HomeAssistant_SolArk](https://github.com/HammondAutomationHub/HomeAssistant_SolArk).
The MIT notice is retained as required.
