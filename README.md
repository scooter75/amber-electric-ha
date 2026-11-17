# Amber Electric for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/scooter75/amber-electric-ha.svg?style=for-the-badge)](https://github.com/scooter75/amber-electric-ha/releases)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge)](https://opensource.org/licenses/Apache-2.0)

A custom Home Assistant integration built from the **Amber Electric Public API v2.1.0** (`https://api.amber.com.au/v1`). Monitor real-time wholesale electricity prices, 5-minute and 30-minute forecasts, price spikes, tariff demand windows, daily usage/costs, and NEM grid renewables directly in Home Assistant.

---

## Features

- **Full UI Configuration (`ConfigFlow` & `OptionsFlow`)**: Configure your API token, select from multiple NMIs/sites, choose your NEM state (`NSW`, `SA`, `QLD`, `VIC`), and adjust the polling interval (`30s`–`600s`) without editing YAML.
- **Per-Channel Entities (`general`, `controlledLoad`, `feedIn`)**: Automatically detects all meter channels on your site and creates dedicated sensors:
  - **Price (`AUD/kWh`)**: Ready for the Home Assistant **Energy Dashboard** (with `per_kwh_cents`, `spot_per_kwh_cents`, `tariff_period`, `advanced_price`, and full 48-interval `forecasts` in attributes).
  - **Spot Price (`c/kWh`)**: Raw NEM wholesale spot price (incl. GST).
  - **Price Descriptor**: Enum sensor (`extremelyLow`, `veryLow`, `low`, `neutral`, `high`, `spike`).
  - **Next Interval Price (`c/kWh`)**: Uses Amber's `advancedPrice.predicted` when available, falling back to `perKwh`.
  - **Daily Usage (`kWh`) & Daily Cost (`AUD`)**: Tracks cumulative daily consumption, solar feed-in, and cost.
- **Binary Sensors**:
  - **Price Spike**: Active when `spikeStatus == "spike"`.
  - **Potential Spike**: Active when `spikeStatus` is `"potential"` or `"spike"`.
  - **Price Estimate**: Indicates whether the current interval price is still an estimate (`estimate: true`) or locked in (`estimate: false`).
  - **Demand Window**: Active when your network tariff is inside a peak demand window.
- **Grid Renewables Sensors**: Site-level renewables percentage plus optional state-wide NEM renewables (`/state/{state}/renewables/current`).
- **Home Assistant Action Services**:
  - `amber_electric.get_prices`: Query historical or forecast interval prices up to 7 days.
  - `amber_electric.get_usage`: Query interval usage and cost up to 7 days (within 90 days).

---

## Installation via HACS

1. Open **HACS** in your Home Assistant instance.
2. Click the **three dots menu (`⋮`)** in the top-right corner and select **Custom repositories**.
3. Enter the repository URL:
   ```text
   https://github.com/scooter75/amber-electric-ha
   ```
4. Select **Integration** as the category and click **Add**.
5. Search for **Amber Electric** in HACS and click **Download**.
6. **Restart Home Assistant**.

### Manual Installation

1. Download the latest release ZIP from [GitHub Releases](https://github.com/scooter75/amber-electric-ha/releases).
2. Extract the `custom_components/amber_electric` folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. Log in to the Amber Electric web app at [app.amber.com.au/developers](https://app.amber.com.au/developers) and generate a Personal API Token.
2. In Home Assistant, go to **Settings → Devices & Services → Add Integration**.
3. Search for **Amber Electric** and enter your **API Key** (and optionally your **NEM State**).
4. If you have multiple sites on your account, select the desired NMI from the dropdown.

---

## Home Assistant Energy Dashboard Setup

1. Go to **Settings → Dashboards → Energy**.
2. Under **Electricity Grid → Grid Consumption**, select your meter entity and choose **Use an entity with current price**, then select `sensor.amber_electric_<nmi>_general_price`.
3. Under **Return to Grid**, select your export entity and choose **Use an entity with current price**, then select `sensor.amber_electric_<nmi>_feed_in_price`.

---

## Example Automation (Turn Off High-Load Appliances on Spike)

```yaml
alias: "Amber Price Spike Protection"
trigger:
  - platform: state
    entity_id: binary_sensor.amber_electric_3052282872_general_price_spike
    to: "on"
action:
  - service: climate.turn_off
    target:
      entity_id: climate.living_room_ac
  - service: notify.mobile_app_phone
    data:
      title: "Amber Price Spike!"
      message: >
        Electricity price is now {{ state_attr('sensor.amber_electric_3052282872_general_price', 'per_kwh_cents') }} c/kWh.
```

---

## License

Licensed under the [Apache License 2.0](LICENSE), matching the Amber Electric Public API specification.
