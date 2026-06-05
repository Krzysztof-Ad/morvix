# Test generation (Section 13).
#
# Generation can produce inputs, but the correct answer for an input must come
# from the reference solution, never from thin air - and that reference is a
# peer's own solution. These functions own that boundary: they make inputs fast,
# and they compute expected answers only by running the reference.
#
# Each function writes input files under tests/<group>/ and registers/updates
# TestCase entries on the project, then the caller saves the project. Generated
# cases are marked manual=False (disposable); gen_manual marks manual=True.
#
# API (implement in Workflow B):
#   gen_manual(ctx, project, name, group="baseline", content=None) -> TestCase
#   gen_random(ctx, project, shape, count, seed, group, params) -> list[TestCase]
#   gen_from_generator(ctx, project, generator_path, count, seed, group, modes=None) -> list[TestCase]
#   gen_expected(ctx, project, use_hash=False, groups=None) -> int   # number of answers computed
#   gen_stress(ctx, project, count, seed, group="regression") -> TestCase | None  # first failing case
#   gen_crash(ctx, project, count, seed, group="bad-input") -> list[TestCase]
#   clean_generated(project, group=None) -> int   # remove generated cases + files; return count

import hashlib
import os
import tempfile

from morvix import layout, process, shapes, suggestions
from morvix.adapters import detect_language, get_adapter
from morvix.cases import TestCase, default_expected_relpath, default_input_relpath
from morvix.errors import UserError
from morvix.judge import build_solution, _runspec, select_cases, _signal_name
from morvix.models import ExecEnv, run_case
from morvix.project import resolve_limits


# A starter generator the user edits to match their program's input format.
GENERATOR_TEMPLATE = '''#!/usr/bin/env python3
# A Morvix generator: print ONE test input to stdout, parameterized by a seed.
#
# Morvix runs this once per case as:  python3 <thisfile> <seed> [mode]
# Use the seed so generation is reproducible. EDIT build_input() so what it
# prints matches EXACTLY what your program reads.
#
# Then:  gen --generator generators/{name}.py --count 1000
#        gen --expected           # compute the answers from your reference

import random
import sys


def build_input(rng):
    # TODO: replace this with your program's real input format.
    # Example below: a count n, then n integers on the next line.
    n = rng.randint(1, 100)
    nums = [rng.randint(0, 1000000) for _ in range(n)]
    return "%d\\n%s\\n" % (n, " ".join(str(x) for x in nums))


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    rng = random.Random(seed)
    sys.stdout.write(build_input(rng))


if __name__ == "__main__":
    main()
'''


# Write text to an absolute path, creating parent dirs first.
def _write_text(abspath, text):
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with open(abspath, "w", encoding="utf-8") as f:
        f.write(text)


def new_generator(ctx, project, name="gen"):
    """Write a starter generator into generators/ and return its relative path."""
    if not name.endswith(".py"):
        name += ".py"
    rel = os.path.join(layout.GENERATORS_DIR, name)
    path = project.abspath(rel)
    if os.path.exists(path):
        raise UserError(f"Generator already exists: {name}",
                        hint="Pick another name, or edit the existing one.")
    _write_text(path, GENERATOR_TEMPLATE.format(name=name[:-3]))
    return rel


# Build the reference/brute once, then run every case through it.
# Mirrors judge(): mkdtemp workdir, build, runspec, ExecEnv, run_case per case.
def _run_reference_over(project, solution, language, cases):
    workdir = tempfile.mkdtemp(prefix="morvix-ref-")
    observations = {}
    try:
        build = build_solution(project, solution, language, workdir)
        if not build.ok:
            from morvix.errors import MorvixError
            raise MorvixError(build.error or "build failed", hint=build.diagnostics)
        runspec = _runspec(project, build, language)
        env = ExecEnv(project=project, build=build, runspec=runspec, workdir=workdir)
        for case in cases:
            limits = resolve_limits(project, None, case)
            observations[case.id] = run_case(project.model, case, env, limits)
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
    return observations


def gen_manual(ctx, project, name, group="baseline", content=None):
    rel = default_input_relpath(group, name)
    _write_text(project.abspath(rel), content or "")
    case = TestCase(name=name, group=group, manual=True, inputs={"stdin": rel})
    project.add_case(case)
    # When created empty in an interactive session, point the user at the file.
    if ctx.interactive and content is None:
        ctx.messenger.info(f"Edit the input at {rel}")
    return case


def gen_random(ctx, project, shape, count, seed, group, params):
    cases = []
    for i in range(count):
        text = shapes.generate(shape, seed + i, params)
        name = f"r{seed}_{i}"
        rel = default_input_relpath(group, name)
        _write_text(project.abspath(rel), text)
        case = TestCase(name=name, group=group, manual=False, inputs={"stdin": rel})
        project.add_case(case)
        cases.append(case)
    return cases


def gen_from_generator(ctx, project, generator_path, count, seed, group, modes=None):
    # - build the generator with its own adapter
    # - run it count times, each with argv [seed+i] + modes, capturing stdout
    language = detect_language(generator_path)
    if not language:
        raise UserError(f"Could not detect the language of '{generator_path}'.",
                        hint="Use a recognised extension (.py, .c, .cpp, .rs, ...).")
    workdir = tempfile.mkdtemp(prefix="morvix-gen-")
    cases = []
    try:
        build = get_adapter(language).build(generator_path, project.lang_config(language), workdir)
        if not build.ok:
            from morvix.errors import MorvixError
            raise MorvixError(build.error or "generator build failed", hint=build.diagnostics)
        spec = get_adapter(language).run_spec(build, project.lang_config(language))
        for i in range(count):
            argv = spec.argv + [str(seed + i)] + list(modes or [])
            res = process.run(argv, cwd=workdir,
                              env=process.base_env(project.locale, spec.env))
            name = f"g{seed}_{i}"
            rel = default_input_relpath(group, name)
            _write_text(project.abspath(rel), res.stdout.decode("utf-8", "replace"))
            case = TestCase(name=name, group=group, manual=False, inputs={"stdin": rel})
            project.add_case(case)
            cases.append(case)
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
    return cases


def gen_expected(ctx, project, use_hash=False, groups=None):
    # The trusted source of answers is the reference (falling back to the solution).
    reference = project.reference or project.solution
    if not reference:
        raise UserError("No reference or solution to compute expected answers from.",
                        hint="Set one with 'solution' or 'reference'.")
    language = project.language or detect_language(reference)

    cases = select_cases(project, groups=groups) if groups else list(project.cases)
    observations = _run_reference_over(project, reference, language, cases)

    computed = 0
    clean_outputs = []   # captured answers from clean runs, to sanity-check below
    for case in cases:
        # Clear any stale expectation so re-running never leaves an impossible
        # combination (e.g. expected_output + expected_signal from two separate runs).
        case.expected_output = None
        case.expected_hash = None
        case.expected_exit = None
        case.expected_signal = None

        obs = observations.get(case.id)
        if obs is None:
            continue
        res = obs.result
        if res.timed_out:
            continue
        if res.signaled:
            # Reference crashed: record the signal as the expectation, not an answer.
            case.expected_signal = _signal_name(res.term_signal)
        elif res.exit_code not in (0, None):
            # Nonzero clean exit: that exit code becomes the expectation.
            case.expected_exit = res.exit_code
        else:
            # Clean run: the captured stdout is the answer.
            clean_outputs.append(obs.output)
            if use_hash:
                # Store only the digest, never the full output.
                case.expected_hash = hashlib.sha256(obs.output).hexdigest()
            else:
                rel = default_expected_relpath(case.group, case.name)
                os.makedirs(os.path.dirname(project.abspath(rel)), exist_ok=True)
                with open(project.abspath(rel), "wb") as f:
                    f.write(obs.output)
                case.expected_output = rel
        computed += 1
    # If almost every answer is empty or they are all identical, the inputs
    # probably don't match the program's format - tell the user (Section 22).
    suggestions.warn_degenerate_expected(ctx, clean_outputs)
    return computed


def gen_stress(ctx, project, count, seed, group="regression"):
    # Stress testing pits the solution against a trusted brute force on random
    # inputs and keeps the first input where they disagree.
    if not project.bruteforce:
        suggestions.explain_missing_bruteforce(ctx, project)
        return None

    solution = project.solution
    if not solution:
        raise UserError("No solution under test to stress.",
                        hint="Set one with 'solution'.")

    sol_lang = project.language or detect_language(solution)
    bf_lang = detect_language(project.bruteforce) or project.language

    shape = "ints"  # a sensible default unless the project says otherwise

    # Build both programs once before the loop (mirrors _run_reference_over).
    import shutil
    sol_workdir = tempfile.mkdtemp(prefix="morvix-stress-sol-")
    bf_workdir = tempfile.mkdtemp(prefix="morvix-stress-bf-")
    try:
        sol_build = build_solution(project, solution, sol_lang, sol_workdir)
        if not sol_build.ok:
            from morvix.errors import MorvixError
            raise MorvixError(sol_build.error or "build failed", hint=sol_build.diagnostics)
        sol_runspec = _runspec(project, sol_build, sol_lang)
        sol_env = ExecEnv(project=project, build=sol_build, runspec=sol_runspec, workdir=sol_workdir)

        bf_build = build_solution(project, project.bruteforce, bf_lang, bf_workdir)
        if not bf_build.ok:
            from morvix.errors import MorvixError
            raise MorvixError(bf_build.error or "build failed", hint=bf_build.diagnostics)
        bf_runspec = _runspec(project, bf_build, bf_lang)
        bf_env = ExecEnv(project=project, build=bf_build, runspec=bf_runspec, workdir=bf_workdir)

        limits = resolve_limits(project, None, None)

        for i in range(count):
            text = shapes.generate(shape, seed + i, {})
            # Write input to a temporary case so run_case can feed it as stdin.
            in_rel = default_input_relpath("_stress_tmp", f"{seed}_{i}")
            _write_text(project.abspath(in_rel), text)
            tmp_case = TestCase(name=f"{seed}_{i}", group="_stress_tmp",
                                manual=False, inputs={"stdin": in_rel})
            try:
                obs_sol = run_case(project.model, tmp_case, sol_env, limits)
                obs_bf = run_case(project.model, tmp_case, bf_env, limits)
            finally:
                _unlink(project.abspath(in_rel))
            if _normalise(obs_sol.output) != _normalise(obs_bf.output):
                # First disagreement: persist it as a permanent regression case,
                # trusting the brute force for the expected answer.
                return _save_regression(project, group, seed + i, text, obs_bf.output)
    finally:
        shutil.rmtree(sol_workdir, ignore_errors=True)
        shutil.rmtree(bf_workdir, ignore_errors=True)
    return None


def _normalise(data):
    """Whitespace-normalise output bytes: collapse runs of whitespace, ignore trailing."""
    return b" ".join(data.split())


def _save_regression(project, group, seed, text, expected_bytes):
    name = f"stress_{seed}"
    in_rel = default_input_relpath(group, name)
    _write_text(project.abspath(in_rel), text)
    exp_rel = default_expected_relpath(group, name)
    os.makedirs(os.path.dirname(project.abspath(exp_rel)), exist_ok=True)
    with open(project.abspath(exp_rel), "wb") as f:
        f.write(expected_bytes)
    case = TestCase(name=name, group=group, manual=True,
                    inputs={"stdin": in_rel}, expected_output=exp_rel)
    project.add_case(case)
    return case


def gen_crash(ctx, project, count, seed, group="bad-input"):
    # Take existing baseline inputs (or generate some) and mangle them into
    # malformed variants that probe input handling. No expected answers here.
    sources = [c for c in project.cases if c.group == "baseline" and c.primary_input()]
    seeds = []
    if sources:
        for c in sources[:count]:
            p = c.input_abspath(project.root)
            if p and os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    seeds.append(f.read())
    while len(seeds) < count:
        seeds.append(shapes.generate("ints", seed + len(seeds), {}))

    # - one malformation per variant, cycling through the kinds
    kinds = ["truncated", "oversized", "wrong_type", "extra_whitespace"]
    cases = []
    for i in range(count):
        base = seeds[i]
        kind = kinds[i % len(kinds)]
        bad = _malform(base, kind)
        name = f"crash_{seed}_{i}_{kind}"
        rel = default_input_relpath(group, name)
        _write_text(project.abspath(rel), bad)
        case = TestCase(name=name, group=group, manual=False, inputs={"stdin": rel})
        project.add_case(case)
        cases.append(case)
    return cases


def _malform(text, kind):
    if kind == "truncated":
        # keep only the first half of the bytes
        return text[: max(1, len(text) // 2)]
    if kind == "oversized":
        # repeat the input many times to blow past expected sizes
        return (text + "\n") * 1000
    if kind == "wrong_type":
        # replace the first whitespace-separated token with a non-numeric one
        parts = text.split(None, 1)
        rest = parts[1] if len(parts) > 1 else ""
        return ("not_a_number " + rest).strip() + "\n"
    if kind == "extra_whitespace":
        # pad every token with surplus spaces and blank lines
        return "\n\n".join("   " + line + "   " for line in text.split("\n")) + "\n"
    return text


def clean_generated(project, group=None):
    # Remove every generated (manual=False) case, optionally only in one group,
    # deleting its input file(s) and any expected file. Manual cases survive.
    removed = 0
    survivors = []
    for case in project.cases:
        if case.manual or (group is not None and case.group != group):
            survivors.append(case)
            continue
        for rel in case.inputs.values():
            _unlink(project.abspath(rel))
        if case.expected_output:
            _unlink(project.abspath(case.expected_output))
        removed += 1
    project.cases = survivors
    return removed


def _unlink(path):
    try:
        os.remove(path)
    except OSError:
        pass
