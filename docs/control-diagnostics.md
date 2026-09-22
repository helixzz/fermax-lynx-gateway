# Control diagnostics

Administrator diagnostics (`GET /v1/diagnostics`, also available in the event viewer)
are local metadata retained for at most seven days / 10,000 records. Export promptly
after a failure; heavy activity may reach the record cap before seven days.

- `control_sent`: local `transaction_id`, purpose, timeout, ACK, effective permission,
  control readiness, dialog age, and allowlisted `request_fields`.
- `control_result`: matching local transaction, elapsed time, receive/invalid/unexpected
  response counts, error, and allowlisted `response_fields`, including relay list
  count and fingerprints, permission and opening result.
- `panel_capabilities`: changes in advertised opening capability and effective permission.
- `session_transport`: connection/disconnection/invalid-message metadata for the current
  panel; invalid-message records are limited to once per second.
- `session_liveness`: outgoing keepalive sent/success/failure counters, incoming keepalive
  count, last processed response latency/error and age of last success. Successful
  results are summarized at most once per five seconds, with additional snapshots
  immediately before an opening, on keepalive failure, call end or network reset.

Relay labels use stable SHA-256 fingerprints (24 hex characters); the first 16 list
entries, total count and truncation flag are retained. These fingerprints support
comparison, not encryption or strong anonymity: protect exported logs. Raw labels,
PMU tag contents, unknown fields, credentials, packets, SDP and media are excluded.
Only presence is stored for a PMU tag. Booleans retain absent versus false semantics.

Transaction IDs correlate local operations only: the legacy transport does not
match replies by these IDs on the wire. Timestamps describe application observation,
not exact packet transmission time. Last-success age is measured when a response
is processed, and liveness counters reset per call. Failed discovery attempts also
retain their result metadata before recovery. Unknown opening result strings are
classified as `other` in diagnostics; the visitor journal is unchanged.

Unavailable diagnostic storage does not disable call processing. This change adds
no control commands, retry, delay policy or elevator authorization mechanism. An
opening OK still does not prove physical lock movement or elevator authorization.
