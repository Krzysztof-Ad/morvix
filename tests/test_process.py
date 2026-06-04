import sys

import pytest

from morvix.process import ProcessResult, run

PY = sys.executable


def test_echo_stdin_stdout():
    # A program that reads stdin and echoes it back.
    result = run(
        [PY, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
        stdin=b"hello world\n",
    )
    assert result.ok
    assert result.exit_code == 0
    assert result.stdout == b"hello world\n"
    assert not result.timed_out
    assert not result.output_truncated


def test_simple_print():
    result = run([PY, "-c", "print('morvix')"])
    assert result.ok
    assert result.stdout.strip() == b"morvix"
    assert result.stderr == b""


def test_nonzero_exit_code():
    result = run([PY, "-c", "raise SystemExit(3)"])
    assert result.exit_code == 3
    assert not result.ok
    assert not result.timed_out


def test_exit_code_1():
    result = run([PY, "-c", "import sys; sys.exit(1)"])
    assert result.exit_code == 1
    assert not result.ok


def test_exit_code_zero():
    result = run([PY, "-c", "pass"])
    assert result.exit_code == 0
    assert result.ok


def test_wall_timeout():
    result = run([PY, "-c", "import time; time.sleep(30)"], wall_limit=0.3)
    assert result.timed_out
    assert not result.ok


def test_wall_timeout_exit_code_none():
    # When timed out, exit_code is None (process was killed).
    result = run([PY, "-c", "import time; time.sleep(30)"], wall_limit=0.3)
    assert result.timed_out
    assert result.exit_code is None


def test_wall_time_measured():
    result = run([PY, "-c", "pass"])
    assert result.wall_time >= 0.0


def test_output_cap_truncates():
    # Print 100 'x' bytes; cap at 10.
    result = run([PY, "-c", "print('x' * 100)"], output_cap_bytes=10)
    assert result.output_truncated
    assert len(result.stdout) == 10


def test_output_cap_no_truncation_when_small():
    result = run([PY, "-c", "print('hi')"], output_cap_bytes=1000)
    assert not result.output_truncated
    assert b"hi" in result.stdout


def test_stderr_captured():
    result = run([PY, "-c", "import sys; sys.stderr.write('err-msg')"])
    assert b"err-msg" in result.stderr


def test_process_result_fields_present():
    result = run([PY, "-c", "pass"])
    assert isinstance(result, ProcessResult)
    assert isinstance(result.exit_code, int)
    assert result.term_signal is None
    assert isinstance(result.timed_out, bool)
    assert isinstance(result.wall_time, float)
    assert isinstance(result.cpu_time, float)
    assert isinstance(result.peak_mem_kb, int)
    assert isinstance(result.stdout, bytes)
    assert isinstance(result.stderr, bytes)
    assert isinstance(result.output_truncated, bool)


def test_signaled_property_false_on_clean_exit():
    result = run([PY, "-c", "pass"])
    assert not result.signaled


def test_describe_exit_clean():
    result = run([PY, "-c", "pass"])
    assert result.describe_exit() == "exit 0"


def test_describe_exit_nonzero():
    result = run([PY, "-c", "raise SystemExit(2)"])
    assert result.describe_exit() == "exit 2"


def test_describe_exit_timed_out():
    result = run([PY, "-c", "import time; time.sleep(30)"], wall_limit=0.3)
    assert result.describe_exit() == "timed out"


def test_stdin_none_does_not_crash():
    result = run([PY, "-c", "pass"], stdin=None)
    assert result.ok


def test_empty_stdin():
    result = run(
        [PY, "-c", "import sys; data = sys.stdin.read(); print(len(data))"],
        stdin=b"",
    )
    assert result.ok
    assert result.stdout.strip() == b"0"


def test_cpu_time_nonnegative():
    result = run([PY, "-c", "x = sum(range(1000))"])
    assert result.cpu_time >= 0.0


def test_no_timeout_completes_normally():
    result = run([PY, "-c", "print(42)"], wall_limit=5.0)
    assert result.ok
    assert b"42" in result.stdout


def test_output_cap_exact_boundary():
    # Exactly cap bytes of output: should NOT be truncated.
    result = run([PY, "-c", "import sys; sys.stdout.buffer.write(b'abcde')"], output_cap_bytes=5)
    assert not result.output_truncated
    assert result.stdout == b"abcde"


def test_output_cap_one_over_boundary():
    # cap+1 bytes: should be truncated to cap.
    result = run(
        [PY, "-c", "import sys; sys.stdout.buffer.write(b'abcdef')"],
        output_cap_bytes=5,
    )
    assert result.output_truncated
    assert result.stdout == b"abcde"
