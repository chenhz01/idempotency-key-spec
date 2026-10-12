#!/usr/bin/env python3
"""Self-test for idempotency-key-spec. Run: python self_test.py"""
import contextlib
import io
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import idempotency_spec as ids
from demo_adapter import InMemoryAdapter

TESTS = []


def t(fn):
    TESTS.append(fn)
    return fn


TD = None


def setup():
    global TD
    TD = tempfile.mkdtemp(prefix="iks_test_")


def wp(name):
    return os.path.join(TD, name)


def make(clock=None, ttl=None):
    if clock is None:
        clock = time.time
    return InMemoryAdapter(clock=clock, ttl=86400.0 if ttl is None else ttl)


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    code = None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = ids.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 0
    return code, out.getvalue(), err.getvalue()


def raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc:
        return
    raise AssertionError("expected %s" % exc.__name__)


FP = "fp"  # any string works at adapter level; spec-level uses sha256

# ---------------- [A] functional

@t
def a01_validate_key_ok():
    assert ids.validate_key("abc-KEY_123~!@#$%^&*()") == "abc-KEY_123~!@#$%^&*()"


@t
def a02_validate_key_max_len():
    ids.validate_key("k" * 255)  # boundary: ok


@t
def a03_fingerprint_deterministic():
    f1 = ids.normalize_fingerprint("POST", "/orders", '{"a":1}')
    f2 = ids.normalize_fingerprint("POST", "/orders", '{"a":1}')
    assert f1 == f2 and len(f1) == 64


@t
def a04_fingerprint_method_normalized():
    assert ids.normalize_fingerprint("post", "/x", "p") == \
        ids.normalize_fingerprint("POST", "/x", "p")


@t
def a05_fingerprint_differs():
    base = ids.normalize_fingerprint("POST", "/x", "p")
    assert ids.normalize_fingerprint("PUT", "/x", "p") != base
    assert ids.normalize_fingerprint("POST", "/y", "p") != base
    assert ids.normalize_fingerprint("POST", "/x", "q") != base


@t
def a06_conformance_all_pass():
    rules = ids.run_conformance(make)
    assert len(rules) == 12
    bad = [r for r in rules if not r["ok"]]
    assert not bad, bad


@t
def a07_rule_ids_ordered():
    rules = ids.run_conformance(make)
    assert [r["rule"] for r in rules][:3] == \
        ["R1 first-begin", "R2 pending-replay", "R3 fingerprint-conflict"]


@t
def a08_first_then_replay():
    a = make()
    assert a.begin("k", FP) == "FIRST"
    assert a.begin("k", FP) == "REPLAY"


@t
def a09_conflict():
    a = make()
    a.begin("k", "fp1")
    assert a.begin("k", "fp2") == "CONFLICT"


@t
def a10_replay_after_done():
    a = make()
    a.begin("k", FP)
    a.complete("k", result=42)
    assert a.begin("k", FP) == "REPLAY"
    assert a.lookup("k")["result"] == 42


@t
def a11_lookup_pending_none_result():
    a = make()
    a.begin("k", FP)
    rec = a.lookup("k")
    assert rec["state"] == "PENDING" and rec["result"] is None


@t
def a12_error_recorded():
    a = make()
    a.begin("k", FP)
    a.complete("k", error="boom")
    assert a.lookup("k")["error"] == "boom"


@t
def a13_purge_returns_count():
    t0 = [100.0]
    a = make(clock=lambda: t0[0], ttl=10.0)
    a.begin("a", FP)
    a.complete("a", result=1)
    a.begin("b", FP)
    t0[0] = 200.0
    assert a.purge(200.0) == 2


@t
def a14_expiry_restart():
    t0 = [0.0]
    a = make(clock=lambda: t0[0], ttl=5.0)
    a.begin("k", FP)
    a.complete("k", result="old")
    t0[0] = 6.0
    assert a.lookup("k") is None
    assert a.begin("k", FP) == "FIRST"


@t
def a15_double_complete_first_wins():
    a = make()
    a.begin("k", FP)
    a.complete("k", result="first")
    assert a.complete("k", result="second") is True
    assert a.lookup("k")["result"] == "first"


@t
def a16_cli_conformance_demo_exit0():
    demo = os.path.join(HERE, "demo_adapter.py")
    code, out, _ = run_cli(["conformance", "--adapter", demo + ":InMemoryAdapter"])
    assert code == 0, out
    assert "SUMMARY: PASS 12/12" in out


@t
def a17_cli_per_rule_output():
    demo = os.path.join(HERE, "demo_adapter.py")
    code, out, _ = run_cli(["conformance", "--adapter", demo + ":InMemoryAdapter"])
    for rid in ("R1", "R4", "R8", "R12"):
        assert rid in out, rid


@t
def a18_states_exposed():
    a = make()
    a.begin("k", FP)
    a.complete("k", result=1)
    rec = a.lookup("k")
    assert set(rec) == {"state", "fingerprint", "result", "error"}
    assert rec["state"] == "DONE"


@t
def a19_conformance_repeat_independent():
    r1 = ids.run_conformance(make)
    r2 = ids.run_conformance(make)
    assert [x["ok"] for x in r1] == [x["ok"] for x in r2] == [True] * 12


@t
def a20_rules_json_serializable():
    rules = ids.run_conformance(make)
    json.loads(json.dumps(rules))

# ---------------- [B] exception paths

@t
def b01_empty_key():
    raises(ValueError, ids.validate_key, "")


@t
def b02_key_256():
    raises(ValueError, ids.validate_key, "k" * 256)


@t
def b03_key_with_space():
    raises(ValueError, ids.validate_key, "has space")


@t
def b04_key_unicode():
    raises(ValueError, ids.validate_key, "ключé")


@t
def b05_key_newline():
    raises(ValueError, ids.validate_key, "line\nbreak")


@t
def b06_key_tab():
    raises(ValueError, ids.validate_key, "tab\tkey")


@t
def b07_key_non_string():
    raises(ValueError, ids.validate_key, 12345)


@t
def b08_fingerprint_non_string():
    raises(ValueError, ids.normalize_fingerprint, "POST", "/x", 42)


@t
def b09_complete_unknown_key():
    raises(KeyError, make().complete, "ghost", result=1)


@t
def b10_lookup_unknown_key_none():
    assert make().lookup("ghost") is None


@t
def b11_conflict_then_replay_still_conflict():
    a = make()
    a.begin("k", "fp1")
    a.begin("k", "fp2")
    assert a.begin("k", "fp2") == "CONFLICT"


@t
def b12_cli_broken_adapter_exit1():
    p = wp("bad_adapter.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write("class BadAdapter:\n"
                "    def __init__(self, clock=None, ttl=86400.0):\n"
                "        self.s = {}\n"
                "    def begin(self, key, fp):\n"
                "        return 'REPLAY'\n"  # violates R1/R3
                "    def complete(self, key, result=None, error=None):\n"
                "        return True\n"  # violates R7
                "    def lookup(self, key):\n"
                "        return None\n"
                "    def purge(self, now):\n"
                "        return 0\n")
    code, out, _ = run_cli(["conformance", "--adapter", p + ":BadAdapter"])
    assert code == 1 and "FAIL" in out and "SUMMARY: FAIL" in out


@t
def b13_cli_missing_spec_colon_exit2():
    code, _, err = run_cli(["conformance", "--adapter", "nofile.py"])
    assert code == 2 and "error" in err


@t
def b14_cli_missing_file_exit2():
    code, _, _ = run_cli(["conformance", "--adapter",
                          wp("missing.py:Nope")])
    assert code == 2


@t
def b15_cli_missing_class_exit2():
    demo = os.path.join(HERE, "demo_adapter.py")
    code, _, err = run_cli(["conformance", "--adapter", demo + ":NoSuchClass"])
    assert code == 2 and "error" in err


@t
def b16_adapter_import_crash_exit2():
    p = wp("crash.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write("raise RuntimeError('kaput')\n")
    code, _, err = run_cli(["conformance", "--adapter", p + ":X"])
    assert code == 2 and "RuntimeError" in err


@t
def b17_no_subcommand_exit2():
    code, _, _ = run_cli([])
    assert code == 2


@t
def b18_incomplete_adapter_detected():
    rules = ids.run_conformance(lambda **kw: _HalfAdapter())
    assert not all(r["ok"] for r in rules)


class _HalfAdapter:
    """Adapter missing fingerprint-conflict logic (R3 must fail)."""

    def __init__(self, clock=time.time, ttl=86400.0):
        self._clock, self._ttl, self._s = clock, ttl, {}

    def begin(self, key, fp):
        rec = self._s.get(key)
        if rec is None:
            self._s[key] = {"fingerprint": fp, "result": None, "error": None,
                            "created": self._clock(), "state": "PENDING"}
            return "FIRST"
        return "REPLAY"  # bug: never CONFLICT

    def complete(self, key, result=None, error=None):
        rec = self._s.get(key)
        if rec is None:
            raise KeyError(key)
        rec.update(state="DONE", result=result, error=error)
        return True

    def lookup(self, key):
        rec = self._s.get(key)
        if rec is None:
            return None
        return {k: rec[k] for k in ("state", "fingerprint", "result", "error")}

    def purge(self, now):
        return 0


@t
def b19_r3_flags_half_adapter():
    rules = ids.run_conformance(lambda **kw: _HalfAdapter())
    r3 = [r for r in rules if r["rule"].startswith("R3")][0]
    assert r3["ok"] is False


@t
def b20_r1_still_passes_half_adapter():
    rules = ids.run_conformance(lambda **kw: _HalfAdapter())
    r1 = [r for r in rules if r["rule"].startswith("R1")][0]
    assert r1["ok"] is True

# ---------------- [C] extreme edges

@t
def c01_ttl_zero_expiry():
    t0 = [100.0]
    a = make(clock=lambda: t0[0], ttl=0.0)
    a.begin("k", FP)
    t0[0] = 100.5  # any elapsed time expires
    assert a.lookup("k") is None


@t
def c02_ttl_huge_stable():
    t0 = [0.0]
    a = make(clock=lambda: t0[0], ttl=1e18)
    a.begin("k", FP)
    t0[0] = 1e12
    assert a.lookup("k") is not None


@t
def c03_frozen_clock_never_expires():
    a = make(clock=lambda: 42.0, ttl=10.0)
    a.begin("k", FP)
    a.complete("k", result=1)
    assert a.begin("k", FP) == "REPLAY"


@t
def c04_boundary_key_255_ok_256_fail():
    ids.validate_key("k" * 255)
    raises(ValueError, ids.validate_key, "k" * 256)


@t
def c05_lowest_printable_key():
    ids.validate_key(chr(0x21))  # '!'
    raises(ValueError, ids.validate_key, chr(0x20))  # space


@t
def c06_highest_printable_key():
    ids.validate_key("~" * 10)  # 0x7E


@t
def c07_empty_payload_fingerprint():
    f = ids.normalize_fingerprint("GET", "/x", "")
    assert len(f) == 64


@t
def c08_unicode_payload_fingerprint():
    f1 = ids.normalize_fingerprint("POST", "/x", "中文-🚀")
    f2 = ids.normalize_fingerprint("POST", "/x", "中文-🚀")
    assert f1 == f2 and f1 != ids.normalize_fingerprint("POST", "/x", "中文-🚂")


@t
def c09_payload_with_newlines():
    p = "line1\nline2\nline3"
    assert ids.normalize_fingerprint("POST", "/x", p) == \
        ids.normalize_fingerprint("POST", "/x", p)


@t
def c10_big_payload_timing():
    big = "x" * 1000000
    t0 = time.time()
    ids.normalize_fingerprint("POST", "/x", big)
    assert time.time() - t0 < 2.0


@t
def c11_purge_empty_store():
    assert make().purge(999.0) == 0


@t
def c12_purge_idempotent():
    t0 = [0.0]
    a = make(clock=lambda: t0[0], ttl=1.0)
    a.begin("k", FP)
    t0[0] = 10.0
    assert a.purge(10.0) == 1
    assert a.purge(10.0) == 0


@t
def c13_complete_error_and_result():
    a = make()
    a.begin("k", FP)
    a.complete("k", result="r", error=None)
    rec = a.lookup("k")
    assert rec["result"] == "r" and rec["error"] is None


@t
def c14_many_keys():
    a = make()
    for i in range(200):
        assert a.begin("k%03d" % i, FP) == "FIRST"
    assert a.begin("k000", FP) == "REPLAY"


@t
def c15_result_shapes():
    a = make()
    a.begin("d", FP)
    a.complete("d", result={"nested": [1, 2, {"x": None}]})
    assert a.lookup("d")["result"] == {"nested": [1, 2, {"x": None}]}


def main():
    setup()
    ok = 0
    fails = []
    for fn in TESTS:
        try:
            fn()
            ok += 1
        except Exception as e:  # noqa: BLE001
            fails.append((fn.__name__, repr(e)))
    for name, e in fails:
        print("FAIL %s: %s" % (name, e))
    total = len(TESTS)
    print("SUMMARY: %s %d/%d" % ("PASS" if not fails else "FAIL", ok, total))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
