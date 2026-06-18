# config command - set how a language is built and run (Section 9).
#
# Two jobs:
#   - the raw build/run escape hatch (--raw-build/--raw-run), which overrides
#     presets entirely (Section 9.3);
#   - per-language settings (compiler, std, flags, ...) stored under
#     project.languages[<lang>], applied from flags one-shot or via a guided
#     form interactively.
# After a change we print the adapter's one-line describe() summary.

from morvix.adapters import get_adapter, list_languages
from morvix.compare import list_strategies
from morvix.components.form import Field, run_form
from morvix.errors import UserError

NAME = "config"


def configure(parser):
    parser.add_argument(
        "language",
        nargs="?",
        choices=list_languages(),
        help="language to configure (cpp, c, python, java, nasm, rust)",
    )
    # Project-wide judging settings (no language needed). These used to be
    # editable only at 'init' or per-run; setting them here bakes them into the
    # shipped package without hand-editing config/project.json.
    judging = parser.add_argument_group("judging (project-wide)")
    judging.add_argument("--compare", choices=list_strategies(), help="default comparison strategy")
    judging.add_argument("--checker", help="checker program for --compare checker")
    judging.add_argument("--epsilon-abs", type=float, help="absolute tolerance for --compare float")
    judging.add_argument("--epsilon-rel", type=float, help="relative tolerance for --compare float")
    judging.add_argument("--wall", type=float, metavar="SEC", help="default wall-clock limit")
    judging.add_argument("--cpu", type=float, metavar="SEC", help="default cpu-time limit")
    judging.add_argument("--memkb", type=int, metavar="KB", help="default address-space limit")
    judging.add_argument("--output-kb", type=int, metavar="KB", help="default output-size limit")
    parser.add_argument("--compiler", help="C/C++ compiler (e.g. g++, clang++)")
    parser.add_argument("--std", help="language standard (e.g. c++20, gnu23)")
    parser.add_argument("--opt", help="optimisation level (e.g. O2)")
    parser.add_argument("--flags", nargs="*", help="extra compiler flags")
    parser.add_argument("--include", nargs="*", help="include dirs (-I)")
    parser.add_argument("--lib", nargs="*", help="libraries to link (-l)")
    parser.add_argument("--libdirs", nargs="*", help="library search dirs (-L)")
    parser.add_argument("--interpreter", help="Python interpreter (e.g. python3)")
    parser.add_argument("--classpath", help="Java classpath")
    parser.add_argument("--release", help="Java release / Rust release build (on)")
    parser.add_argument("--format", help="NASM object format (e.g. elf64, macho64)")
    parser.add_argument("--link", choices=["ld", "gcc"], help="NASM linker")
    parser.add_argument("--edition", help="Rust edition (e.g. 2021)")
    parser.add_argument("--raw-build", help="raw build command, overrides presets")
    parser.add_argument("--raw-run", help="raw run command, overrides presets")


# Which flags are meaningful for each language, mapping CLI arg -> config key.
# Anything not listed for a language is simply ignored for that language.
_LANG_FLAGS = {
    "cpp": {
        "compiler": "compiler",
        "std": "std",
        "opt": "opt",
        "flags": "flags",
        "include": "include",
        "lib": "lib",
        "libdirs": "libdirs",
    },
    "c": {
        "compiler": "compiler",
        "std": "std",
        "opt": "opt",
        "flags": "flags",
        "include": "include",
        "lib": "lib",
        "libdirs": "libdirs",
    },
    "python": {"interpreter": "interpreter"},
    "java": {"compiler": "javac", "classpath": "classpath", "release": "release"},
    "nasm": {"format": "format", "link": "link", "flags": "flags"},
    "rust": {"compiler": "rustc", "edition": "edition", "release": "release"},
}

# A small, sensible field set per language for the interactive form. Each entry
# is (config-key, label, kind, default-when-unset).
_LANG_FORM = {
    "cpp": [
        ("compiler", "Compiler", "text", "g++"),
        ("std", "Standard", "text", "c++20"),
        ("opt", "Optimisation", "text", "O2"),
    ],
    "c": [
        ("compiler", "Compiler", "text", "gcc"),
        ("std", "Standard", "text", "gnu23"),
        ("opt", "Optimisation", "text", "O2"),
    ],
    "python": [("interpreter", "Interpreter", "text", "python3")],
    "java": [
        ("javac", "javac", "text", "javac"),
        ("java", "java", "text", "java"),
        ("classpath", "Classpath", "text", ""),
        ("release", "Release", "text", ""),
    ],
    "nasm": [("format", "Object format", "text", "elf64"), ("link", "Linker", "choice", "gcc")],
    "rust": [
        ("rustc", "rustc", "text", "rustc"),
        ("edition", "Edition", "text", "2021"),
        ("release", "Release build", "bool", False),
    ],
}


def run(ctx, args) -> int:
    project = ctx.require_project()

    # --- raw build/run escape hatch: overrides any preset (Section 9.3) ---
    raw_build = getattr(args, "raw_build", None)
    raw_run = getattr(args, "raw_run", None)
    if raw_build is not None or raw_run is not None:
        if raw_build is not None:
            project.raw_build = raw_build
        if raw_run is not None:
            project.raw_run = raw_run
        ctx.save_project()
        if raw_build is not None:
            ctx.messenger.success(f"Raw build command set: {raw_build}")
        if raw_run is not None:
            ctx.messenger.success(f"Raw run command set: {raw_run}")
        ctx.messenger.info("Raw commands override language presets.")
        return 0

    # --- project-wide judging settings (comparison + limits, no language) ---
    judging_changed = _apply_judging(project, args)

    lang = getattr(args, "language", None)
    if lang is None:
        if judging_changed:
            ctx.save_project()
            ctx.messenger.success("Updated judging settings.")
            ctx.messenger.info(_judging_summary(project))
            return 0
        raise UserError(
            "Nothing to configure.",
            hint="Pass a language (e.g. 'config cpp'), set judging (e.g. --compare exact, "
            "--wall 5), or use --raw-build/--raw-run.",
        )

    cfg = dict(project.lang_config(lang))  # start from what's already stored

    provided = _collect_flags(args, lang)
    if provided:
        # One-shot: merge the provided, language-relevant flags.
        cfg.update(provided)
    elif ctx.interactive:
        # No flags: open the guided form, pre-filled from existing/global config.
        result = _run_lang_form(ctx, lang, cfg)
        if result is None:
            ctx.messenger.info("Cancelled.")
            return 0
        cfg.update(result)
    # else: no flags, non-interactive -> just (re)assert the language with what's there.

    project.set_lang_config(lang, cfg)
    project.language = lang
    ctx.save_project()

    summary = get_adapter(lang).describe(cfg)
    ctx.messenger.success(f"Configured {lang}.")
    ctx.messenger.info(summary)
    return 0


# Apply any project-wide judging flags that were given. Returns True if anything
# changed, so the caller knows whether to save/report when no language is set.
def _apply_judging(project, args):
    changed = False
    if getattr(args, "compare", None):
        project.compare["strategy"] = args.compare
        changed = True
    if getattr(args, "checker", None):
        project.compare["checker"] = args.checker
        changed = True
    if getattr(args, "epsilon_abs", None) is not None:
        project.compare["epsilon_abs"] = args.epsilon_abs
        changed = True
    if getattr(args, "epsilon_rel", None) is not None:
        project.compare["epsilon_rel"] = args.epsilon_rel
        changed = True
    for arg_name, key in (
        ("wall", "wall"),
        ("cpu", "cpu"),
        ("memkb", "mem_kb"),
        ("output_kb", "output_kb"),
    ):
        value = getattr(args, arg_name, None)
        if value is not None:
            project.limits[key] = value
            changed = True
    return changed


def _judging_summary(project):
    bits = ["compare=%s" % project.compare.get("strategy")]
    if project.compare.get("strategy") == "checker" and project.compare.get("checker"):
        bits.append("checker=%s" % project.compare["checker"])
    limits = {k: v for k, v in project.limits.items() if v is not None}
    if limits:
        bits.append("limits " + ", ".join("%s=%s" % kv for kv in sorted(limits.items())))
    return "Judging: " + "; ".join(bits)


# Pull the flags relevant to this language off args, returning a config dict of
# only the ones the user actually gave (None = not provided).
def _collect_flags(args, lang):
    out = {}
    for arg_name, cfg_key in _LANG_FLAGS.get(lang, {}).items():
        value = getattr(args, arg_name, None)
        if value is None:
            continue
        if cfg_key == "release":
            out[cfg_key] = _as_release(value, lang)
        else:
            out[cfg_key] = value
    return out


# --release means different things per language: a version string for Java,
# a boolean for Rust.
def _as_release(value, lang):
    if lang == "rust":
        return str(value).lower() not in ("", "0", "off", "false", "no")
    return value


def _run_lang_form(ctx, lang, existing):
    spec = _LANG_FORM.get(lang, [])
    # Global per-language defaults, if the user keeps any in their config.
    gdefaults = (ctx.global_config.get("languages", {}) or {}).get(lang, {})

    fields = []
    for key, label, kind, fallback in spec:
        default = existing.get(key, gdefaults.get(key, fallback))
        if kind == "choice" and key == "link":
            choices = [("gcc", "gcc"), ("ld", "ld")]
            fields.append(Field(key, label, "choice", choices=choices, default=default))
        elif kind == "bool":
            fields.append(Field(key, label, "bool", default=bool(default)))
        else:
            fields.append(Field(key, label, "text", default=default))

    result = run_form(ctx, f"Configure {lang}", fields)
    if result is None:
        return None
    # Drop empty optional text fields so we don't litter the config with "".
    return {k: v for k, v in result.items() if v not in ("", None)}


def complete(ctx, prev_words, word):
    # - after --link, suggest the two linkers
    if prev_words and prev_words[-1] == "--link":
        return [("gcc", "linker"), ("ld", "linker")]
    # - after --compare, suggest the comparison strategies
    if prev_words and prev_words[-1] == "--compare":
        return [(s, "strategy") for s in list_strategies()]
    # - otherwise suggest language names for the positional
    return [(lang, "language") for lang in list_languages()]
