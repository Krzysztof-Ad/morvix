# gen command: make test inputs and compute expected answers (Section 13).
#
# One mode per invocation (mutually exclusive):
#   --manual NAME    hand-written, permanent case
#   --random         random inputs from a built-in shape
#   --generator PROG run a custom generator program
#   --expected       (re)compute expected answers from the solution under test
#   --stress         pit the solution against the stress oracle, keep first failure
#   --crash          mangle inputs into malformed variants
#
# All mutating modes save the project afterwards and print a summary.

import glob
import os

from morvix import boundspec, distributions, generators, shapes, suggestions
from morvix.components.progress import progress_bar
from morvix.errors import UserError

NAME = "gen"

# Above this many random cases we show a progress bar.
LARGE_COUNT = 50


def configure(parser):
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--manual", metavar="NAME", help="create a permanent hand-written case named NAME"
    )
    mode.add_argument(
        "--random", action="store_true", help="generate random inputs from a built-in shape"
    )
    mode.add_argument(
        "--generator", metavar="PROG", help="run a custom generator program to produce inputs"
    )
    mode.add_argument(
        "--expected",
        action="store_true",
        help="(re)compute expected answers from the solution under test",
    )
    mode.add_argument(
        "--stress", action="store_true", help="stress the solution against a --stress rival oracle"
    )
    mode.add_argument(
        "--crash", action="store_true", help="generate malformed inputs to probe error handling"
    )
    mode.add_argument(
        "--new-generator",
        nargs="?",
        const="gen",
        metavar="NAME",
        help="write a starter generator you can edit (default name: gen)",
    )
    mode.add_argument(
        "--grammar",
        metavar="FILE",
        help="sample inputs from a declarative grammar file (correct-by-construction structure)",
    )
    mode.add_argument(
        "--new-grammar",
        nargs="?",
        const="gram",
        metavar="NAME",
        help="write a starter grammar you can edit (default name: gram)",
    )
    mode.add_argument(
        "--boundary",
        action="store_true",
        help="enumerate boundary cases (min/max/zero/...) from declared --axis ranges",
    )
    mode.add_argument(
        "--exhaustive",
        action="store_true",
        help="enumerate the WHOLE small-input space for tiny bounds (guarded by a cap)",
    )
    mode.add_argument(
        "--pairwise",
        action="store_true",
        help="t-wise covering array over discrete --axis factors (every pair covered)",
    )
    mode.add_argument(
        "--multi",
        type=int,
        metavar="T",
        help="wrap T generated inputs into one multi-test file with a T header",
    )
    mode.add_argument(
        "--ladder",
        action="store_true",
        help="emit one case per geometric size rung for empirical complexity profiling",
    )
    mode.add_argument(
        "--shrink",
        metavar="CASE",
        help="minimise a failing case to a small reproducer (input shrinks, answer re-derived)",
    )

    parser.add_argument(
        "--hash", action="store_true", help="with --expected: store output digests instead of files"
    )
    parser.add_argument(
        "--count", type=int, default=10, help="how many cases to generate (default 10)"
    )
    parser.add_argument("--seed", type=int, default=1, help="base random seed (default 1)")
    parser.add_argument("--group", help="target group (default depends on mode)")
    parser.add_argument(
        "--shape",
        default="ints",
        choices=shapes.list_shapes(),
        help="with --random: input shape (default ints)",
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="shape parameter, repeatable (e.g. --param lo=0)",
    )
    parser.add_argument(
        "--dist",
        default="uniform",
        help="value distribution: uniform, loguniform, zipf, gaussian, bimodal, clustered",
    )
    parser.add_argument(
        "--difficulty",
        help="difficulty dial easy|medium|hard|adversarial or 0..1; scales size and adversariality",
    )
    parser.add_argument(
        "--axis",
        action="append",
        default=[],
        metavar="NAME=SPEC",
        help="declare a bounded axis (e.g. --axis count=1..1e5 --axis hi=-1e9..1e9)",
    )
    parser.add_argument(
        "--matrix",
        default="one-at-a-time",
        choices=["one-at-a-time", "corners", "full"],
        help="with --boundary: how to combine multiple axes",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=500,
        help="cap on generated cases (boundary/exhaustive/pairwise)",
    )
    parser.add_argument(
        "--max-n",
        type=int,
        default=4,
        help="with --exhaustive: largest structure size to enumerate",
    )
    parser.add_argument(
        "--values", help="with --exhaustive: the value set each element draws from (e.g. 0,1,2)"
    )
    parser.add_argument(
        "--strength",
        type=int,
        default=2,
        help="with --pairwise: combination strength t (2=pairwise)",
    )
    parser.add_argument(
        "--steps", type=int, default=8, help="with --ladder: number of geometric size rungs"
    )
    parser.add_argument("--lo-n", type=int, default=1, help="with --ladder: smallest n rung")
    parser.add_argument("--hi-n", type=int, default=100000, help="with --ladder: largest n rung")
    parser.add_argument(
        "--layout-multi",
        default="t-first",
        choices=["t-first", "per-line"],
        help="with --multi: how to lay out sub-inputs",
    )
    parser.add_argument(
        "--from-group",
        help="with --multi: draw sub-inputs from an existing group instead of generating",
    )
    parser.add_argument(
        "--auto-t",
        action="store_true",
        help="with --multi: also emit T=1, small-T and max-T variants",
    )
    parser.add_argument(
        "--keep", type=int, default=8, help="with --stress: how many disagreements to keep"
    )
    parser.add_argument(
        "--no-shrink", action="store_true", help="skip automatic minimisation of a found failure"
    )
    parser.add_argument(
        "--shrink-budget", type=int, default=2000, help="max solution runs spent shrinking"
    )
    parser.add_argument(
        "--keep-clean",
        action="store_true",
        help="with --crash: keep even inputs the solution handled cleanly",
    )


# Parse repeated KEY=VALUE strings into a dict, coercing ints/floats.
def _parse_params(items):
    params = {}
    for item in items:
        if "=" not in item:
            raise UserError(
                f"Bad --param '{item}': expected KEY=VALUE.",
                hint="For example: --param lo=0 --param hi=100",
            )
        key, value = item.split("=", 1)
        params[key.strip()] = _coerce(value.strip())
    return params


def _coerce(value):
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def run(ctx, args) -> int:
    project = ctx.require_project()

    if args.manual is not None:
        return _do_manual(ctx, project, args)
    if args.random:
        return _do_random(ctx, project, args)
    if args.generator:
        return _do_generator(ctx, project, args)
    if args.expected:
        return _do_expected(ctx, project, args)
    if args.stress:
        return _do_stress(ctx, project, args)
    if args.crash:
        return _do_crash(ctx, project, args)
    if args.new_generator is not None:
        return _do_new_generator(ctx, project, args)
    if args.grammar:
        return _do_grammar(ctx, project, args)
    if args.new_grammar is not None:
        return _do_new_grammar(ctx, project, args)
    if args.boundary:
        return _do_boundary(ctx, project, args)
    if args.exhaustive:
        return _do_exhaustive(ctx, project, args)
    if args.pairwise:
        return _do_pairwise(ctx, project, args)
    if args.multi is not None:
        return _do_multi(ctx, project, args)
    if args.ladder:
        return _do_ladder(ctx, project, args)
    if args.shrink:
        return _do_shrink(ctx, project, args)

    raise UserError(
        "No generation mode given.",
        hint="Pick one of --manual, --random, --generator, --grammar, --boundary, "
        "--exhaustive, --pairwise, --multi, --ladder, --expected, --stress, --crash, "
        "--new-generator, --new-grammar.",
    )


def _do_manual(ctx, project, args):
    group = args.group or "baseline"
    case = generators.gen_manual(ctx, project, args.manual, group=group)
    ctx.save_project()
    ctx.messenger.success(f"Created manual case {case.id}.")
    return 0


# Fold --dist / --difficulty into the shape params, and return the (possibly
# retargeted) shape. Difficulty may crank a plain shape to its adversarial twin.
def _apply_dials(args, shape, params):
    if args.difficulty is not None:
        d = distributions.parse_difficulty(args.difficulty)
        dp = distributions.difficulty_params(shape, d)
        retarget = dp.pop("shape", None)
        for key, value in dp.items():
            params.setdefault(key, value)
        if retarget and retarget in shapes.list_shapes():
            shape = retarget
    if args.dist and args.dist != "uniform":
        params["dist"] = args.dist
    return shape, params


def _do_random(ctx, project, args):
    group = args.group or "baseline"
    params = _parse_params(args.param)
    shape, params = _apply_dials(args, args.shape, params)
    count = args.count

    # Show a progress bar only when there's enough work to be worth it.
    if count >= LARGE_COUNT:
        with progress_bar(ctx, count, "generating") as step:
            cases = generators.gen_random(ctx, project, shape, count, args.seed, group, params)
            step(count)
    else:
        cases = generators.gen_random(ctx, project, shape, count, args.seed, group, params)

    ctx.save_project()
    ctx.messenger.success(f"Generated {len(cases)} '{shape}' case(s) in group '{group}'.")
    ctx.messenger.info("Next: run 'gen --expected' to compute their answers.")
    return 0


def _parse_values(spec):
    if not spec:
        return [0, 1]
    return [_coerce(t.strip()) for t in spec.split(",")]


def _do_ladder(ctx, project, args):
    group = args.group or "ladder"
    _, params = _apply_dials(args, args.shape, _parse_params(args.param))
    cases = generators.gen_ladder(
        ctx,
        project,
        args.shape,
        args.seed,
        group,
        params,
        steps=args.steps,
        lo_n=args.lo_n,
        hi_n=args.hi_n,
    )
    ctx.save_project()
    ctx.messenger.success(f"Generated {len(cases)} ladder rung(s) in group '{group}'.")
    ctx.messenger.info(
        "Next: 'gen --expected', then 'run --group %s --time' to read complexity." % group
    )
    return 0


def _do_boundary(ctx, project, args):
    if not args.axis:
        raise UserError(
            "--boundary needs at least one --axis.",
            hint="e.g. gen --boundary --axis count=1..1000 --axis hi=-1000..1000 --shape ints",
        )
    group = args.group or "boundary"
    axes = boundspec.parse_specs(args.axis)
    cases = generators.gen_boundary(
        ctx,
        project,
        args.shape,
        args.seed,
        group,
        axes,
        strategy=args.matrix,
        cap=args.max_cases,
        base=_parse_params(args.param),
    )
    ctx.save_project()
    ctx.messenger.success(f"Generated {len(cases)} boundary case(s) in group '{group}'.")
    ctx.messenger.info("Next: run 'gen --expected' to compute their answers.")
    return 0


def _do_exhaustive(ctx, project, args):
    group = args.group or "exhaustive"
    cases = generators.gen_exhaustive(
        ctx,
        project,
        args.shape,
        args.seed,
        group,
        args.max_n,
        _parse_values(args.values),
        cap=args.max_cases,
    )
    ctx.save_project()
    ctx.messenger.success(f"Generated {len(cases)} exhaustive case(s) in group '{group}'.")
    if len(cases) >= args.max_cases:
        ctx.messenger.warning(
            f"Hit the cap of {args.max_cases}; not every input was enumerated.",
            hint="Raise --max-cases or lower --max-n.",
        )
    ctx.messenger.info("Next: run 'gen --expected' to compute their answers.")
    return 0


def _do_pairwise(ctx, project, args):
    if not args.axis:
        raise UserError(
            "--pairwise needs at least one --axis.",
            hint="e.g. gen --pairwise --axis layout=sorted,reverse --axis count=1,100,1000",
        )
    group = args.group or "pairwise"
    axes = boundspec.parse_specs(args.axis)
    cases = generators.gen_pairwise(
        ctx,
        project,
        args.shape,
        args.seed,
        group,
        axes,
        strength=args.strength,
        cap=args.max_cases,
        base=_parse_params(args.param),
    )
    ctx.save_project()
    ctx.messenger.success(f"Generated {len(cases)} pairwise case(s) in group '{group}'.")
    ctx.messenger.info("Next: run 'gen --expected' to compute their answers.")
    return 0


def _do_multi(ctx, project, args):
    group = args.group or "baseline"
    _, params = _apply_dials(args, args.shape, _parse_params(args.param))
    cases = generators.gen_multi(
        ctx,
        project,
        args.shape,
        args.multi,
        args.seed,
        group,
        params,
        layout_kind=args.layout_multi,
        from_group=args.from_group,
        auto_t=args.auto_t,
    )
    ctx.save_project()
    ctx.messenger.success(f"Generated {len(cases)} multi-test file(s) in group '{group}'.")
    ctx.messenger.info("Next: run 'gen --expected' to compute their answers.")
    return 0


def _do_generator(ctx, project, args):
    group = args.group or "baseline"
    path = os.path.abspath(args.generator)
    if not os.path.isfile(path):
        raise UserError(
            f"Generator not found: {args.generator}", hint="Check the path and try again."
        )
    cases = generators.gen_from_generator(ctx, project, path, args.count, args.seed, group)
    ctx.save_project()
    ctx.messenger.success(
        f"Generated {len(cases)} case(s) in group '{group}' from {os.path.basename(path)}."
    )
    ctx.messenger.info("Next: run 'gen --expected' to compute their answers.")
    return 0


def _do_expected(ctx, project, args):
    # Remember which cases already carried a crash expectation so we only flag
    # the ones gen_expected discovered this run.
    before = {
        c.id for c in project.cases if c.expected_exit is not None or c.expected_signal is not None
    }

    computed = generators.gen_expected(ctx, project, use_hash=args.hash)
    ctx.save_project()

    how = "hashes" if args.hash else "output files"
    ctx.messenger.success(f"Computed {computed} expected answer(s) ({how}).")

    # Cases that crashed under the solution now carry an exit/signal expectation.
    crashing = [
        c.id
        for c in project.cases
        if (c.expected_exit is not None or c.expected_signal is not None) and c.id not in before
    ]
    if crashing:
        suggestions.suggest_exit_status(ctx, project, crashing)
    return 0


def _do_stress(ctx, project, args):
    group = args.group or "regression"
    shape, params = _apply_dials(args, args.shape, _parse_params(args.param))
    source = lambda i: shapes.generate(shape, args.seed + i, params)  # noqa: E731
    cases = generators.gen_stress(
        ctx,
        project,
        args.count,
        args.seed,
        group=group,
        source=source,
        keep=args.keep,
        do_shrink=not args.no_shrink,
        shrink_budget=args.shrink_budget,
    )
    ctx.save_project()
    if not cases:
        ctx.messenger.success(f"No disagreement found in {args.count} trial(s).")
    else:
        ctx.messenger.warning(
            f"Found and saved {len(cases)} minimised disagreement(s) in group '{group}'.",
            hint="Inspect them, fix the solution, then rerun.",
        )
    return 0


def _do_crash(ctx, project, args):
    group = args.group or "bad-input"
    kept, buckets = generators.gen_crash(
        ctx,
        project,
        args.count,
        args.seed,
        group=group,
        keep_clean=args.keep_clean,
        do_shrink=not args.no_shrink,
        shrink_budget=args.shrink_budget,
    )
    ctx.save_project()
    if buckets:
        summary = ", ".join(f"{k}:{v}" for k, v in sorted(buckets.items()))
        ctx.messenger.warning(
            f"Kept {len(kept)} input(s) that misbehave ({summary}).",
            hint="These crash/hang/error the solution - check its input handling.",
        )
    elif kept:
        ctx.messenger.success(f"Generated {len(kept)} malformed input(s) in group '{group}'.")
    else:
        ctx.messenger.success(
            f"All {args.count} malformed inputs were handled cleanly - none kept."
        )
    return 0


def _do_shrink(ctx, project, args):
    case = generators.gen_shrink(ctx, project, args.shrink, budget=args.shrink_budget)
    ctx.save_project()
    if case is None:
        ctx.messenger.info("Nothing to shrink.")
        return 0
    size = len(_read_file(project.abspath(case.primary_input())))
    ctx.messenger.success(f"Shrunk {case.id} to a {size}-byte reproducer.")
    return 0


def _read_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _do_grammar(ctx, project, args):
    group = args.group or "baseline"
    path = os.path.abspath(args.grammar)
    if not os.path.isfile(path):
        raise UserError(f"Grammar not found: {args.grammar}", hint="Check the path and try again.")
    params = _parse_params(args.param)
    cases = generators.gen_from_grammar(ctx, project, path, args.count, args.seed, group, params)
    ctx.save_project()
    ctx.messenger.success(
        f"Generated {len(cases)} case(s) in group '{group}' from {os.path.basename(path)}."
    )
    ctx.messenger.info("Next: run 'gen --expected' to compute their answers.")
    return 0


def _do_new_grammar(ctx, project, args):
    rel = generators.new_grammar(ctx, project, args.new_grammar)
    ctx.messenger.success(f"Wrote a starter grammar: {rel}")
    ctx.messenger.info("Edit the rules to match your program's input, then run:")
    ctx.messenger.info(f"  gen --grammar {rel} --count 1000")
    ctx.messenger.info("  gen --expected")
    return 0


def _do_new_generator(ctx, project, args):
    rel = generators.new_generator(ctx, project, args.new_generator)
    ctx.messenger.success(f"Wrote a starter generator: {rel}")
    ctx.messenger.info("Edit build_input() to match your program's input, then run:")
    ctx.messenger.info(f"  gen --generator {rel} --count 1000")
    ctx.messenger.info("  gen --expected")
    return 0


def complete(ctx, prev_words, word):
    prev = prev_words[-1] if prev_words else ""

    # --shape: suggest the known shapes.
    if prev == "--shape":
        return [(s, "shape") for s in shapes.list_shapes() if s.startswith(word or "")]

    # --generator / --grammar: suggest filesystem paths.
    if prev in ("--generator", "--grammar"):
        return _path_completions(word)

    # --manual takes a free-form name; nothing useful to suggest.
    return []


def _path_completions(word):
    pattern = (word or ".") + "*"
    results = []
    for m in sorted(glob.glob(os.path.expanduser(pattern))):
        if os.path.isdir(m):
            results.append((m + "/", "dir"))
        else:
            label = os.path.splitext(m)[1].lstrip(".") or "file"
            results.append((m, label))
    return results
