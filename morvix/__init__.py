# Morvix - a test-authoring, test-running, and test-sharing CLI for
# university programming assignments.
#
# This package is the tool itself. The stdlib-only runner that ships inside
# shared packages lives in morvix/runner_core/ and is deliberately kept
# separate so it never imports anything from here.

from morvix.version import __version__

__all__ = ["__version__"]
