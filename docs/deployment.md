# Deployment

The commands below assume a repository copied to `/opt/fermax-lynx-gateway` and a dedicated service account named `fermax`. Review paths for your distribution. Run Python from the repository directory or install the package first; ENet and PyAV are OS dependencies in this example.

```sh
sudo useradd --system --home /var/lib/fermax --create-home fermax
sudo install -d -o fermax -g fermax -m 700 /var/lib/fermax
cd /opt/fermax-lynx-gateway
sudo -u fermax python3 -m fermax.admin --state-dir /var/lib/fermax init
sudo -u fermax python3 -m fermax.admin --state-dir /var/lib/fermax password
```

Edit `/var/lib/fermax/config.json` with real site values; keep it mode 600 and owned by fermax. Install your own protocol key at `/var/lib/fermax/edk`, also mode 600. The web UI supports the same configuration fields, but changes require restarting the service. Never commit these files.

`building` is a display label. Numeric `block` (0–99), `unit` and `extension` are used in periodic LYNX identity announcements to configured panels; `unit` also appears in the SIP User-Agent. `monitor_ip` is explicit and is used for bind addresses, SIP addressing and SDP. No universal IP calculator or building-directory provisioning is implemented. Set the OS static address to match before starting. The building interface must have no default route; route home and Internet traffic through `home_interface`. Do not enable forwarding between these interfaces.

```sh
sudo install -m 644 deploy/fermax-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fermax-gateway
journalctl -u fermax-gateway -n 40
```

The sample unit is headless. It preserves `/var/lib/fermax` across updates. Back up the full state directory, including SQLite WAL files while the service is stopped; never publish the backup. Deploy source atomically or stop the service while replacing code. Do not restart during an active call.

## DHCP time service

The NTP helper reads `/etc/fermax-gateway/config.json` for `home_interface`; when absent, it defaults to wlan0. Use a symlink to the active state configuration so interface settings stay aligned:

```sh
sudo install -d /etc/fermax-gateway
sudo ln -s /var/lib/fermax/config.json /etc/fermax-gateway/config.json
sudo install -m 644 deploy/ntp.py /usr/local/lib/fermax-ntp.py
sudo install -m 755 deploy/90-fermax-ntp /etc/NetworkManager/dispatcher.d/
sudo install -m 644 deploy/fermax-ntp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fermax-ntp
timedatectl timesync-status
```

This integration requires NetworkManager and systemd-timesyncd. Other network managers need an equivalent hook. DHCP option 42 takes priority; if absent, the helper configures the public NTP pool. After changing the interface, restart the NTP oneshot too.

## Optional LCD

The existing renderer targets ILI9486, 480×320 RGB565, and ADS7846 touch. Supply a compatible kernel overlay and install `python3-evdev fonts-wqy-microhei`. Grant the service account access to the framebuffer and input device. Add `--display` to ExecStart using a systemd override. The renderer discovers the framebuffer by driver name, not fb0/fb1 numbering.

For console handoff, install `deploy/console.py` as root-owned `/usr/local/lib/fermax-console.py`; add `ExecStartPre=+/usr/bin/python3 /usr/local/lib/fermax-console.py detach` and `ExecStopPost=+/usr/bin/python3 /usr/local/lib/fermax-console.py restore`. Only use these hooks on the supported display. Disable a conflicting tty1 getty, while retaining SSH or serial recovery access.

## Upgrade from the private prototype

The public implementation does not migrate plaintext credentials automatically. Preserve private state, create a validated config.json, run the password command and rotate the API token. Neither the old token nor a protocol key should enter Git. The application uses the minimal schema included in Python source and no longer needs the full vendor descriptor file.

Phone music settings live in `phone-preferences.json` and `phone-music/` under the private state directory. Include both in backups alongside device grants and existing gateway state.

## Gateway sound (v0.5.0)

Install `alsa-utils`; allow the service user access to sound devices (the example unit includes `SupplementaryGroups=audio`). Preserve custom service options when upgrading. Include `gateway-audio.json` in full-state backups. First-upgrade ringing defaults on, but explicit off persists. No desktop login or global default-device change is required. See [sound setup and hardware acceptance](gateway-audio.md).
