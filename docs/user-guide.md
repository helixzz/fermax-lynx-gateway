# Illustrated user guide

[Home](../README.md) · [中文完整手册](user-guide.zh-CN.md) · [Every screen](demo-gallery.md)

This guide covers version 0.3.0, including clock themes, configurable music and the
redesigned video page. All previews use synthetic data;
check the [changelog](../CHANGELOG.md) before choosing a release. UI labels are Chinese.

## Install and connect

Use a Linux host with separate home/intercom interfaces and your own compatible site
identity, addresses and 24-byte protocol key. Download a source release and verify
`sha256sum -c SHA256SUMS` before extraction. From the extracted source directory:

```sh
sudo apt update
sudo apt install python3-pil python3-protobuf python3-pycryptodome python3-enet python3-av
python3 -m fermax.admin init
python3 -m fermax.admin password
```

Set the correct private values in `~/.local/state/fermax/config.json`, supply `edk`
in the same directory with mode 0600, and configure Linux addresses separately.
The generated documentation addresses will not operate an installation. Keep the
intercom interface without a default route, avoid bridging the networks, and avoid
an address conflict with the original monitor. Start with `python3 -m fermax.main`.
The [deployment guide](deployment.md) covers systemd, time synchronization and LCD.

## Authorize a tablet

Open `http://<home-ip>:8765/`, log in, and choose **平板话机模式** (tablet mode). Name
the device, select its permitted entrances, re-enter the administrator password and
choose **授权并进入话机**. Enrollment ends that browser's administrator session.

![Tablet enrollment with entrance scope and administrator confirmation](demo/phone-enrollment.webp)

Tap **启用并试听铃声** (enable and test ringing) and confirm actual sound. Device
grants survive refreshes and service restarts; clearing browser data, revoking the
device or changing the password requires fresh enrollment. A first touch of the
idle clock only reveals controls.

## Choose a clock and seconds behavior

![Per-tablet display and sound preferences](demo/phone-preferences.webp)

Choose **雅致** (editorial), **清晰** (digital), **经典** (analog), or **暖光** (tube).
Seconds can be hidden, ticking or sweeping. Sweep applies to the analog hand; digital
seconds remain whole numbers. Reduced-motion preferences use ticking instead.
Style, seconds mode and volume belong to this browser, not every device. These
cosmetic preferences contain no credentials.

| Editorial | Analog |
|---|---|
| ![Editorial clock](demo/clock-editorial.webp) | ![Analog clock](demo/clock-analog.webp) |
| Digital | Tube |
| ![Digital clock](demo/clock-digital.webp) | ![Tube clock](demo/clock-nixie.webp) |

The clock follows gateway time and labels unsynchronized/offline time. Dimming
changes page content, not screen backlight. Configure the device's auto-lock behavior;
background and locked-screen ringing are not guaranteed.

## Administrator music settings

In **设备与密码设置**, choose a built-in melody or upload custom music. **试听 3 秒**
previews the selection; **停止试听** stops it. Save **15, 30, 45 or 60 seconds** of
looping, with **30 seconds** as the default. New settings apply to the next incoming
visit on all tablets, without changing automatic opening or restarting the service.

![Custom music and ringing duration](demo/admin-custom-music.webp)

For custom music, select a browser-decodable MP3, WAV or M4A of at most 60 seconds and
10 MB. Choose **上传并选择**, then **保存铃声设置**. Only the latest uploaded track is
retained. Use music you have rights to use; no external music service receives it.
If decoding fails, try WAV or another administrator browser. Unavailable custom
music falls back to the built-in chime with a message.

The ringing window starts when the gateway receives the visit. Joining late,
refreshing or reconnecting only uses the remaining time; an expired window is not
replayed. The melody loops until the limit, mute, disconnection or call end. Video
and controls remain available after ringing expires. Changes during an active visit
apply to the next visit.

## Incoming video and controls

![Full landscape video with translucent controls](demo/phone-incoming.webp)

Video uses the complete viewport with `contain` scaling, so the 4:3 image is neither
stretched nor cropped. Landscape tablets use more of the screen; portrait preserves
letterboxing. Large controls stay at the edges:

| Label | Action |
|---|---|
| 开门 | Request opening, only with a valid current session and panel permission |
| 结束来访 / 结束预览 | End the visit or preview |
| 本次静音 | Silence this visit immediately, keeping video and the next visit's ringing |
| 启用铃声 | Allow audio with a gesture when the browser has not enabled it yet |

This release does not implement two-way voice or present video as an answered call.
Opening results are associated with the originating request; uncertain outcomes are
not automatically retried. Existing automatic-opening policy runs on the gateway,
not separately in every tablet. An acknowledgement is not proof of physical opening.

## Devices, settings and events

![Authorized device management](demo/admin-devices.webp)

Administrators can review entrance scope and revoke a device with password
confirmation. **退出并撤销此话机** on the tablet revokes its own grant. Closing the
page does not revoke it. Changing the administrator password revokes all phone grants.

Display preferences do not require device re-enrollment. Hardware/network settings
remain in management; saving them requires a service restart and does not configure
Linux interfaces. The recent-activity disclosure is in the tablet panel; the full
journal, filters and CSV export are in management.

## Troubleshooting and maintenance

| Symptom | What to check |
|---|---|
| No ring | Enable/test with a touch, check system mute and both volume settings. An expired ringing window will not restart. |
| Music upload fails | Use a decodable file within 60 seconds/10 MB; try WAV or another browser. |
| Offline | Controls disable and the old image clears. Wait for reconnection; controls are never replayed. |
| Stale video | The image is removed and explicitly marked unavailable. |
| Portrait bars | Expected when preserving the complete 4:3 frame; rotate to landscape for a larger view. |
| Authorization required | Check password changes, revocation or cleared browser storage, then enroll again. |

![Disconnected page with disabled controls](demo/phone-offline.webp)

Before upgrading, confirm no active call and back up code plus the entire private
state directory, including `phone-preferences.json`, `phone-music/` and device grants.
Follow [deployment and rollback guidance](deployment.md); avoid restoring old state
that could undo credential revocations. Recover a forgotten password as the service
user: `python3 -m fermax.admin --state-dir /var/lib/fermax password`. API tokens are
independent and rotate with the `api-token` subcommand.

Old iPadOS 15, real tablet sound and 72-hour/seven-day endurance validation remain
outstanding. Voice, recording, webhooks, MCP and HTTPS are outside current scope.
See the [complete gallery](demo-gallery.md) for every normal and exceptional screen.
