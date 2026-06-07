# Tests for the pure behavior-bucketing logic in morvix.fuzz.
#
# behavior_key buckets an observation COARSELY: identical observations collide,
# meaningfully different ones (crash vs clean, much longer output, a different
# timing/memory regime) separate. is_novel detects a never-seen bucket and
# records it. None of this touches an expected answer - it only steers inputs.

from morvix.fuzz import behavior_key, is_novel


def _obs(output=b"", exit=0, signal=None, timed_out=False, wall=0.01, mem_kb=1000):
    return {
        "output": output,
        "exit": exit,
        "signal": signal,
        "timed_out": timed_out,
        "wall": wall,
        "mem_kb": mem_kb,
    }


_LIMITS = {"wall": 1.0, "mem_kb": 100_000}


def test_behavior_key_buckets():
    # Identical observations -> identical key; a key is hashable (a tuple).
    a = behavior_key(_obs(output=b"42\n"), _LIMITS)
    b = behavior_key(_obs(output=b"42\n"), _LIMITS)
    assert a == b
    assert isinstance(a, tuple)
    assert hash(a) == hash(b)


def test_identical_observations_same_key():
    obs = _obs(output=b"hello world\n", exit=0, wall=0.123, mem_kb=4242)
    assert behavior_key(obs, _LIMITS) == behavior_key(dict(obs), _LIMITS)


def test_small_jitter_does_not_change_key():
    # A few bytes of output and a touch more wall time stay in the same regime.
    a = behavior_key(_obs(output=b"100\n", wall=0.01), _LIMITS)
    b = behavior_key(_obs(output=b"101\n", wall=0.012), _LIMITS)
    assert a == b


def test_crash_differs_from_clean_run():
    clean = behavior_key(_obs(output=b"5\n", exit=0), _LIMITS)
    crash = behavior_key(_obs(output=b"", exit=None, signal="SIGSEGV"), _LIMITS)
    assert clean != crash


def test_nonzero_exit_differs_from_clean():
    clean = behavior_key(_obs(exit=0), _LIMITS)
    failed = behavior_key(_obs(exit=1), _LIMITS)
    assert clean != failed


def test_different_signals_differ():
    segv = behavior_key(_obs(exit=None, signal="SIGSEGV"), _LIMITS)
    abrt = behavior_key(_obs(exit=None, signal="SIGABRT"), _LIMITS)
    assert segv != abrt


def test_timeout_is_its_own_regime():
    timeout = behavior_key(_obs(timed_out=True, wall=1.0), _LIMITS)
    clean = behavior_key(_obs(timed_out=False, wall=0.01), _LIMITS)
    assert timeout != clean
    assert timeout[0] == ("timeout",)


def test_much_longer_output_differs():
    short = behavior_key(_obs(output=b"x\n"), _LIMITS)
    long = behavior_key(_obs(output=b"x\n" * 5000), _LIMITS)
    assert short != long


def test_timing_regime_buckets_not_raw():
    # Two fast runs share a bucket; a near-limit run is a different regime.
    fast_a = behavior_key(_obs(wall=0.01), _LIMITS)
    fast_b = behavior_key(_obs(wall=0.05), _LIMITS)
    slow = behavior_key(_obs(wall=0.95), _LIMITS)
    assert fast_a == fast_b
    assert slow != fast_a


def test_memory_regime_buckets_not_raw():
    low_a = behavior_key(_obs(mem_kb=1000), _LIMITS)
    low_b = behavior_key(_obs(mem_kb=5000), _LIMITS)
    high = behavior_key(_obs(mem_kb=95_000), _LIMITS)
    assert low_a == low_b
    assert high != low_a


def test_missing_limits_drops_timing_and_mem():
    # With no limits the timing/mem axes do not invent a distinction.
    a = behavior_key(_obs(wall=0.01, mem_kb=1000), {})
    b = behavior_key(_obs(wall=0.99, mem_kb=999_999), {})
    assert a == b
    # ... yet status and output still distinguish behaviors.
    crash = behavior_key(_obs(exit=None, signal="SIGSEGV"), {})
    assert crash != a


def test_missing_output_handled():
    # A None output is treated as empty, not an error.
    key = behavior_key(_obs(output=None), _LIMITS)
    assert isinstance(key, tuple)
    assert key == behavior_key(_obs(output=b""), _LIMITS)


def test_distinct_token_count_matters():
    # Same length, very different token variety -> different bucket.
    uniform = behavior_key(_obs(output=b"1 1 1 1 1 1 1 1 1 1"), _LIMITS)
    varied = behavior_key(_obs(output=b"1 2 3 4 5 6 7 8 9 10"), _LIMITS)
    assert uniform != varied


def test_is_novel_updates_seen():
    seen = set()
    k1 = behavior_key(_obs(output=b"a\n"), _LIMITS)
    assert is_novel(k1, seen) is True
    # Same key again is no longer novel.
    assert is_novel(k1, seen) is False
    assert k1 in seen


def test_is_novel_distinct_keys_accumulate():
    seen = set()
    keys = [
        behavior_key(_obs(output=b"a\n"), _LIMITS),
        behavior_key(_obs(exit=None, signal="SIGSEGV"), _LIMITS),
        behavior_key(_obs(timed_out=True, wall=1.0), _LIMITS),
    ]
    novel = [is_novel(k, seen) for k in keys]
    assert novel == [True, True, True]
    assert len(seen) == 3
    # Re-seeing any of them is not novel.
    assert all(is_novel(k, seen) is False for k in keys)


def test_no_expected_fields_anywhere():
    # Honesty: the key carries only INPUT-steering signal, no answer fields.
    key = behavior_key(_obs(output=b"answer\n"), _LIMITS)
    flat = repr(key)
    for forbidden in ("expected_output", "expected_hash", "expected_exit", "expected_signal"):
        assert forbidden not in flat
