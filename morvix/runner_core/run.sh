#!/usr/bin/env sh
# The habitual entry point for a shared package: ./run.sh <solution> [options].
#
# A thin POSIX sh wrapper around morvix_runner.py. It only needs a Python 3 on
# the machine - nothing else - so the Receiver can run the harness on a clean
# system. It resolves its own directory, finds the runner script next to it (or
# under runner/), finds a python3, and execs it, forwarding all arguments.

# - resolve the directory this script lives in, following one level of symlink
SCRIPT="$0"
if [ -L "$SCRIPT" ]; then
    SCRIPT=$(readlink "$SCRIPT")
fi
DIR=$(cd "$(dirname "$SCRIPT")" && pwd)

# - locate morvix_runner.py: next to this script, under runner/, or .morvix/runner/
if [ -f "$DIR/morvix_runner.py" ]; then
    RUNNER="$DIR/morvix_runner.py"
elif [ -f "$DIR/runner/morvix_runner.py" ]; then
    RUNNER="$DIR/runner/morvix_runner.py"
elif [ -f "$DIR/.morvix/runner/morvix_runner.py" ]; then
    RUNNER="$DIR/.morvix/runner/morvix_runner.py"
else
    echo "error: could not find morvix_runner.py next to run.sh" >&2
    exit 2
fi

# - find a Python 3 interpreter: prefer python3, fall back to python
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "error: no Python 3 found. Install Python 3 and ensure 'python3' is on your PATH." >&2
    exit 2
fi

exec "$PY" "$RUNNER" "$@"
