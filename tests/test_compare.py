# Tests for morvix/compare.py and morvix/comparators.py.
#
# We build CompareInput directly - no running programs, no project files.
# A SimpleNamespace with .root is enough for non-checker strategies.
# For the checker strategy we write a trivial shell script to tmp_path.

import hashlib
import os
import stat
import types

import pytest

from morvix.cases import TestCase
from morvix.compare import CompareInput, compare, make_diff


def _case(**kwargs) -> TestCase:
    defaults = dict(name="t", group="baseline")
    defaults.update(kwargs)
    return TestCase(**defaults)


def _project(root):
    return types.SimpleNamespace(root=str(root))


def _ci(observed: bytes, expected: bytes, case=None, project=None, params=None, root=None):
    if case is None:
        case = _case()
    if project is None:
        project = _project(root or ".")
    return CompareInput(
        observed=observed,
        expected=expected,
        case=case,
        project=project,
        params=params or {},
    )


# --- exact ---


class TestExact:
    def test_pass_equal(self):
        v = compare("exact", _ci(b"hello\n", b"hello\n"))
        assert v.passed

    def test_fail_different(self):
        v = compare("exact", _ci(b"hello\n", b"world\n"))
        assert not v.passed
        assert v.diff is not None
        assert "expected" in v.diff or "world" in v.diff

    def test_fail_trailing_newline(self):
        # exact is byte-for-byte; trailing newline difference must fail
        v = compare("exact", _ci(b"hello", b"hello\n"))
        assert not v.passed

    def test_fail_empty_vs_nonempty(self):
        v = compare("exact", _ci(b"", b"x"))
        assert not v.passed

    def test_pass_empty_both(self):
        assert compare("exact", _ci(b"", b"")).passed


# --- whitespace ---


class TestWhitespace:
    def test_pass_equal(self):
        assert compare("whitespace", _ci(b"42\n", b"42\n")).passed

    def test_pass_trailing_newline_difference(self):
        assert compare("whitespace", _ci(b"42", b"42\n")).passed

    def test_pass_extra_spaces(self):
        assert compare("whitespace", _ci(b"1  2  3\n", b"1 2 3\n")).passed

    def test_pass_leading_trailing_spaces(self):
        assert compare("whitespace", _ci(b"  42  \n", b"42\n")).passed

    def test_fail_different_content(self):
        v = compare("whitespace", _ci(b"1\n", b"2\n"))
        assert not v.passed
        assert v.diff is not None

    def test_pass_empty_vs_whitespace_only(self):
        # whitespace-only output normalises to same as empty
        assert compare("whitespace", _ci(b"   \n  \n", b"")).passed


# --- float ---


class TestFloat:
    def test_pass_exact(self):
        assert compare("float", _ci(b"1.0 2.0\n", b"1.0 2.0\n")).passed

    def test_pass_within_eps_abs(self):
        # default eps_abs=1e-6
        assert compare("float", _ci(b"1.0000005\n", b"1.0\n")).passed

    def test_fail_outside_eps_abs(self):
        v = compare("float", _ci(b"2.0\n", b"1.0\n"))
        assert not v.passed

    def test_pass_custom_epsilon_abs(self):
        ci = _ci(b"1.5\n", b"1.0\n", params={"epsilon_abs": 1.0})
        assert compare("float", ci).passed

    def test_fail_custom_epsilon_abs_exceeded(self):
        ci = _ci(b"3.0\n", b"1.0\n", params={"epsilon_abs": 1.0, "epsilon_rel": 0.0})
        assert not compare("float", ci).passed

    def test_pass_relative_epsilon(self):
        # 1e9 vs 1e9 + 100: diff=100, scale=1e9, diff/scale=1e-7 < default rel 1e-9? No.
        # Use explicit rel large enough.
        ci = _ci(b"1000001.0\n", b"1000000.0\n", params={"epsilon_abs": 0.0, "epsilon_rel": 1e-5})
        assert compare("float", ci).passed

    def test_fail_token_count_mismatch(self):
        v = compare("float", _ci(b"1.0 2.0\n", b"1.0\n"))
        assert not v.passed
        assert "token count" in v.detail

    def test_pass_non_numeric_tokens_equal(self):
        assert compare("float", _ci(b"YES\n", b"YES\n")).passed

    def test_fail_non_numeric_tokens_differ(self):
        v = compare("float", _ci(b"NO\n", b"YES\n"))
        assert not v.passed

    def test_pass_mixed(self):
        assert compare("float", _ci(b"OK 3.14\n", b"OK 3.14\n")).passed


# --- hash ---


class TestHash:
    def test_pass_correct_hash(self):
        data = b"output line\n"
        h = hashlib.sha256(data).hexdigest()
        case = _case(expected_hash=h)
        assert compare("hash", _ci(data, b"", case=case)).passed

    def test_fail_wrong_hash(self):
        case = _case(expected_hash="a" * 64)
        v = compare("hash", _ci(b"something\n", b"", case=case))
        assert not v.passed
        assert "hash mismatch" in v.detail

    def test_fail_no_hash_set(self):
        # expected_hash is None -> empty string, sha256 of data won't match
        case = _case(expected_hash=None)
        v = compare("hash", _ci(b"data\n", b"", case=case))
        assert not v.passed

    def test_no_diff_produced(self):
        case = _case(expected_hash="b" * 64)
        v = compare("hash", _ci(b"x", b"", case=case))
        assert v.diff is None

    def test_pass_empty_bytes_hash(self):
        data = b""
        h = hashlib.sha256(data).hexdigest()
        case = _case(expected_hash=h)
        assert compare("hash", _ci(data, b"", case=case)).passed


# --- checker ---


class TestChecker:
    def test_no_checker_configured(self):
        v = compare("checker", _ci(b"x", b"", params={}))
        assert not v.passed
        assert "no checker" in v.detail

    def test_checker_accepts(self, tmp_path):
        checker = tmp_path / "checker.sh"
        checker.write_text("#!/bin/sh\nexit 0\n")
        checker.chmod(checker.stat().st_mode | stat.S_IEXEC)
        params = {"checker": str(checker)}
        v = compare("checker", _ci(b"anything\n", b"", project=_project(tmp_path), params=params))
        assert v.passed

    def test_checker_rejects(self, tmp_path):
        checker = tmp_path / "checker_fail.sh"
        checker.write_text("#!/bin/sh\nexit 1\n")
        checker.chmod(checker.stat().st_mode | stat.S_IEXEC)
        params = {"checker": str(checker)}
        v = compare("checker", _ci(b"wrong\n", b"", project=_project(tmp_path), params=params))
        assert not v.passed
        assert "checker rejected" in v.detail

    def test_hanging_checker_is_bounded(self, tmp_path):
        """A looping/sleeping checker must time out, not hang the run."""
        checker = tmp_path / "checker_hang.sh"
        checker.write_text("#!/bin/sh\nsleep 30\n")
        checker.chmod(checker.stat().st_mode | stat.S_IEXEC)
        # _wall is the case's wall limit; the checker gets 4x that.
        params = {"checker": str(checker), "_wall": 0.1}
        v = compare("checker", _ci(b"x\n", b"", project=_project(tmp_path), params=params))
        assert not v.passed
        assert "timed out" in v.detail


# --- make_diff helper ---


class TestMakeDiff:
    def test_identical_produces_empty(self):
        assert make_diff(b"a\n", b"a\n") == ""

    def test_diff_contains_minus_plus(self):
        d = make_diff(b"a\n", b"b\n")
        assert "-a" in d and "+b" in d
