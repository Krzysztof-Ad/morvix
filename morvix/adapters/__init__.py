# Language adapters: the only language-aware part of the system (Section 8).
#
# An adapter knows one thing - how to turn this language's source into something
# runnable, and how to invoke it. It knows nothing about tests, models or
# comparison. That is the whole point: adding a language is writing one adapter
# (Section 4.1), and nothing else in the tool changes.
#
# Each concrete adapter lives in its own module (c.py, cpp.py, ...) and calls
# register() at import time. The registry below is how the rest of the tool
# finds them.

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BuildResult:
    """The outcome of compiling/assembling a solution.

    On success, artifact + the run information are filled in. On failure, ok is
    False and diagnostics holds the toolchain's own output, shown verbatim.
    """

    ok: bool
    artifact: Optional[str] = None        # the produced binary / class dir / script path
    run_argv: List[str] = field(default_factory=list)   # how to invoke the artifact
    run_env: Dict[str, str] = field(default_factory=dict)  # extra env (LD_LIBRARY_PATH, ...)
    diagnostics: str = ""                 # compiler output, shown on failure
    error: Optional[str] = None           # short summary of what went wrong
    build_command: str = ""               # the command line we ran, for messages


@dataclass
class RunSpec:
    """How to actually invoke a built artifact: the argv prefix and extra env.

    The execution model takes this and adds the per-case bits (stdin, argv,
    files) before handing it to the process layer.
    """

    argv: List[str]
    env: Dict[str, str] = field(default_factory=dict)


class Adapter(ABC):
    """The small interface every language exposes (Section 8.3)."""

    name: str = ""

    @abstractmethod
    def build(self, source: str, config: dict, workdir: str) -> BuildResult:
        """Compile/assemble/link (or no-op for interpreted languages)."""

    @abstractmethod
    def run_spec(self, build: BuildResult, config: dict) -> RunSpec:
        """The command + environment needed to run the built artifact."""

    @abstractmethod
    def describe(self, config: dict) -> str:
        """One-line human summary, e.g. 'C, gcc, -std=gnu23, -O2'."""


_REGISTRY: Dict[str, Adapter] = {}

# Map common file extensions to a language name, for auto-detection on import.
_EXTENSIONS = {
    ".c": "c",
    ".h": "c",
    ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".c++": "cpp", ".hpp": "cpp",
    ".asm": "nasm", ".s": "nasm", ".nasm": "nasm",
    ".py": "python",
    ".java": "java",
    ".rs": "rust",
}


def register(adapter: Adapter) -> None:
    _REGISTRY[adapter.name] = adapter


def get_adapter(language: str) -> Adapter:
    _load_builtins()
    if language not in _REGISTRY:
        from morvix.errors import UserError

        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise UserError(
            f"No adapter for language '{language}'.",
            hint=f"Supported: {known}. Or use a raw build/run command (config --raw-build).",
        )
    return _REGISTRY[language]


def list_languages() -> List[str]:
    _load_builtins()
    return sorted(_REGISTRY)


def detect_language(path: str) -> Optional[str]:
    """Guess the language from a file's extension."""
    import os

    return _EXTENSIONS.get(os.path.splitext(path)[1].lower())


_loaded = False


def _load_builtins() -> None:
    # Import the concrete adapters once, so they self-register. Listed explicitly
    # rather than auto-discovered to keep imports predictable.
    global _loaded
    if _loaded:
        return
    _loaded = True
    from morvix.adapters import c, cpp, nasm, python, java, rust  # noqa: F401
