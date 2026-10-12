"""Reference in-memory adapter for idempotency-key-spec (passes R1-R12)."""

import time as _time


class InMemoryAdapter:
    """Single-process reference implementation of the adapter contract.

    Constructor accepts ``clock`` (callable -> float seconds) and ``ttl``
    (seconds). States: PENDING -> DONE. Expired records vanish on access and
    are removed by purge().
    """

    def __init__(self, clock=_time.time, ttl=86400.0):
        self._clock = clock
        self._ttl = float(ttl)
        self._store = {}

    def _live(self, key):
        rec = self._store.get(key)
        if rec is None:
            return None
        if self._clock() - rec["created"] > self._ttl:
            del self._store[key]
            return None
        return rec

    def begin(self, key, fingerprint):
        rec = self._live(key)
        if rec is None:
            self._store[key] = {"state": "PENDING", "fingerprint": fingerprint,
                                "result": None, "error": None,
                                "created": self._clock()}
            return "FIRST"
        if rec["fingerprint"] != fingerprint:
            return "CONFLICT"
        return "REPLAY"

    def complete(self, key, result=None, error=None):
        rec = self._live(key)
        if rec is None:
            raise KeyError(key)
        if rec["state"] != "DONE":  # R12: first complete wins
            rec["state"] = "DONE"
            rec["result"] = result
            rec["error"] = error
        return True

    def lookup(self, key):
        rec = self._live(key)
        if rec is None:
            return None
        return {"state": rec["state"], "fingerprint": rec["fingerprint"],
                "result": rec["result"], "error": rec["error"]}

    def purge(self, now):
        expired = [k for k, r in self._store.items()
                   if now - r["created"] > self._ttl]
        for k in expired:
            del self._store[k]
        return len(expired)
