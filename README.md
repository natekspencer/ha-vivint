<!-- BEGIN AUTO-GENERATED HEADER -->

[![Release](https://img.shields.io/github/v/release/natekspencer/ha-vivint?style=for-the-badge)](https://github.com/natekspencer/ha-vivint/releases)
[![HACS Badge](https://img.shields.io/badge/HACS-default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![Buy Me A Coffee/Beer](https://img.shields.io/badge/Buy_Me_A_☕/🍺-F16061?style=for-the-badge&logo=ko-fi&logoColor=white&labelColor=grey)](https://ko-fi.com/natekspencer)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor_💜-6f42c1?style=for-the-badge&logo=github&logoColor=white&labelColor=grey)](https://github.com/sponsors/natekspencer)

![Downloads](https://img.shields.io/github/downloads/natekspencer/ha-vivint/total?style=flat-square)
![Latest Downloads](https://img.shields.io/github/downloads/natekspencer/ha-vivint/latest/total?style=flat-square)

<!-- END AUTO-GENERATED HEADER -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="custom_components/vivint/brand/dark_logo.png">
  <img alt="Vivint logo" src="custom_components/vivint/brand/logo.png">
</picture>

# Vivint for Home Assistant

Home Assistant integration for a Vivint home security system.

<!-- BEGIN AUTO-GENERATED INSTALLATION -->

## ⬇️ Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=natekspencer&repository=ha-vivint&category=integration)

This integration is available in the default [HACS](https://hacs.xyz/) repository.

1. Use the **My Home Assistant** badge above, or from within Home Assistant, click on **HACS**
2. Search for `Vivint` and click on the appropriate repository
3. Click **DOWNLOAD**
4. Restart Home Assistant

### Manual

If you prefer manual installation:

1. Download or clone this repository
2. Copy the `custom_components/vivint` folder to your Home Assistant `custom_components` directory. If this is your first custom component, you may need to create the directory.
   Example paths:
   - Hassio: `/config/custom_components`
   - Hassbian: `/home/homeassistant/.homeassistant/custom_components`
3. Restart Home Assistant

> ⚠️ Manual installation will not provide automatic update notifications. HACS installation is recommended unless you have a specific need.

## ➕ Setup

Once installed, you can set up the integration by clicking on the following badge:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=vivint)

Alternatively:

1. Go to [Settings > Devices & services](https://my.home-assistant.io/redirect/integrations/)
2. In the bottom-right corner, select **Add integration**
3. Type `Vivint` and select the **Vivint** integration
4. Follow the instructions to add the integration to your Home Assistant
<!-- END AUTO-GENERATED INSTALLATION -->

## ⚙️ Options

After this integration is set up, you can configure a couple of options relating to the camera streams:

- **HD Stream** - indicates whether to stream the camera in high definition or not, defaults to `True`
- **RTSP Stream** - which RTSP stream source to use, defaults to `Direct`. Can be one of:
  - _Direct_ - falls back to the internal RTSP stream if direct access is unavailable
  - _Internal_ - use this if, for some reason, you have a camera that doesn't seem to stream despite the Vivint API indicating direct access is available for it
  - _External_ - use this option if your Vivint system and Home Assistant installation are on separate networks without access to each other

---

<!-- BEGIN AUTO-GENERATED FOOTER -->

## ❤️ Support Me

I maintain this Home Assistant integration in my spare time. If you find it useful, consider supporting development:

- 💜 [Sponsor me on GitHub](https://github.com/sponsors/natekspencer)
- ☕ [Buy me a coffee / beer](https://ko-fi.com/natekspencer)
- 💸 [PayPal (direct support)](https://www.paypal.com/paypalme/natekspencer)
- ⭐ [Star this project](https://github.com/natekspencer/ha-vivint)
- 📦 If you’d like to support in other ways, such as donating hardware for testing, feel free to [reach out to me](https://github.com/natekspencer)

If you don't already own a Vivint system, please consider using [my referral code (35fr23sv)](https://www.vivint.com/get?refCode=35fr23sv&v=200) and get a free Doorbell Camera Pro from Vivint (as well as a tip to me in appreciation)! You can also call (855) 747-7199 and mention referral code `35fr23sv`.

## 📈 Star History

[![Star History Chart](https://api.star-history.com/chart?repos=natekspencer/ha-vivint&type=date&legend=top-left)](https://www.star-history.com/?repos=natekspencer%2Fha-vivint)

<!-- END AUTO-GENERATED FOOTER -->
