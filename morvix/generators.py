# Test generation (Section 13).
#
# Generation can produce inputs, but the correct answer for an input must come
# from running a real program, never from thin air - and that program is the
# solution under test (a peer's own solution). These functions own that
# boundary: they make inputs fast, and they compute expected answers only by
# running the solution.
#
# Each function writes input files under tests/<group>/ and registers/updates
# TestCase entries on the project, then the caller saves the project. Generated
# cases are marked manual=False (disposable); gen_manual marks manual=True.

import os
import shutil
import tempfile

from morvix import (
    boundary,
    boundspec,
    catalog,
    combinatorial,
    enumerate_inputs,
    fuzz,
    grammar,
    inference,
    layout,
    metamorphic,
    multitest,
    mutate,
    process,
    properties,
    provenance,
    schema,
    shapes,
    shrink,
    suggestions,
)
from morvix.adapters import detect_language, get_adapter
from morvix.cases import TestCase, default_expected_relpath, default_input_relpath
from morvix.errors import MorvixError, UserError
from morvix.judge import _runspec, _signal_name, build_solution, select_cases
from morvix.models import ExecEnv, run_case
from morvix.project import resolve_limits

# A starter generator the user edits to match their program's input format.
GENERATOR_TEMPLATE = """#!/usr/bin/env python3
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
"""


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
        raise UserError(
            f"Generator already exists: {name}", hint="Pick another name, or edit the existing one."
        )
    _write_text(path, GENERATOR_TEMPLATE.format(name=name[:-3]))
    return rel


GRAMMAR_EXT = ".gram"


def new_grammar(ctx, project, name="gram"):
    """Write a starter grammar into generators/ and return its relative path."""
    if not name.endswith(GRAMMAR_EXT):
        name += GRAMMAR_EXT
    rel = os.path.join(layout.GENERATORS_DIR, name)
    path = project.abspath(rel)
    if os.path.exists(path):
        raise UserError(
            f"Grammar already exists: {name}", hint="Pick another name, or edit the existing one."
        )
    _write_text(path, grammar.STARTER_GRAMMAR.format(path=rel))
    return rel


def gen_from_grammar(ctx, project, grammar_path, count, seed, group, params=None):
    # Parse the grammar once, then sample one valid input per case. A grammar
    # asserts input shape only - answers still come from gen --expected.
    try:
        source = _read_bytes(grammar_path).decode("utf-8")
    except OSError as e:
        raise UserError(f"Grammar not found: {grammar_path}", hint="Check the path.") from e
    try:
        g = grammar.parse(source, grammar_path)
    except grammar.GrammarError as e:
        raise UserError(f"Grammar error in {os.path.basename(grammar_path)}", hint=str(e)) from e

    rel_gram = _generator_relpath(project, grammar_path)
    shash = provenance.hash_bytes(source.encode("utf-8"))
    base = os.path.basename(grammar_path)
    cases = []
    for i in range(count):
        try:
            text = grammar.sample(g, seed + i, params or {})
        except grammar.GrammarError as e:
            raise UserError("Grammar sampling failed", hint=str(e)) from e
        case = _emit_input_case(
            project,
            group,
            f"gram{seed}_{i}",
            text,
            "grammar",
            tags=[f"grammar:{base}"],
            seed=seed + i,
            grammar=rel_gram,
            source_hash=shash,
            params=params or None,
        )
        cases.append(case)
    return cases


def gen_catalog(ctx, project, name, count, seed, group, params=None):
    # Generate inputs from a vetted catalog generator (built on genlib). Inputs
    # only - answers still come from gen --expected.
    if name not in catalog.CATALOG:
        known = ", ".join(sorted(catalog.CATALOG))
        raise UserError(f"Unknown catalog generator '{name}'.", hint=f"Try one of: {known}")
    cases = []
    for i in range(count):
        text = catalog.generate(name, seed + i, params or {})
        cases.append(
            _emit_input_case(
                project,
                group,
                f"lib{seed}_{i}",
                text,
                "lib",
                tags=[f"lib:{name}"],
                seed=seed + i,
                lib=name,
                params=params or None,
            )
        )
    return cases


# Write one input-only case (no expected_*), stamping tags + provenance + hash.
def _emit_input_case(project, group, name, text, mode, tags=None, note=None, **prov):
    rel = default_input_relpath(group, name)
    _write_text(project.abspath(rel), text)
    case = TestCase(
        name=name,
        group=group,
        manual=False,
        inputs={"stdin": rel},
        tags=tags or [],
        note=note,
        provenance=provenance.make_record(mode, **prov),
    )
    _finalize_case(project, case)
    return case


def _read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _geometric_sizes(lo, hi, steps):
    """`steps` distinct sizes from lo to hi spaced geometrically."""
    lo = max(1, int(lo))
    hi = max(lo, int(hi))
    if steps <= 1:
        return [hi]
    out, seen = [], set()
    for i in range(steps):
        t = i / (steps - 1)
        v = max(lo, min(hi, int(round(lo * (hi / lo) ** t))))
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def gen_ladder(ctx, project, shape, seed, group, params, steps=8, lo_n=1, hi_n=100000):
    # One case per geometric size rung - read complexity off the timing column.
    sp = shapes.size_param(shape)
    cases = []
    for i, size in enumerate(_geometric_sizes(lo_n, hi_n, steps)):
        p = dict(params)
        if sp:
            p[sp] = size
        text = shapes.generate(shape, seed + i, p)
        cases.append(
            _emit_input_case(
                project,
                group,
                f"ladder{seed}_{size}",
                text,
                "ladder",
                tags=["ladder", f"random:{shape}"],
                seed=seed + i,
                shape=shape,
                params={sp: size} if sp else None,
            )
        )
    return cases


def gen_boundary(
    ctx, project, shape, seed, group, axes, strategy="one-at-a-time", cap=500, base=None
):
    # Enumerate boundary param-sets from declared axes (axis names are the
    # shape's own param names, e.g. count/lo/hi/rows), then generate one each.
    psets = boundary.boundary_param_sets(axes, strategy, shape, cap=cap)
    psets += boundary.structural_extremes(shape, axes)
    cases = []
    for i, pset in enumerate(psets[:cap]):
        p = dict(base or {})
        p.update(pset)
        text = shapes.generate(shape, seed + i, p)
        cases.append(
            _emit_input_case(
                project,
                group,
                f"bnd{seed}_{i}",
                text,
                "boundary",
                tags=["boundary", f"random:{shape}"],
                seed=seed + i,
                shape=shape,
                params=pset or None,
            )
        )
    return cases


def gen_exhaustive(ctx, project, shape, seed, group, max_n, values, cap=500):
    # Enumerate the whole small-input space for tiny bounds (guarded by cap).
    texts = enumerate_inputs.enumerate_for(shape, max_n, values, cap)
    cases = []
    for i, text in enumerate(texts):
        cases.append(
            _emit_input_case(
                project,
                group,
                f"ex{i}",
                text,
                "exhaustive",
                tags=["exhaustive", f"random:{shape}"],
                shape=shape,
            )
        )
    return cases


def gen_pairwise(ctx, project, shape, seed, group, axes, strength=2, cap=500, base=None):
    # A t-wise covering array over discrete axis levels: every pair (or t-tuple)
    # of levels appears in at least one generated case.
    import random as _random

    factors = {name: boundspec.factor_levels(dom) for name, dom in axes.items()}
    rows = combinatorial.covering_array(factors, strength, _random.Random(seed))
    cases = []
    for i, row in enumerate(rows[:cap]):
        p = dict(base or {})
        p.update(row)
        text = shapes.generate(shape, seed + i, p)
        cases.append(
            _emit_input_case(
                project,
                group,
                f"pw{seed}_{i}",
                text,
                "pairwise",
                tags=["pairwise", f"random:{shape}"],
                seed=seed + i,
                shape=shape,
                params=row or None,
            )
        )
    return cases


def gen_multi(
    ctx,
    project,
    shape,
    t,
    seed,
    group,
    params,
    layout_kind="t-first",
    from_group=None,
    auto_t=False,
):
    # Wrap T generated (or borrowed) sub-inputs into one multi-test file.
    pool = None
    if from_group:
        pool = [c for c in project.cases if c.group == from_group and c.primary_input()]
        if not pool:
            raise UserError(
                f"No inputs in group '{from_group}' to draw from.",
                hint="Generate that group first, or drop --from-group.",
            )

    def sub(idx):
        if pool:
            src = pool[idx % len(pool)]
            return _read_text(project.abspath(src.primary_input())).rstrip("\n")
        return shapes.generate(shape, seed + idx, params)

    sizes = multitest.auto_t_sizes(t) if auto_t else [t]
    cases = []
    for j, count in enumerate(sizes):
        subs = [sub(j * 100000 + k) for k in range(count)]
        text = multitest.wrap(subs, layout_kind)
        cases.append(
            _emit_input_case(
                project,
                group,
                f"multi{seed}_{count}",
                text,
                "multi",
                tags=["multi"],
                seed=seed,
                shape=shape,
            )
        )
    return cases


# Build a program (the solution, an oracle, ...) once and return a ready ExecEnv
# plus the temp workdir to clean up. Mirrors judge(): mkdtemp, build, runspec,
# ExecEnv. Stress/metamorphic/property/fuzz all reuse this to build once.
def _make_solution_env(project, solution, language, prefix="morvix-env-"):
    workdir = tempfile.mkdtemp(prefix=prefix)
    build = build_solution(project, solution, language, workdir)
    if not build.ok:
        shutil.rmtree(workdir, ignore_errors=True)
        raise MorvixError(build.error or "build failed", hint=build.diagnostics)
    runspec = _runspec(project, build, language)
    env = ExecEnv(project=project, build=build, runspec=runspec, workdir=workdir)
    return env, workdir


def _has_expectation(case):
    return any(
        getattr(case, k) is not None
        for k in ("expected_output", "expected_hash", "expected_exit", "expected_signal")
    )


# Compile a generator program once and return (produce, cleanup). produce(seed,
# modes) runs it and returns the printed input text, so a generator can drive
# many inputs (stress, etc.) without rebuilding per call.
def generator_source(project, generator_path):
    language = detect_language(generator_path)
    if not language:
        raise UserError(
            f"Could not detect the language of '{generator_path}'.",
            hint="Use a recognised extension (.py, .c, .cpp, .rs, ...).",
        )
    workdir = tempfile.mkdtemp(prefix="morvix-gen-")
    build = get_adapter(language).build(generator_path, project.lang_config(language), workdir)
    if not build.ok:
        shutil.rmtree(workdir, ignore_errors=True)
        raise MorvixError(build.error or "generator build failed", hint=build.diagnostics)
    spec = get_adapter(language).run_spec(build, project.lang_config(language))

    def produce(seed, modes=None):
        argv = spec.argv + [str(seed)] + list(modes or [])
        res = process.run(argv, cwd=workdir, env=process.base_env(project.locale, spec.env))
        return res.stdout.decode("utf-8", "replace")

    def cleanup():
        shutil.rmtree(workdir, ignore_errors=True)

    return produce, cleanup


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _generator_relpath(project, path):
    """A generator's path relative to the project root if it lives inside it."""
    ap = os.path.abspath(path)
    root = os.path.abspath(project.root)
    if ap.startswith(root + os.sep):
        return os.path.relpath(ap, root)
    return os.path.basename(ap)


# Stamp the input hash on a freshly written case and register it. Generators set
# inputs only - never an expected_* field (the honesty boundary lives here).
def _finalize_case(project, case):
    provenance.ensure_input_hash(project, case)
    project.add_case(case)
    return case


def gen_manual(ctx, project, name, group="baseline", content=None):
    rel = default_input_relpath(group, name)
    _write_text(project.abspath(rel), content or "")
    case = TestCase(
        name=name,
        group=group,
        manual=True,
        inputs={"stdin": rel},
        provenance=provenance.make_record("manual"),
    )
    _finalize_case(project, case)
    # When created empty in an interactive session, point the user at the file.
    if ctx.interactive and content is None:
        ctx.messenger.info(f"Edit the input at {rel}")
    return case


def gen_random(ctx, project, shape, count, seed, group, params):
    cases = []
    for i in range(count):
        text = shapes.generate(shape, seed + i, params)
        case = _emit_input_case(
            project,
            group,
            f"r{seed}_{i}",
            text,
            "random",
            tags=[f"random:{shape}"],
            seed=seed + i,
            shape=shape,
            params=params or None,
        )
        cases.append(case)
    return cases


def gen_from_generator(ctx, project, generator_path, count, seed, group, modes=None):
    # Build the generator once, then run it count times (argv [seed+i] + modes),
    # capturing stdout as one input per case.
    rel_gen = _generator_relpath(project, generator_path)
    ghash = provenance.hash_bytes(_read_bytes(generator_path))
    base = os.path.basename(generator_path)
    produce, cleanup = generator_source(project, generator_path)
    cases = []
    try:
        for i in range(count):
            text = produce(seed + i, modes)
            case = _emit_input_case(
                project,
                group,
                f"g{seed}_{i}",
                text,
                "generator",
                tags=[f"gen:{base}"],
                seed=seed + i,
                generator=rel_gen,
                generator_hash=ghash,
                modes=list(modes) if modes else None,
            )
            cases.append(case)
    finally:
        cleanup()
    return cases


def gen_expected(
    ctx,
    project,
    use_hash=False,
    groups=None,
    check_stable=False,
    repeat=3,
    changed_only=False,
    force_all=False,
):
    # Answers always come from the solution under test: build it once, run it
    # over each case, and freeze its observed behaviour as the expected answer.
    # Returns {"computed", "reused", "unstable"}.
    solution = project.solution
    if not solution:
        raise UserError(
            "No solution to compute expected answers from.",
            hint="Import one first with 'import <file>'.",
        )
    language = project.language or detect_language(solution)
    cases = select_cases(project, groups=groups) if groups else list(project.cases)
    fingerprint = provenance.solution_fingerprint(project)

    env, workdir = _make_solution_env(project, solution, language, prefix="morvix-ref-")
    computed = 0
    reused = 0
    unstable = []
    clean_outputs = []
    error_exits = []  # nonzero exit codes seen, to catch a "nothing ran" suite
    try:
        for case in cases:
            limits = resolve_limits(project, None, case)
            # Incremental: skip a case whose input and the solution are unchanged.
            if changed_only and not force_all and _has_expectation(case):
                cur = provenance.compute_input_hash(case, project.root)
                if (
                    cur == case.input_hash
                    and case.provenance.get("solution_fingerprint") == fingerprint
                ):
                    reused += 1
                    continue

            obs = run_case(project.model, case, env, limits)
            if check_stable and _varies(project, case, env, limits, obs, repeat):
                unstable.append(case.id)
                continue  # refuse to freeze a nondeterministic answer

            # Clear any stale expectation so re-running never leaves an impossible
            # combination (expected_output + expected_signal from two runs).
            case.expected_output = case.expected_hash = None
            case.expected_exit = case.expected_signal = None
            res = obs.result
            if res.timed_out:
                continue
            if res.signaled:
                case.expected_signal = _signal_name(res.term_signal)
            elif res.exit_code not in (0, None):
                case.expected_exit = res.exit_code
                error_exits.append(res.exit_code)
            else:
                clean_outputs.append(obs.output)
                if use_hash:
                    case.expected_hash = provenance.hash_bytes(obs.output)
                else:
                    rel = default_expected_relpath(case.group, case.name)
                    os.makedirs(os.path.dirname(project.abspath(rel)), exist_ok=True)
                    with open(project.abspath(rel), "wb") as f:
                        f.write(obs.output)
                    case.expected_output = rel
            # Record which solution froze this answer, so drift is detectable.
            case.provenance["solution_fingerprint"] = fingerprint
            provenance.ensure_input_hash(project, case)
            computed += 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    # If almost every answer is empty or identical, the inputs likely don't match
    # the program's format - tell the user (Section 22).
    suggestions.warn_degenerate_expected(ctx, clean_outputs)
    if unstable:
        suggestions.warn_unstable_answers(ctx, unstable)
    # Trust guard: if EVERY computed case errored with the same exit code and not
    # one produced output, the solution probably never really ran (wrong run
    # command, missing file, ...). Don't let that freeze as a green suite.
    if computed >= 2 and not clean_outputs and len(set(error_exits)) == 1:
        suggestions.warn_solution_not_running(ctx, computed, error_exits[0])
    return {"computed": computed, "reused": reused, "unstable": unstable}


def _varies(project, case, env, limits, first_obs, repeat):
    """Run the case a few more times; True if its observable behaviour changes."""
    for _ in range(max(repeat - 1, 0)):
        obs = run_case(project.model, case, env, limits)
        if (
            _normalise(obs.output) != _normalise(first_obs.output)
            or obs.result.exit_code != first_obs.result.exit_code
            or obs.result.signaled != first_obs.result.signaled
        ):
            return True
    return False


# Run a program on one input text via a throwaway case; return the Observation.
def _run_on_text(project, env, text, limits):
    in_rel = default_input_relpath("_tmp", "t")
    _write_text(project.abspath(in_rel), text)
    tmp = TestCase(name="t", group="_tmp", manual=False, inputs={"stdin": in_rel})
    try:
        return run_case(project.model, tmp, env, limits)
    finally:
        _unlink(project.abspath(in_rel))


def gen_stress(
    ctx,
    project,
    count,
    seed,
    group="regression",
    source=None,
    keep=8,
    do_shrink=True,
    shrink_budget=2000,
):
    # Pit the solution against a trusted oracle (a --stress rival) on generated
    # inputs; keep up to `keep` minimised disagreements as permanent regressions.
    # The oracle is the authority for the answer (its honesty carve-out).
    oracle = project.stress_rival()
    if not oracle:
        suggestions.explain_missing_stress_oracle(ctx, project)
        return []

    solution = project.solution
    if not solution:
        raise UserError("No solution under test to stress.", hint="Import one with 'import'.")

    sol_lang = project.language or detect_language(solution)
    bf_lang = detect_language(oracle.path) or project.language
    if source is None:
        source = lambda i: shapes.generate("ints", seed + i, {})  # noqa: E731

    sol_env, sol_wd = _make_solution_env(project, solution, sol_lang, prefix="morvix-stress-sol-")
    try:
        bf_env, bf_wd = _make_solution_env(
            project, oracle.path, bf_lang, prefix="morvix-stress-bf-"
        )
    except MorvixError:
        shutil.rmtree(sol_wd, ignore_errors=True)
        raise

    limits = resolve_limits(project, None, None)

    # Disagreement check: the oracle must give a usable answer (not crash/hang)
    # for the comparison to be trusted; returns the oracle's output or None.
    def disagreement(text):
        obs_bf = _run_on_text(project, bf_env, text, limits)
        if obs_bf.result.timed_out or obs_bf.result.signaled:
            return None
        obs_sol = _run_on_text(project, sol_env, text, limits)
        if _normalise(obs_sol.output) != _normalise(obs_bf.output):
            return obs_bf.output
        return None

    saved = []
    try:
        for i in range(count):
            if len(saved) >= keep:
                break
            text = source(i)
            ans = disagreement(text)
            if ans is None:
                continue
            if do_shrink:
                pred = lambda b: disagreement(b.decode("utf-8", "replace")) is not None  # noqa: E731
                text = shrink.shrink_failure(
                    pred, text.encode("utf-8"), budget=shrink_budget
                ).decode("utf-8", "replace")
                ans = disagreement(text)  # re-derive the oracle's answer for the shrunk input
                if ans is None:
                    continue
            saved.append(_save_regression(project, group, seed + i, text, ans))
    finally:
        shutil.rmtree(sol_wd, ignore_errors=True)
        shutil.rmtree(bf_wd, ignore_errors=True)
    return saved


def gen_shrink(ctx, project, case_id, budget=2000):
    # Minimise one already-failing case to a small reproducer. Handles a
    # crashing/hanging/erroring solution (re-derives the observed exit/signal),
    # and stress-style disagreements when a --stress oracle is registered.
    case = project.get_case(case_id)
    if case is None:
        raise UserError(f"No such case: {case_id}", hint="See 'status' for the groups and counts.")
    rel = case.primary_input()
    if not rel or not os.path.exists(project.abspath(rel)):
        raise UserError(f"Case {case_id} has no input file to shrink.")
    text = _read_text(project.abspath(rel))

    solution = project.solution
    if not solution:
        raise UserError("No solution under test.", hint="Import one with 'import'.")
    sol_lang = project.language or detect_language(solution)
    sol_env, sol_wd = _make_solution_env(project, solution, sol_lang, prefix="morvix-shrink-")
    limits = resolve_limits(project, None, case)
    try:
        obs = _run_on_text(project, sol_env, text, limits)
        kind = _crash_kind(obs)
        if kind:
            pred = lambda b: (
                _crash_kind(  # noqa: E731
                    _run_on_text(project, sol_env, b.decode("utf-8", "replace"), limits)
                )
                == kind
            )
            small = shrink.shrink_failure(pred, text.encode("utf-8"), budget=budget)
            _write_text(project.abspath(rel), small.decode("utf-8", "replace"))
            final = _run_on_text(project, sol_env, small.decode("utf-8", "replace"), limits)
            _set_observed_expectation(case, final)
            case.note = f"shrunk reproducer ({kind})"
            provenance.ensure_input_hash(project, case)
            return case
    finally:
        shutil.rmtree(sol_wd, ignore_errors=True)

    # Not a crash: fall back to the stress oracle for a disagreement reproducer.
    if project.stress_rival():
        return _shrink_against_oracle(ctx, project, case, text, budget)
    raise UserError(
        f"Case {case_id} doesn't currently crash the solution, so there's nothing to shrink here.",
        hint="Shrinking a wrong-answer case needs a trusted oracle: register one with "
        "'rival add <path> --stress'.",
    )


def _shrink_against_oracle(ctx, project, case, text, budget):
    oracle = project.stress_rival()
    sol_lang = project.language or detect_language(project.solution)
    bf_lang = detect_language(oracle.path) or project.language
    sol_env, sol_wd = _make_solution_env(
        project, project.solution, sol_lang, prefix="morvix-shr-s-"
    )
    try:
        bf_env, bf_wd = _make_solution_env(project, oracle.path, bf_lang, prefix="morvix-shr-o-")
    except MorvixError:
        shutil.rmtree(sol_wd, ignore_errors=True)
        raise
    limits = resolve_limits(project, None, case)

    def disagreement(t):
        obs_bf = _run_on_text(project, bf_env, t, limits)
        if obs_bf.result.timed_out or obs_bf.result.signaled:
            return None
        obs_sol = _run_on_text(project, sol_env, t, limits)
        return obs_bf.output if _normalise(obs_sol.output) != _normalise(obs_bf.output) else None

    try:
        if disagreement(text) is None:
            raise UserError(
                f"Case {case.id} no longer disagrees with the oracle - nothing to shrink."
            )
        pred = lambda b: disagreement(b.decode("utf-8", "replace")) is not None  # noqa: E731
        small = shrink.shrink_failure(pred, text.encode("utf-8"), budget=budget).decode(
            "utf-8", "replace"
        )
        ans = disagreement(small)
        rel = case.primary_input()
        _write_text(project.abspath(rel), small)
        exp_rel = default_expected_relpath(case.group, case.name)
        os.makedirs(os.path.dirname(project.abspath(exp_rel)), exist_ok=True)
        with open(project.abspath(exp_rel), "wb") as f:
            f.write(ans)
        case.expected_output = exp_rel
        case.expected_hash = case.expected_exit = case.expected_signal = None
        case.note = "shrunk reproducer (disagreement)"
        provenance.ensure_input_hash(project, case)
        return case
    finally:
        shutil.rmtree(sol_wd, ignore_errors=True)
        shutil.rmtree(bf_wd, ignore_errors=True)


def _crash_kind(obs):
    """Classify a misbehaving run: 'crash' (signal), 'hang' (timeout), 'error'
    (nonzero clean exit), or None if it ran cleanly."""
    res = obs.result
    if res.timed_out:
        return shrink.FailureKind.HANG
    if res.signaled:
        return shrink.FailureKind.CRASH
    if res.exit_code not in (0, None):
        return shrink.FailureKind.ERROR
    return None


def _set_observed_expectation(case, obs):
    """Record the solution's own observed misbehaviour as the expectation."""
    case.expected_output = case.expected_hash = case.expected_exit = case.expected_signal = None
    res = obs.result
    if res.signaled:
        case.expected_signal = _signal_name(res.term_signal)
    elif res.exit_code not in (0, None):
        case.expected_exit = res.exit_code


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
    case = TestCase(
        name=name,
        group=group,
        manual=True,
        inputs={"stdin": in_rel},
        expected_output=exp_rel,
        tags=["stress"],
        note="disagreement between the solution and the stress oracle",
        provenance=provenance.make_record("stress", seed=seed),
    )
    provenance.ensure_input_hash(project, case)
    project.add_case(case)
    return case


def gen_crash(
    ctx,
    project,
    count,
    seed,
    group="bad-input",
    keep_clean=False,
    do_shrink=True,
    shrink_budget=2000,
):
    # Mangle baseline inputs into malformed variants, RUN them through the
    # solution, and keep only those that actually crash/hang/error (unless
    # --keep-clean). Inputs only - no expected_* is set. Returns (kept, buckets).
    sources = [c for c in project.cases if c.group == "baseline" and c.primary_input()]
    seeds = []
    for c in sources[:count]:
        p = c.input_abspath(project.root)
        if p and os.path.exists(p):
            seeds.append(_read_text(p))
    while len(seeds) < count:
        seeds.append(shapes.generate("ints", seed + len(seeds), {}))

    kinds = ["truncated", "oversized", "wrong_type", "extra_whitespace"]
    variants = [
        (i, kinds[i % len(kinds)], _malform(seeds[i], kinds[i % len(kinds)])) for i in range(count)
    ]

    buckets = {}
    kept = []

    def emit(i, kind, text, ck):
        if ck:
            buckets[ck] = buckets.get(ck, 0) + 1
        tags = [f"crash:{kind}"] + ([f"crash-kind:{ck}"] if ck else [])
        return _emit_input_case(
            project,
            group,
            f"crash_{seed}_{i}_{kind}",
            text,
            "crash",
            tags=tags,
            seed=seed + i,
            detail=ck or None,
        )

    if not project.solution:
        # No solution to triage against: keep all malformed inputs (legacy behaviour).
        for i, kind, bad in variants:
            kept.append(emit(i, kind, bad, None))
        return kept, buckets

    sol_lang = project.language or detect_language(project.solution)
    sol_env, sol_wd = _make_solution_env(
        project, project.solution, sol_lang, prefix="morvix-crash-"
    )
    limits = resolve_limits(project, None, None)
    try:
        for i, kind, bad in variants:
            obs = _run_on_text(project, sol_env, bad, limits)
            ck = _crash_kind(obs)
            if ck is None and not keep_clean:
                continue
            text = bad
            if ck and do_shrink:
                pred = lambda b, k=ck: (  # noqa: E731
                    _crash_kind(
                        _run_on_text(project, sol_env, b.decode("utf-8", "replace"), limits)
                    )
                    == k
                )
                text = shrink.shrink_failure(
                    pred, bad.encode("utf-8"), budget=shrink_budget
                ).decode("utf-8", "replace")
                ck = _crash_kind(_run_on_text(project, sol_env, text, limits))
            kept.append(emit(i, kind, text, ck))
    finally:
        shutil.rmtree(sol_wd, ignore_errors=True)
    return kept, buckets


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


def _misbehaved(obs):
    return obs.result.timed_out or obs.result.signaled


def _isint(s):
    try:
        int(s)
        return True
    except ValueError:
        return False


# --- oracle-free bug finding: metamorphic, property, fuzz -------------------


def gen_metamorphic(ctx, project, relation_name, source, count, seed, group="metamorphic", keep=8):
    # Apply a relation's input transform and check the solution's two outputs
    # relate as they should. A violation (saved as an input) means the solution
    # is sensitive to something it shouldn't be - found with NO reference answer.
    rel = metamorphic.get_relation(relation_name)
    solution = project.solution
    if not solution:
        raise UserError("No solution under test.", hint="Import one with 'import'.")
    language = project.language or detect_language(solution)
    env, wd = _make_solution_env(project, solution, language, prefix="morvix-meta-")
    limits = resolve_limits(project, None, None)
    saved = []
    try:
        for i in range(count):
            if len(saved) >= keep:
                break
            base = source(i)
            follow = metamorphic.follow_input(rel, seed + i, base)
            if _normalise(base.encode("utf-8")) == _normalise(follow.encode("utf-8")):
                continue  # the transform was a no-op for this input
            o_base = _run_on_text(project, env, base, limits)
            o_follow = _run_on_text(project, env, follow, limits)
            if _misbehaved(o_base) or _misbehaved(o_follow):
                continue  # a run crashed/hung: inconclusive, never a violation
            verdict = metamorphic.check(o_base.output, o_follow.output)
            if verdict.holds is False:
                saved.append(
                    _emit_input_case(
                        project,
                        group,
                        f"meta{seed}_{i}",
                        base,
                        "metamorphic",
                        tags=[f"metamorphic:{relation_name}"],
                        note=f"{relation_name}: {verdict.detail}",
                        seed=seed + i,
                        relation=relation_name,
                        detail=verdict.detail,
                    )
                )
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    return saved


def _property_env(input_text, output_bytes):
    out = output_bytes.decode("utf-8", "replace")
    out_toks = out.split()
    in_toks = input_text.split()
    return {
        "out": out,
        "out_len": len(out_toks),
        "out_lines": len(out.splitlines()),
        "out_int": int(out_toks[0]) if out_toks and _isint(out_toks[0]) else None,
        "n": int(in_toks[0]) if in_toks and _isint(in_toks[0]) else None,
        "in_len": len(in_toks),
    }


def gen_property(ctx, project, expr, source, count, seed, group="property", keep=8):
    # Check a bound on one of the solution's outputs (e.g. out_int <= n). A
    # False result is a violation (saved); an unparseable output is skipped,
    # never a violation. The property never asserts a correct answer.
    prop = properties.compile_property(expr)
    solution = project.solution
    if not solution:
        raise UserError("No solution under test.", hint="Import one with 'import'.")
    language = project.language or detect_language(solution)
    env, wd = _make_solution_env(project, solution, language, prefix="morvix-prop-")
    limits = resolve_limits(project, None, None)
    saved = []
    try:
        for i in range(count):
            if len(saved) >= keep:
                break
            text = source(i)
            obs = _run_on_text(project, env, text, limits)
            if _misbehaved(obs):
                continue
            if prop.evaluate(_property_env(text, obs.output)) is False:
                saved.append(
                    _emit_input_case(
                        project,
                        group,
                        f"prop{seed}_{i}",
                        text,
                        "property",
                        tags=["property"],
                        note=f"property failed: {expr}",
                        seed=seed + i,
                        detail=expr,
                    )
                )
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    return saved


def gen_fuzz(ctx, project, seeds, budget, seed, group="fuzz", keep=8):
    # Diversity-guided fuzzing: mutate a corpus and keep inputs that make the
    # solution behave a NEW observable way (output shape, exit/signal, timing
    # regime). Behaviour buckets only steer the search; inputs only are saved.
    import random as _random

    solution = project.solution
    if not solution:
        raise UserError("No solution under test.", hint="Import one with 'import'.")
    language = project.language or detect_language(solution)
    env, wd = _make_solution_env(project, solution, language, prefix="morvix-fuzz-")
    limits = resolve_limits(project, None, None)
    limit_dict = {"wall": limits.get("wall"), "mem_kb": limits.get("mem_kb")}
    rng = _random.Random(seed)
    corpus = list(seeds) or [shapes.generate("ints", seed, {})]
    seen = set()
    saved = []
    try:
        # Establish the baseline behaviours so only genuinely new ones are kept.
        for base in corpus:
            seen.add(
                fuzz.behavior_key(_obs_dict(_run_on_text(project, env, base, limits)), limit_dict)
            )
        for i in range(budget):
            if len(saved) >= keep:
                break
            cand = mutate.mutate_once(rng, rng.choice(corpus), mutate.DEFAULT_OPS)
            obs = _run_on_text(project, env, cand, limits)
            key = fuzz.behavior_key(_obs_dict(obs), limit_dict)
            if fuzz.is_novel(key, seen):
                corpus.append(cand)
                saved.append(
                    _emit_input_case(
                        project,
                        group,
                        f"fuzz{seed}_{i}",
                        cand,
                        "fuzz",
                        tags=["fuzz"],
                        note="new observable behaviour",
                        seed=seed + i,
                    )
                )
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    return saved


def _obs_dict(obs):
    r = obs.result
    return {
        "output": obs.output,
        "exit": r.exit_code,
        "signal": _signal_name(r.term_signal) if r.signaled else None,
        "timed_out": r.timed_out,
        "wall": r.wall_time,
        "mem_kb": r.peak_mem_kb,
    }


# --- corpus mutation and format inference -----------------------------------


def gen_mutate(ctx, project, source_group, count, seed, group, schema_path=None, ops=None):
    corpus = [c for c in project.cases if c.group == source_group and c.primary_input()]
    if not corpus:
        raise UserError(
            f"No inputs in group '{source_group}' to mutate.",
            hint="Generate that group first, or pass --from <group>.",
        )
    import random as _random

    sch = schema.load_schema(schema_path) if schema_path else None
    cases = []
    for i in range(count):
        base = _read_text(project.abspath(corpus[i % len(corpus)].primary_input()))
        cand = mutate.mutate_once(_random.Random(seed + i), base, ops or mutate.DEFAULT_OPS, sch)
        cases.append(
            _emit_input_case(
                project, group, f"mut{seed}_{i}", cand, "mutate", tags=["mutate"], seed=seed + i
            )
        )
    return cases


def infer_and_draft(ctx, project, sample_paths, name="gen", as_grammar=False):
    # Read sample inputs, infer their format, and write a DRAFT generator (or
    # grammar) the user edits. Pure analysis: nothing is run, no answer computed.
    samples = [_read_text(p) for p in sample_paths]
    result = inference.infer_schema(samples)
    inference.report_inference(ctx, result)
    if as_grammar:
        gram = inference.try_write_grammar(result, name)
        if gram is not None:
            return write_inferred(project, name + GRAMMAR_EXT, gram, ext_ok=True)
        ctx.messenger.warning(
            "The shape was too irregular for a grammar; wrote a generator instead."
        )
    return write_inferred(project, name, inference.render_draft(result, name))


def gen_suggested_inputs(project, inputs, group="suggested", seed=1):
    # Materialise model-suggested INPUTS as inert cases (no expected_*); they
    # become real tests only once gen --expected runs the solution over them.
    cases = []
    for i, text in enumerate(inputs):
        cases.append(
            _emit_input_case(
                project,
                group,
                f"sugg{seed}_{i}",
                str(text),
                "suggested",
                tags=["suggested"],
                seed=seed + i,
            )
        )
    return cases


def write_inferred(project, name, source_text, ext_ok=False):
    if not ext_ok and not name.endswith(".py"):
        name += ".py"
    rel = os.path.join(layout.GENERATORS_DIR, name)
    path = project.abspath(rel)
    if os.path.exists(path):
        raise UserError(f"File already exists: {name}", hint="Pick another --name.")
    _write_text(path, source_text)
    return rel


def clean_one(project, case):
    """Delete one case's files and drop it from the project."""
    for rel in case.inputs.values():
        _unlink(project.abspath(rel))
    if case.expected_output:
        _unlink(project.abspath(case.expected_output))
    project.remove_case(case.id)


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
