#!/usr/bin/env python3
"""idempotency-key-spec: formal semantics for idempotency keys + conformance suite.

This repo is deliberately NOT an implementation library (that layer exists —
see README "Why not X"). It defines the key/state/fingerprint/expiry semantics
as rules R1-R12 and ships a conformance harness that runs any adapter against
them. Adapter contract (all methods required):

    Adapter(clock=..., ttl=...)          # clock: () -> float seconds
    .begin(key, fingerprint) -> "FIRST" | "REPLAY" | "CONFLICT"
    .complete(key, result=None, error=None) -> True   # KeyError on unknown key
    .lookup(key) -> {"state", "fingerprint", "result", "error"} | None
    .purge(now) -> int                   # number of records removed

Rules (normative):
  R1  begin on an unseen valid key -> FIRST
  R2  begin again on a pending key, same fingerprint -> REPLAY (result None)
  R3  begin on a pending/done key with a DIFFERENT fingerprint -> CONFLICT
  R4  begin after complete, same fingerprint -> REPLAY with stored result/error
  R5  complete stores the result; lookup exposes it with state DONE
  R6  complete(error=...) stores the error; REPLAY exposes it
  R7  complete on an unknown key raises KeyError
  R8  after ttl has passed (clock), lookup is None and begin -> FIRST again
  R9  purge removes only expired records and returns their count
  R10 keys must be 1-255 chars, printable ASCII (0x21-0x7E); else ValueError
  R11 fingerprint(method, path, payload) is deterministic; changing any input
      changes it
  R12 complete is idempotent: a second complete returns True and does not
      corrupt the stored record
"""
import argparse
import hashlib
import importlib.util
import sys
import time

MAX_KEY_LEN = 255


# ---------------------------------------------------------------- key rules

def validate_key(key):
    """R10: 1-255 chars, printable ASCII 0x21-0x7E. Raises ValueError."""
    if not isinstance(key, str):
        raise ValueError("key must be a string")
    if not 1 <= len(key) <= MAX_KEY_LEN:
        raise ValueError("key length must be 1..%d, got %d" % (MAX_KEY_LEN, len(key)))
    for ch in key:
        if not (0x21 <= ord(ch) <= 0x7E):
            raise ValueError("key must be printable ASCII 0x21-0x7E: %r" % key)
    return key


def normalize_fingerprint(method, path, payload):
    """R11: deterministic sha256 hex of method+path+payload."""
    if not isinstance(method, str) or not isinstance(path, str) \
            or not isinstance(payload, str):
        raise ValueError("method, path and payload must be strings")
    basis = "%s %s\n%s" % (method.strip().upper(), path, payload)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- conformance

def _run_rule(rules, name, fn):
    try:
        detail = fn()
        rules.append({"rule": name, "ok": True, "detail": detail or "ok"})
    except Exception as e:  # noqa: BLE001
        rules.append({"rule": name, "ok": False,
                      "detail": "%s: %s" % (type(e).__name__, e)})


def run_conformance(make_adapter):
    """Run rules R1-R12 against a factory -> list of {rule, ok, detail}.

    ``make_adapter(clock=..., ttl=...)`` must return a fresh adapter each call;
    when called with no arguments it should use its own defaults
    (clock=time.time, ttl=86400).
    """
    rules = []

    def fresh(**kw):
        return make_adapter(**kw)

    def r1():
        a = fresh()
        fp = normalize_fingerprint("POST", "/orders", "{}")
        assert a.begin("k1", fp) == "FIRST", a.begin("k1", fp)
    _run_rule(rules, "R1 first-begin", r1)

    def r2():
        a = fresh()
        fp = normalize_fingerprint("POST", "/x", "p")
        a.begin("k", fp)
        st = a.begin("k", fp)
        assert st == "REPLAY", st
        assert a.lookup("k")["result"] is None
    _run_rule(rules, "R2 pending-replay", r2)

    def r3():
        a = fresh()
        a.begin("k", normalize_fingerprint("POST", "/x", "p1"))
        st = a.begin("k", normalize_fingerprint("POST", "/x", "p2"))
        assert st == "CONFLICT", st
    _run_rule(rules, "R3 fingerprint-conflict", r3)

    def r4():
        a = fresh()
        fp = normalize_fingerprint("POST", "/x", "p")
        a.begin("k", fp)
        a.complete("k", result={"id": 7})
        rec = a.begin("k", fp)
        assert rec == "REPLAY", rec
        assert a.lookup("k")["result"] == {"id": 7}
    _run_rule(rules, "R4 done-replay-with-result", r4)

    def r5():
        a = fresh()
        fp = normalize_fingerprint("POST", "/x", "p")
        a.begin("k", fp)
        a.complete("k", result="res-1")
        rec = a.lookup("k")
        assert rec is not None and rec["state"] == "DONE" and rec["result"] == "res-1"
    _run_rule(rules, "R5 complete-stores-result", r5)

    def r6():
        a = fresh()
        fp = normalize_fingerprint("POST", "/x", "p")
        a.begin("k", fp)
        a.complete("k", error="upstream 500")
        rec = a.lookup("k")
        assert rec["error"] == "upstream 500"
    _run_rule(rules, "R6 error-recorded", r6)

    def r7():
        a = fresh()
        try:
            a.complete("ghost", result=1)
        except KeyError:
            return "KeyError raised"
        raise AssertionError("no KeyError for unknown key")
    _run_rule(rules, "R7 complete-unknown-key", r7)

    def r8():
        t = [1000.0]
        a = fresh(clock=lambda: t[0], ttl=10.0)
        fp = normalize_fingerprint("POST", "/x", "p")
        a.begin("k", fp)
        a.complete("k", result="r")
        t[0] = 1011.0
        assert a.lookup("k") is None, a.lookup("k")
        assert a.begin("k", fp) == "FIRST"
    _run_rule(rules, "R8 ttl-expiry-restart", r8)

    def r9():
        t = [1000.0]
        a = fresh(clock=lambda: t[0], ttl=10.0)
        fp = normalize_fingerprint("POST", "/x", "p")
        a.begin("old", fp)
        a.complete("old", result=1)
        a.begin("new", fp)
        t[0] = 1005.0
        a.begin("young", fp)  # created at 1005, still fresh
        t[0] = 1012.0
        n = a.purge(t[0])
        assert n == 2, n
        assert a.lookup("old") is None and a.lookup("new") is None
        assert a.lookup("young") is not None
    _run_rule(rules, "R9 purge-expired-only", r9)

    def r10():
        for bad in ("", "a" * 256, "has space", "unicode-é", "line\nbreak"):
            try:
                validate_key(bad)
            except ValueError:
                continue
            raise AssertionError("key %r accepted" % bad)
        validate_key("ok-key_123~!@#")
    _run_rule(rules, "R10 key-validation", r10)

    def r11():
        a_fp = normalize_fingerprint("POST", "/x", "p")
        assert normalize_fingerprint("post", "/x", "p") == a_fp  # method normalized
        assert normalize_fingerprint("POST", "/y", "p") != a_fp
        assert normalize_fingerprint("POST", "/x", "q") != a_fp
    _run_rule(rules, "R11 fingerprint-determinism", r11)

    def r12():
        a = fresh()
        fp = normalize_fingerprint("POST", "/x", "p")
        a.begin("k", fp)
        a.complete("k", result="v1")
        assert a.complete("k", result="v2") is True
        rec = a.lookup("k")
        assert rec["result"] == "v1", rec  # first write wins
    _run_rule(rules, "R12 complete-idempotent", r12)

    return rules


# ---------------------------------------------------------------- adapter loading

def load_adapter_class(spec):
    """spec = 'path/to/file.py:ClassName' -> class object."""
    if ":" not in spec:
        raise ValueError("adapter spec must be 'file.py:ClassName'")
    path, cls_name = spec.rsplit(":", 1)
    spec_obj = importlib.util.spec_from_file_location("idem_adapter_mod", path)
    if spec_obj is None or spec_obj.loader is None:
        raise ValueError("cannot load adapter module from %s" % path)
    mod = importlib.util.module_from_spec(spec_obj)
    try:
        spec_obj.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        raise ValueError("adapter module raised on import: %s: %s"
                         % (type(e).__name__, e))
    cls = getattr(mod, cls_name, None)
    if cls is None or not isinstance(cls, type):
        raise ValueError("module %s has no class %r" % (path, cls_name))
    return cls


# ---------------------------------------------------------------- CLI

def cmd_conformance(args):
    cls = load_adapter_class(args.adapter)

    def make(clock=None, ttl=None):
        import time as _t
        try:
            return cls(clock=clock or _t.time,
                       ttl=ttl if ttl is not None else args.ttl)
        except TypeError:
            return cls()

    rules = run_conformance(make)
    failed = 0
    for r in rules:
        print("%s %s — %s" % ("PASS" if r["ok"] else "FAIL", r["rule"], r["detail"]))
        if not r["ok"]:
            failed += 1
    total = len(rules)
    print("SUMMARY: %s %d/%d" % ("PASS" if not failed else "FAIL",
                                 total - failed, total))
    return 0 if not failed else 1


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="idempotency-spec",
        description="Conformance suite for idempotency-key adapter semantics (R1-R12).")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("conformance", help="run R1-R12 against an adapter class")
    c.add_argument("--adapter", required=True, help="path/file.py:ClassName")
    c.add_argument("--ttl", type=float, default=86400.0)
    c.set_defaults(fn=cmd_conformance)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
