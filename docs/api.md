# API

For the separate scoped tablet credentials, renewable sessions and state stream, see [phone API](phone.md). Ordinary administrator sessions below retain their existing expiration.

The service listens on loopback and the configured home IPv4 address. Default port: 8765. `GET /health` and static UI files are public; all other GET endpoints require authentication. Health means process availability; check `network` in state for building connectivity.

Administrator `/v1/state` also includes `control_health`: `idle`, `connecting`, `retrying`, `ready` or `failed`. It describes the current call's control discovery/connection, separately from the building interface's `network` state. `ready` means the discovery queries completed, not that opening is permitted or a physical lock moved. Local `control_health` journal events record `status`, `reason`, `purpose`, and, during discovery, `attempt` and `elapsed_ms`. Failed discovery requests additionally record `request_ms`, `received` (messages on that peer while the request was outstanding), `invalid` (decode failures), and `unexpected_responses` (other response types). These counters contain no packet payload and do not by themselves establish why a panel did not answer. Events are emitted on transitions rather than every polling iteration. Phone and integration projections retain their existing scoped fields; use their opening permission and outcome events as before.

For Home Assistant and new integrations, use [scoped integration credentials and API](integration-api.md), issued through short-lived pairing codes. The older administrator API below accepts `Authorization: Bearer <api-token>` with full administrator access; do not give that token to the HA custom integration. The web client exchanges its password for a random HttpOnly/SameSite=Strict session cookie, valid for up to 24 hours. Password changes and command-line resets revoke all web sessions and scoped integration grants. Sessions also end when the service restarts. Legacy administrator API tokens are separate and revoked through `fermax.admin api-token`.

| Method / path | Request / result |
|---|---|
| POST /v1/login | password; establishes a session |
| POST /v1/logout | empty JSON object; revokes that session |
| POST /v1/password | current_password, new_password; revokes every session |
| GET /v1/config | saved config and restart_required; does not return credentials |
| POST /v1/config | complete config object; validates and saves while idle, does not reconfigure Linux or restart |
| GET /v1/state | identity, panels, network, call, permissions, policy, clock and recent events |
| POST /v1/auto | minutes: 15, 30, 60, 120, 240, 480, 720, 0 (unlimited), or null (off) |
| POST /v1/control | action, optional panel, request_id |
| GET /v1/phone-preferences | administrator-owned ringtone settings |
| POST /v1/phone-preferences | ringtone: ID from the bundled ringtones.json catalog, or custom; ring_seconds: 15/30/45/60 |
| POST /v1/ringtone | administrator; raw 16-bit PCM WAV, at most 6 MiB and 60 seconds |
| GET /v1/ringtone | administrator; WAV audio, optional revision query |
| GET /v1/frame.jpg | latest fresh JPEG, or 404 |
| GET /v1/logs | limit (1–500), optional before ID and kind |
| GET /v1/logs/export | all application events as UTF-8 CSV |

Supported actions: preview, open, hangup. Answer is reserved and currently rejected because audio transport is not implemented. Preview uses a configured panel ID. Open requires an established session, a relay and the panel's permission. A 202 response is an accepted queue request, not confirmation that a lock moved. Check journal events for the outcome. Reuse the same request_id only when retrying exactly the same intended action; it is persisted to avoid repeated actuation.

A positive panel response yields open_manual/open_auto; rejection yields open_denied; a timeout yields open_unknown without an automatic retry. All logs are local, persistent and potentially sensitive. Do not upload them publicly without redaction.

The current HTTP server rejects cross-origin browser POST requests. It does not trust forwarded headers, implement CORS or provide an HTTPS reverse-proxy configuration. Credentials and controls should remain on the trusted LAN until HTTPS support is added. Passwords are 12–128 characters, stored with PBKDF2-HMAC-SHA256, a random salt and 600,000 iterations. Changing a password does not change an independently issued API token.

## Daily statistics

Administrator `/v1/state`, scoped `/v1/phone/state` and phone SSE `state` add `statistics`: `{ "date": "2030-05-18", "available": true, "incoming": 7, "openings": 4 }`. The date follows the gateway local calendar. Unavailable values are null, not zero. Phone counts are filtered by its authorized panel IDs before serialization. No additional public endpoint or permission is added. See [counting rules and persistence](daily-statistics.md).
