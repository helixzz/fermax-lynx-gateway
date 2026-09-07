# Changelog

## Unreleased

- Independent gateway ringing with persistent on/off, application volume and USB → analog → HDMI output selection; bounded failure fallback.
- Shared Web/LCD gateway sound settings and explicit three-second hardware sound test.
- Repeated incoming events preserve the original music pin and ringing deadline.
- Requires alsa-utils and service-user audio access; enabled by default on first upgrade. Hardware acceptance remains open.

## 0.4.0 — 2026-09-07

- Sixteen locally synthesized original ringtone scores with grouped selection, audition and source/license records.
- State-driven administrator automatic-opening controls; enabled policies expose only Stop.
- Separate management navigation and settings sections, fixing overlapping entry buttons across screen sizes.
- Updated synthetic demos, offline sound audition and guides.


## 0.3.0 — 2026-09-07

- Four phone clock styles with hidden/ticking/sweeping seconds and device-local display preferences.
- Larger touch typography and a full-viewport, uncropped 4:3 video layout with translucent controls.
- Administrator ringtone melodies or uploaded music; 15/30/45/60-second loops, default 30, bounded by monotonic call age.
- Illustrated English/Chinese guides, synthetic all-screen demos and a redesigned project introduction.

## 0.2.0 — 2026-09-07

### Added

- Foreground tablet `/phone` page with clock, touch controls, incoming video,
  panel preview, manual opening, hangup, ringtone activation/mute and recent activity.
- Scoped, revocable device grants that survive restarts; rotating five-minute
  sessions with automatic renewal, password-reset revocation and administrator
  privilege separation.
- Bounded SSE snapshots, heartbeat and reconnect recovery; scoped JPEG access.
- Documented versioning and release procedure.

### Fixed

- Reject stale-call phone commands both at admission and in the controller queue.
- Match manual opening results to their originating request and call, including
  denial/timeout; another client's result cannot satisfy the pending action.
- Prevent late HTTP replies from clearing a newer pending operation.

### Validation and limits

50 synthetic Python tests and Chromium/WebKit loopback flows passed, including
400 simulated four-minute renewals and request correlation. Old iPadOS 15, actual
tablet sound, 72-hour foreground endurance and seven-day observation remain open.
Two-way voice, answering arbitration, configurable offline grace, HTTPS, recording,
webhooks and MCP are not included. State snapshots may coalesce intermediate events.

### Upgrade and rollback

Back up the full private state and code before upgrading while no call is active.
Existing configuration and automatic opening policy are retained. Enrollment adds
`phone-devices.json`; no existing database schema migration is required. A service
restart ends in-memory administrator/short phone sessions; device grants can renew.
Rolling back code removes phone functionality. Keep the newer private state intact
unless a separately verified state restore is necessary; restoring an older device
registry can undo revocations. Never publish state backups with release assets.
