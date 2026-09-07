# FERMAX LYNX Gateway

### A quieter clock. A clearer view of who's at the door.

Turn a compatible LYNX installation into a local, tablet-friendly intercom experience:
a room clock when it's quiet, a large entrance view when someone arrives, and the
controls you need within reach. Runs on Linux, with an optional Raspberry Pi display.

[**Get started**](docs/user-guide.md) · [**中文用户手册**](docs/user-guide.zh-CN.md) · [**Explore every screen**](docs/demo-gallery.md) · [**Download a release**](https://github.com/helixzz/fermax-lynx-gateway/releases) · [**Report an issue**](https://github.com/helixzz/fermax-lynx-gateway/issues)

![Incoming video fills a landscape tablet, with large translucent controls along the bottom. Original synthetic entrance illustration; no camera footage.](docs/demo/phone-incoming.webp)

*Development preview after v0.3.0: the 16-track library and revised administrator layout are not in the v0.3.0 release.
See [changelog](CHANGELOG.md) for release scope.
All images use synthetic data and an original illustrated entrance.*

## Make it feel at home

| A clock for your room | A clock with character |
|---|---|
| ![Editorial clock with large serif numerals](docs/demo/clock-editorial.webp) | ![Warm glowing tube-style clock](docs/demo/clock-nixie.webp) |
| **Editorial** — quiet, spacious numerals. | **Tube** — warm light and a vintage glass effect. |
| ![Clear electronic clock](docs/demo/clock-digital.webp) | ![Classic analog clock](docs/demo/clock-analog.webp) |
| **Digital** — bold digits for a quick glance. | **Analog** — a classic face with ticking or sweeping seconds. |

Show or hide seconds. Choose your own volume. Preferences stay with each tablet;
credentials do not go into browser storage. A first touch reveals controls without
also operating the door.

## See more. Reach less.

The video page uses the full viewport and preserves the complete 4:3 image. A compact
header and translucent, large touch controls sit at its edges. Landscape makes the
most of a tablet's screen; portrait keeps the image uncropped.

- **Incoming video and previews:** see an entrance, end a visit, or use manual opening
  when the active session and panel permit it. There is no fake “answered” state.
- **A familiar sound:** administrators choose 16 original short melodies or upload a
  music excerpt. Loop for 15, 30, 45 or 60 seconds; 30 is the default. Muting or ending
  the visit stops playback, and reconnecting does not restart the whole ringing window.
- **Stay connected:** scoped device grants, automatic short-session renewal, heartbeat
  status and recovery after network interruptions or service restarts.
- **Manage locally:** revoke individual tablets, manage the existing automatic-opening
  policy, inspect events and export the journal. The gateway owns automatic opening;
  multiple tablets do not each repeat it.

![Administrator music selection, duration and upload controls](docs/demo/admin-custom-music.webp)

[Music sources and offline audition →](docs/ringtones.md)

![Automatic opening is enabled; only the Stop action is offered](docs/demo/admin-auto-unlimited.webp)

[Read the illustrated guide →](docs/user-guide.md) · [查看中文操作步骤 →](docs/user-guide.zh-CN.md)

## Is this right for your installation?

This is an **experimental, unofficial interoperability project** for compatible
FERMAX VIVO / LYNX systems. You need a Linux host, separate intercom/home network
interfaces, your own valid site configuration and a compatible 24-byte protocol key.
No key, vendor firmware, private configuration or real camera image is distributed.

| Available in this branch | Still outside the current scope |
|---|---|
| Incoming video, entrance preview, permitted door controls, event journal | Two-way voice and browser microphone support |
| Tablet mode, clock choices, device authorization and configurable ringing | Recording, Home Assistant entities, webhooks and MCP |
| Existing automatic-opening policy and optional SPI display | General compatibility with every building or firmware |

Old iPadOS 15, actual tablet sound, 72-hour foreground operation and seven-day
observation still need field validation. Background/locked-screen ringing is not
promised. HTTP is intended for a trusted LAN; HTTPS support is a separate milestone.
A protocol acknowledgement alone does not establish physical opening or elevator behavior.

## Start with a release

Download a [tagged source release](https://github.com/helixzz/fermax-lynx-gateway/releases),
verify its checksum and extract it. From that directory on Debian / Raspberry Pi OS:

```sh
sudo apt update
sudo apt install python3-pil python3-protobuf python3-pycryptodome python3-enet python3-av
python3 -m fermax.admin init
python3 -m fermax.admin password
# Set your site values in ~/.local/state/fermax/config.json and install your own edk.
chmod 600 ~/.local/state/fermax/edk
python3 -m fermax.main
```

The generated configuration contains documentation addresses, so it cannot be used
unchanged. Configure Linux network addresses separately, keep the intercom interface
without a default route, and avoid an address conflict with the original monitor.
Then open `http://<home-ip>:8765/` and follow the [first-use guide](docs/user-guide.md).
For a system service and optional LCD, use the [deployment guide](docs/deployment.md).

## Explore or contribute

| For users | For contributors |
|---|---|
| [English user guide](docs/user-guide.md) / [中文手册](docs/user-guide.zh-CN.md) | [Contributing](CONTRIBUTING.md) / [coordination](AGENTS.md) |
| [Every screen, with captions](docs/demo-gallery.md) | [API](docs/api.md) / [protocol scope](docs/protocol.md) |
| [Product overview / 项目简介](docs/product.md) | [UI decisions and sources](docs/phone-design.md) |
| [Releases and version rules](docs/releases.md) | [Roadmap](docs/roadmap.md) / [tests](docs/phone.md#limitations-and-validation) |

The gallery also includes a [local HTML demo viewer](docs/demo/index.html): open it
from a downloaded checkout to browse all previews without running a gateway.

MIT for the original implementation; dependencies retain their licenses. FERMAX,
VIVO and LYNX identify compatibility targets. This project is not affiliated with
or endorsed by their owners.
