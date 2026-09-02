# SolArk Grid Charge - Quick Start Guide

## What You'll Get

One entity:

- `switch.solark_grid_charge` — whether the inverter may charge the battery from the grid

This mirrors the **Grid Charge** toggle on the Sol-Ark portal's *Battery Setting* page.
The integration provides no sensors.

## Installation (4 Steps)

### Step 1: Install via HACS

1. Open Home Assistant
2. Go to **HACS** → **Integrations**
3. Click **⋮** → **Custom repositories**
4. Add: `https://github.com/andrewjfreyer/solark-grid-charge`
5. Category: **Integration**
6. Click **Download** on "SolArk Grid Charge"
7. **Restart Home Assistant**

### Step 2: Get Your Plant ID

1. Go to [solarkcloud.com](https://www.solarkcloud.com)
2. Log in with your Sol-Ark account
3. Click on your system/plant
4. Look at the URL: `https://www.solarkcloud.com/plants/overview/12345/...`
5. Your Plant ID is the number: `12345`

### Step 3: Add Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ ADD INTEGRATION**
3. Search: **SolArk Grid Charge**
4. Enter:
   - Username: (your Sol-Ark email)
   - Password: (your Sol-Ark password)
   - Plant ID: (from Step 2)
   - Settings poll interval: `60` (leave default)
5. Click **SUBMIT**

### Step 4: Verify

1. Go to **Developer Tools** → **States**
2. Search for: `solark`
3. You should see `switch.solark_grid_charge` matching what the portal shows
4. Toggle it and confirm the portal's Battery Setting page follows within ~15 seconds

## Troubleshooting

### "Authentication Failed"

- Double-check your username and password
- Try logging into solarkcloud.com with the same credentials
- Make sure your Plant ID is correct

### "Switch doesn't appear"

- Restart Home Assistant completely
- Check **Settings** → **System** → **Logs** for errors (credentials are redacted)

### "Switch shows unavailable"

- Your inverter did not report the `sdChargeOn` field. Three-phase models use a
  different settings family and are not currently supported.
- Download diagnostics from the integration page to inspect the settings payload

### "Switch flips back after I toggle it"

The cloud API only confirms a command was *queued*. The inverter applies it a few
seconds later (3–15s measured on a 12K), and the switch holds your requested state
during that window. If it still reverts, the inverter rejected the command — check the
logs for a warning naming the value the inverter reported.

## Getting Help

- **GitHub Issues:** [GitHub Issues](https://github.com/andrewjfreyer/solark-grid-charge/issues)
- **Logs:** **Settings** → **System** → **Logs** (credentials are redacted)
- **Community:** [Home Assistant Forums](https://community.home-assistant.io/)
