"""Allowlisted call evidence. Fingerprints compare labels without storing their text."""
import hashlib
import time


def fingerprint(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:24] if isinstance(value, str) else None


def semantics(fields):
    if not isinstance(fields, dict):
        return {}
    out = {key: fields[key] for key in ('doormatic', 'allowOpenDoor', 'openDoorEnable', 'state')
           if type(fields.get(key)) is bool}
    if isinstance(fields.get('relayName'), str):
        out['relay_fingerprint'] = fingerprint(fields['relayName'])
    if isinstance(fields.get('relayTags'), list):
        tags = fields['relayTags']
        out.update(relay_count=len(tags), relay_fingerprints=[fingerprint(v) for v in tags[:16]],
                   relays_truncated=len(tags) > 16)
    if 'pmuTag' in fields:
        out['pmu_tag_present'] = True
    if isinstance(fields.get('result'), str):
        result = fields['result']
        out['result'] = result if result in ('PANEL_OPEN_DOOR_RESULT_OK', 'PANEL_OPEN_DOOR_RESULT_ERROR') else 'other'
    return out


class CallTrace:
    def __init__(self, state, clock=time.monotonic):
        self.state, self.clock = state, clock
        self.started = clock()
        self.sent = self.ok = self.failed = self.inbound = 0
        self.last_ok = None
        self.last_rtt_ms = None
        self.last_error = None
        self.last_summary = float('-inf')
        self.capabilities = None

    def record(self, kind, detail):
        self.state.diagnostics.record(kind, {'call_id': self.state.call_id,
            'panel_id': self.state.panel_id, 'call_elapsed_ms': round((self.clock()-self.started)*1000), **detail},
            **({'rate_key': 'control_invalid', 'interval': 1} if detail.get('stage') == 'invalid' else {}))

    def summary(self, stage, force=False):
        now = self.clock()
        if not force and now-self.last_summary < 5:
            return
        self.last_summary = now
        self.record('session_liveness', {'stage': stage, 'sent': self.sent, 'ok': self.ok,
            'failed': self.failed, 'inbound': self.inbound,
            'last_rtt_ms': self.last_rtt_ms, 'last_error': self.last_error,
            'last_ok_age_ms': None if self.last_ok is None else round((now-self.last_ok)*1000)})

    def keep_result(self, pending):
        success = not pending.error and bool((pending.result or {}).get('state'))
        started = getattr(pending, 'started', None)
        self.last_rtt_ms = round((self.clock()-started)*1000) if isinstance(started, (int, float)) else None
        self.last_error = (pending.error if pending.error in ('timeout', 'disconnected', 'closed')
                           else 'other') if pending.error else (None if success else 'state_false')
        if success:
            self.ok += 1
            self.last_ok = self.clock()
        else:
            self.failed += 1
        self.summary('reply' if success else 'failed', force=not success)

    def capability(self, fields, effective):
        value = semantics(fields) | {'effective_allow_open': effective}
        if value != self.capabilities:
            self.capabilities = value
            self.record('panel_capabilities', value)
