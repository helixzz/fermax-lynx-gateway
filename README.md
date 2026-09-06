# FERMAX LYNX Gateway

A self-hosted Linux gateway for a compatible FERMAX VIVO / LYNX installation. It replaces an indoor monitor's observed video and door-control functions with a local web interface, JSON API, event journal, and optional Raspberry Pi touch display.

**Experimental interoperability project, not an official FERMAX product.** Tested at one installation. Other firmware, addressing plans, panels and elevator integrations require validation. Local voice, browser audio, Home Assistant entities, webhooks and MCP are not implemented yet.

## Features

- Configurable building/unit label, apartment number, extension, monitor IP, network interfaces and up to eight entrance panels. No real residence information is embedded in the source.
- Incoming-call video and on-demand previews, dynamic door permission/relay queries, manual opening, automatic opening and hangup.
- Persistent automatic-open timers, including unlimited duration; automatic opening applies only to incoming calls and attempts once per call.
- Single-user web password changes, salted PBKDF2 hashes, revocable sessions, separate API tokens and command-line password recovery.
- Complete SQLite application-event journal, filtering, pagination and CSV export. This is not a recording or packet-capture archive.
- DHCP NTP selection with a public fallback when no NTP server is supplied; optional small SPI display with clock and recent events.

## What you need

A Linux machine with a network interface dedicated to the building intercom and a separate home-network interface. Raspberry Pi with Ethernet for the intercom and Wi-Fi for the home network is one tested arrangement. A local microphone or speaker is not required for video and door controls.

Supply your own installation addresses and a compatible 24-byte protocol key in a private file named `edk`. **No protocol key, firmware archive, vendor descriptor bundle, captured traffic, private configuration or camera image is distributed.** The repository contains a small, source-defined wire schema for the operations it implements. It does not provide a key-discovery or firmware-extraction tool.

The example uses reserved documentation IP addresses and will not work unchanged. Changing the apartment label does not provision the building controller or assign an IP to Linux. Obtain the correct site configuration; do not assume an address formula proven at one site applies everywhere. Disconnect the original monitor before using its address.

## Quick start (Debian / Raspberry Pi OS)

```sh
sudo apt update
sudo apt install python3-pil python3-protobuf python3-pycryptodome python3-enet python3-av
python3 -m fermax.admin init
python3 -m fermax.admin password
# Edit ~/.local/state/fermax/config.json and place your private key in edk.
chmod 600 ~/.local/state/fermax/edk
python3 -m fermax.main
```

Run these commands from the repository directory. Configure the Linux interfaces separately: the intercom interface needs the site's static address/subnet and no default route; home traffic uses the home interface. Keep IP forwarding disabled. The program binds building protocols to `monitor_ip`, and HTTP to the home IPv4 address and loopback. It does not bridge the networks.

Open `http://<home-ip>:8765/` and log in with the password you set. Device settings and password management are available in the web interface. Saved device settings require a service restart; they do not change OS network configuration. The UI is currently Chinese.

For a headless system service, see [deployment](docs/deployment.md). The optional display supports the observed ILI9486/ADS7846 480×320 profile and shows the first two panels; the web interface shows all configured panels. Other displays need adaptation.

## Password recovery

Passwords are hashed in `auth.json`; they cannot be read back. Run the recovery command as the service user with the same state directory:

```sh
python3 -m fermax.admin --state-dir /var/lib/fermax password
```

It prompts twice, writes a new hash and invalidates existing web sessions without restarting. `--stdin` is available for a protected pipeline; never put a password on the command line. Do not edit the hash format manually.

API tokens are independent of web passwords. To generate or revoke an API token:

```sh
python3 -m fermax.admin --state-dir /var/lib/fermax api-token
```

The new token is written to `api-token`; it is not printed. The HTTP service is intended for a trusted LAN. HTTPS is not built in; deployment behind a reverse proxy needs a separate HTTPS/origin/cookie configuration change. Do not expose this development HTTP endpoint directly to the Internet.

## API and roadmap

See [API](docs/api.md), [protocol scope](docs/protocol.md) and [roadmap](docs/roadmap.md). Webhook and MCP plans are proposals only; the gateway does not send event data to external services.

## Validation

```sh
python3 -m unittest discover -s tests -v
```

Public tests use fabricated identities and messages, documentation IPs and synthetic media. ENet tests communicate only over loopback; controller tests do not create network sockets or operate locks. Private traffic was used during development but is not required to run the public suite.

A compatible site has confirmed automatic opening followed by its existing elevator-floor authorization. Elevator authorization is an effect of that site's door workflow, not a standalone feature or arbitrary floor-selection API. Signaling success alone does not prove physical opening; each installation needs its own checks. No long-term reliability claim is made.

## 中文简述

这是一个自托管的 LYNX 室内机网关原型，支持真实视频、开门、自动策略与日志。楼号、门牌号、分机、设备 IP、接口和门口机列表均可配置；没有内置真实住户信息或协议密钥。

网页“设备与密码设置”支持保存配置和修改密码。设备配置保存后需重启服务，Linux 网卡地址另行配置。忘记密码可运行 `python3 -m fermax.admin password`，无需多用户系统。Webhook 和 MCP 目前仅有提案与工作量评估。

## License

MIT for this repository's original implementation. Third-party packages retain their own licenses. FERMAX, VIVO and LYNX names identify compatibility targets; this project is not affiliated with or endorsed by their owners.
