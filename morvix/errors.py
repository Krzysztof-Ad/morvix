# Error categories.
#
# Section 7 of the design splits failures into three kinds so a message can be
# specific about what went wrong and what to do next. Every internal failure is
# raised as one of these and caught at the top level, where it is turned into a
# clean message (the raw traceback is only shown under --debug). Nothing in
# Morvix should ever dump a Python traceback at the user by default.

from typing import Optional


class MorvixError(Exception):
    """Base for every error we raise on purpose.

    - message: what failed, in plain language.
    - hint:    the next action the user can take (the fix), shown when present.
    """

    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class UserError(MorvixError):
    """A bad command, flag, path, or name - something the user can correct."""


class EnvironmentError_(MorvixError):
    """A missing or broken tool: no compiler, no interpreter, permission denied.

    Named with a trailing underscore so it does not shadow the builtin.
    """


class RunFailure(MorvixError):
    """The program under test misbehaved: crashed, timed out, hit a limit.

    Note this is only an *error* when it was unexpected. A crash that a case
    explicitly expects (Section 14.6) is a pass, not a RunFailure.
    """


# Friendly alias so call sites can read naturally.
EnvError = EnvironmentError_
