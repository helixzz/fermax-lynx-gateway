# Tablet phone mode

The `/phone` page provides a foreground clock, incoming video, panel preview,
manual opening, hangup, a synthesized ringtone and three recent activities.
It uses the existing single-call gateway. Two-way voice and answering arbitration
remain separate; the page does not present video as an answered call.

## Enable and revoke

1. Log in to management and select **平板话机模式**.
2. Name the device, select permitted entrance panels and re-enter the administrator
   password. Enrollment ends that browser's administrator session.
3. Tap **启用话机并测试铃声** and verify the test tone is audible. Browser or
   operating-system mute can still prevent audible ringing.
4. Leave the page visible. Touch the idle clock to reveal controls; this touch
   cannot also operate the door. Controls hide after 20 seconds of inactivity.

Management device settings list grants and allow revocation with a fresh password
check. **退出并撤销此话机** revokes this device. Web password changes and CLI resets
invalidate every grant, including after restart. Phone credentials cannot access
configuration, full logs, passwords or automatic policy changes. Automatic opening
remains exclusively controlled by the gateway; administration requires normal login.

## Sessions and protocol

Only SHA-256 digests of random device secrets and device metadata are stored in
`phone-devices.json` (0600), bound to the current password revision. Up to 32
devices and 256 concurrent short sessions are retained.

The persistent `fermax_device` HttpOnly, SameSite=Strict cookie is restricted to
`/v1/phone/session`. It renews a separate five-minute `fermax_phone` cookie. The page
renews and reconnects every four minutes; short credentials rotate through HTTP
Set-Cookie. Device grants remain valid until revoked. Their browser cookie has a
rolling 400-day Max-Age; browser storage eviction/clearing still requires enrollment.
There is no configurable offline grace policy in this first implementation.
Existing trusted-LAN HTTP deployment is unchanged: TLS/Secure-cookie/proxy support
is a separate prerequisite for HTTPS deployment, not inferred from forwarded headers.

| Endpoint | Authorization and behavior |
|---|---|
| POST `/v1/phone/enroll` | Administrator session/token and current password; `name`, `panels`, `password` |
| GET `/v1/devices` | Administrator; device metadata, never grant digests |
| POST `/v1/devices/revoke` | Administrator and current password; `id`, `password` |
| POST `/v1/phone/session` | Device cookie; rotates short session and renews device cookie |
| POST `/v1/phone/session/logout` | Device cookie; revokes grant, clears both cookies |
| GET `/v1/phone/state` | Short session; scoped full snapshot |
| GET `/v1/phone/events` | Short session; SSE snapshots and 15-second heartbeats |
| GET `/v1/phone/frame.jpg` | Short session; current permitted panel's fresh JPEG |
| POST `/v1/phone/control` | Short session; `action`, `panel`, `call_id`, `request_id` |

Stream messages contain `schema: 1`, per-process `epoch`, increasing state
`version`, `event_id` (`epoch:version`), `server_time`, and `state`. Snapshots include
gateway UTC offset, opaque `call_id`, direction, permitted panel aliases, automatic
policy and three scoped event summaries. Residence identity, panel addresses and
raw journal text/details are omitted.

Every connection begins with a complete snapshot, including when Last-Event-ID is
stale or from another process. Changed snapshots and heartbeats are also complete;
intermediate versions can be coalesced. This is a current-state feed, not a lossless
event subscription. Durable webhooks require a separate journal/outbox contract.

The server samples at most twice a second, admits at most 12 streams across its
listeners, has no per-client event backlog, and bounds socket writes to two seconds.
Authorization is checked each iteration (approximately 0.5 seconds), so revocation
closes existing streams. Control work never waits for stream delivery. Slow clients
are disconnected and recover from snapshots.

The browser discards older versions/abandoned connections, uses jittered 1–30-second
reconnect backoff, disables control on network loss or after a 45-second heartbeat
timeout, and recovers on pageshow/visibility/online events. A short-session failure
gets at most one device-renewal attempt before a new snapshot. Rejected device
renewal (401/403) stops retries and requires enrollment. Controls are never replayed.
Open/hangup require the current call ID at admission and again in the controller
queue. Persisted request IDs deduplicate requests; 202 means queued, not physical opening.
Manual opening outcomes carry the request ID through the controller queue to the
scoped event summary. A page only resolves its pending action from a matching
request/call pair; another client's outcome remains a recent activity.

## Limitations and validation

Video still uses JPEG snapshots; this is not a new streaming media pipeline. Stale
frames are indicated, and old images removed on disconnect/call changes. The clock
follows gateway time/UTC offset and marks unsynchronized or offline time.

Dark idle mode dims page content, not backlight. Wake Lock is requested only when
supported in a secure context; otherwise use system auto-lock settings. Background
or locked-screen ringing is not promised. No microphone is accessed.
Platform references: [SSE framing/connection limits](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events),
[Wake Lock requirements](https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API).

```sh
python3 -m unittest discover -s tests -v
# Optional: install Playwright separately, select Python with gateway dependencies.
PYTHON=python3 node tests/phone_browser.cjs
```

`BROWSER_ENGINE` (default `chromium`, also `webkit`), `PLAYWRIGHT_MODULE`,
`BROWSER_EXECUTABLE`, and `SCREENSHOT_DIR` select local browser
test tools/output. The smoke test launches a synthetic loopback fixture and covers
enrollment, privilege separation, wake touch, preview, incoming display, one opening
request, another client's result, three scheduled renewals using the browser clock,
refresh/offline/restart recovery, revocation and portrait layout. It never
contacts a building network.

Old iPadOS 15 Safari, real tablet sound/autoplay, 72-hour foreground operation and
seven-day observation remain outstanding. Synthetic clock advancement tests 400
consecutive four-minute device renewals beyond 24 hours and verifies that retained
sessions stay bounded; it does not establish real-device endurance.
