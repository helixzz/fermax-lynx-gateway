# Scoped integration API — schema 1

Available in gateway 0.7.0. Uses local HTTP JSON and SSE; no MQTT dependency.
This is separate from administrator and phone credentials. Send JSON objects and
use `Authorization: Bearer <integration-token>` only on `/v1/integration/*`.
Tokens do not authorize configuration, logs, automatic-opening changes or phone APIs.
Use a trusted network/transport; do not put secrets in URLs or public diagnostics.

## Administrator authorization lifecycle

These plural `/v1/integrations` routes require administrator authentication. Writes
also require the current password; browser writes enforce the existing same-origin
policy. Pairing, exchange and revoke share the existing per-IP authentication limit.

| Method and path | Request / response |
|---|---|
| GET `/v1/integrations` | `{integrations: [{id,name,panels,permissions,created_at}]}` |
| POST `/v1/integrations/pairing` | `{password,name,panels,permissions}` → `{code,expires_in:300}` |
| POST `/v1/integrations/revoke` | `{password,id}` → `{ok:true}` |
| POST `/v1/integration/pair` | No existing credential; `{code}` → `{schema:1,token,integration,gateway}` |

`name` has 1–60 characters; `panels` is a nonempty list of configured panel IDs.
Required permissions: `state`, `events`. Optional: `camera`, `preview`, `hangup`,
`open`. The omitted permission list defaults to state/events. Up to 32 grants and
10 pending codes are allowed. Codes expire after five monotonic minutes, are
single-use/in-memory and bound to the administrator password revision. Exchange
revalidates current panel configuration and persists a hash before returning a token.
Restart discards pending codes. Revocation also discards all outstanding codes.
Grant hashes are persisted in `integrations.json` with mode 0600. Password reset
invalidates all grants; a normal restart preserves them. Removing a granted panel
fails authorization until the integration is paired again with valid scope.

`gateway` is `{id,version}`. Gateway ID and event-journal ID are persistent UUIDs in
the event database's `integration_meta` table. `created_at` is Unix epoch seconds.
Never use a rotating grant ID as a gateway or entity identity.

## State and camera

`GET /v1/integration/state` returns:

```json
{
  "schema": 1,
  "gateway": {"id": "synthetic-gateway-id", "version": "0.7.0"},
  "integration": {"id": "synthetic-grant-id", "name": "Home Assistant", "panels": ["hall"], "permissions": ["events", "state"], "created_at": 1905330000},
  "server_time": 1905330000,
  "cursor": "synthetic-journal-id:42",
  "state": {
    "network": "ready", "call": "idle", "call_id": null,
    "panel_id": null, "panel": null, "direction": null,
    "panels": [{"id": "hall", "name": "Example entrance"}],
    "allow_open": false, "video_ready": false,
    "statistics": {"date": "2030-05-18", "available": true, "incoming": 7, "openings": 4},
    "auto": {"enabled": false, "minutes": null, "expires_at": null}
  }
}
```

Names, statistics and call context are filtered to permitted panels. An active call
at another panel appears as `busy`, with its identity hidden. `allow_open` and
`video_ready` also reflect integration permissions. No network addresses, resident
identities, raw logs or media preferences are included. `server_time` is Unix epoch
seconds; clients can estimate elapsed gateway time with a monotonic local clock.

`GET /v1/integration/frame.jpg?panel=hall` requires camera permission and panel scope.
It returns a JPEG only for the current panel with a frame less than five seconds old;
otherwise 404. It never starts preview and is not a video-streaming endpoint.

## Journal SSE

`GET /v1/integration/events` opens one stream. Supply `Last-Event-ID` to resume a
journal cursor (`journalUUID:integerID`). Four simultaneous integration streams
are allowed independently of phone streams; excess receives 503/Retry-After.
The server rechecks authorization at least each processing loop, normally every
0.5 seconds; revoked streams send `unauthorized` then close. Slow writes time out.

| SSE event | Payload and cursor semantics |
|---|---|
| `snapshot` | Full state response; **no SSE id**. Its payload cursor may be ahead of events still to deliver. |
| `event` | `{id,time,kind,panel_id,call_id,request_id,replayed}`; SSE id equals the journal event ID. |
| `checkpoint` | `{cursor}` and matching SSE id: every preceding row was scanned, including filtered-out rows. |
| `reset` | `{reason:"cursor_reset",cursor}` for an invalid, replaced-journal or future cursor. |
| `ready` | `{cursor}` and matching SSE id: replay to the admission-time head is complete; following events are live. |
| `heartbeat` | Full state response, no SSE id; normally every 15 seconds without a state change. |
| `unauthorized` | Empty object; credential invalid, re-pair instead of repeatedly reconnecting. |

Admission captures a head and sends a snapshot. A valid resume cursor replays the
permitted journal entries up to that head, in bounded 500-row batches; `replayed`
is true. A missing or invalid cursor starts at the current head. Newer events have
`replayed:false`. Clients advance their event cursor only from delivered event,
checkpoint, reset and ready messages, never from a state snapshot.

Kinds: `incoming`, `outgoing`, `call_ended`, `open_manual`, `open_auto`, `open_unknown`,
`open_denied`, `control_failed`. Event time is gateway Unix epoch seconds. Projections
include only these structured fields, never raw protocol results or free-text logs.
IDs reflect persisted rows, not receipt time. Preserve a fully consumed prefix when
processing large or filtered replay; a batch limit is not an end-of-history signal.

For doorbell automations, wait for ready, ignore replayed events, enforce a live age
window, and deduplicate journal IDs and incoming call IDs with bounded caches. The
companion HA integration uses a 30-second window and intentionally suppresses missed
calls after disconnection/startup. This is not an exactly-once notification service.

## Explicit controls

`POST /v1/integration/control`:

```json
{"action":"open","panel":"hall","call_id":"synthetic-call-id","request_id":"48d05ca2-a749-43f5-8159-733e64fc1e97","expires_at":1905330020}
```

Actions `preview`, `hangup`, `open` require their own permission and the selected
panel. `request_id` must be a UUID. `expires_at` is finite Unix seconds, between now
and now+30. Non-preview actions require the current call ID and panel. Preview
requires idle; open additionally requires the existing panel permission and relay.
Authentication, scope, configuration, call and expiry are rechecked while consuming
the action queue and immediately before transmitting a queued opening. A monotonic
deadline prevents a backward wall-clock jump from extending an admitted request.

202 returns `{request_id,duplicate}`; the returned request ID is an opaque grant-ID
namespace plus normalized UUID, also used in outcome events. Identical valid retries
within the same grant are idempotent; different grants cannot collide. Clients should
not automatically retry actuation, especially after an uncertain network result.
An expired retry can be rejected even if its earlier request was accepted.

401 means unavailable/revoked authorization, 403 denied permission or panel, 409
expired/stale/conflicting state, 400 malformed input, and 503 temporary unavailability.
A 202 response only confirms queue admission. `open_manual` reports a positive
protocol response; `open_denied` reports rejection and `open_unknown` means an
unconfirmed outcome. None measures physical door position.
