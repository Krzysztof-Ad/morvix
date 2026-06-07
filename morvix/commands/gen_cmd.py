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

from morvix import (
    assist,
    boundspec,
    catalog,
    distributions,
    generators,
    hygiene,
    importers,
    metamorphic,
    pack,
    shapes,
    snapshots,
    suggestions,
    validators,
)
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
    mode.add_argument(
        "--validate",
        nargs="?",
        const="",
        metavar="PROG",
        help="check generated inputs are well-formed with a validator (default: saved validator)",
    )
    mode.add_argument(
        "--new-validator",
        nargs="?",
        const="validate",
        metavar="NAME",
        help="write a starter input validator you can edit (default name: validate)",
    )
    mode.add_argument(
        "--pin",
        nargs="?",
        const="snapshot",
        metavar="NAME",
        help="save a named snapshot of current inputs+expected so later drift can be detected",
    )
    mode.add_argument(
        "--diff-pin",
        metavar="NAME",
        help="show which inputs or expected answers changed since NAME",
    )
    mode.add_argument(
        "--list-snapshots", action="store_true", help="list saved snapshots (see gen --pin)"
    )
    mode.add_argument(
        "--lib",
        metavar="NAME",
        help="generate inputs from a vetted catalog generator (see --list-lib)",
    )
    mode.add_argument(
        "--list-lib", action="store_true", help="list the catalog of vetted generators"
    )
    mode.add_argument(
        "--export-pack",
        metavar="FILE",
        help="bundle this project's generators/grammars into a pack",
    )
    mode.add_argument(
        "--import-pack",
        metavar="FILE",
        help="import generators/grammars from a pack (no code is run)",
    )
    mode.add_argument(
        "--metamorphic",
        action="store_true",
        help="check a metamorphic relation between the solution's outputs (needs --relation)",
    )
    mode.add_argument(
        "--property",
        metavar="EXPR",
        help="check a property of the solution's output, e.g. 'out_int <= n'",
    )
    mode.add_argument(
        "--fuzz",
        action="store_true",
        help="diversity-guided fuzz: keep inputs that make the solution behave a new way",
    )
    mode.add_argument(
        "--mutate", action="store_true", help="mutate existing inputs into new candidates"
    )
    mode.add_argument(
        "--infer",
        nargs="+",
        metavar="SAMPLE",
        help="infer the input format from sample files and draft a generator you edit",
    )
    mode.add_argument(
        "--import",
        dest="import_path",
        metavar="PATH",
        help="import existing input files (dir, glob, or .zip) as cases; bundled answers are stripped",
    )
    mode.add_argument(
        "--suggest",
        nargs="?",
        const="scaffold",
        metavar="KIND",
        help="OFF BY DEFAULT, network-gated: ask your --hook to draft a generator or inputs",
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
        "--content", help="with --manual: the case's input text (or pipe it on stdin)"
    )
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
    parser.add_argument(
        "--check-stable",
        action="store_true",
        help="with --expected: run each case several times and refuse to freeze a varying answer",
    )
    parser.add_argument(
        "--repeat", type=int, default=3, help="with --check-stable: how many runs per case"
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="with --expected: only recompute cases whose input or the solution changed",
    )
    parser.add_argument(
        "--all", action="store_true", help="with --expected --changed: force a full recompute"
    )
    parser.add_argument(
        "--require-valid",
        action="store_true",
        help="with --random/--generator/--grammar: drop inputs the validator rejects",
    )
    parser.add_argument(
        "--dedup",
        action="store_true",
        help="skip byte-identical inputs; with no mode, prune existing duplicate generated cases",
    )
    parser.add_argument(
        "--with-catalog",
        action="store_true",
        help="with --export-pack: also record the catalog generator names used",
    )
    parser.add_argument(
        "--force", action="store_true", help="with --import-pack: overwrite existing files"
    )
    parser.add_argument("--relation", help="with --metamorphic: the relation to check")
    parser.add_argument(
        "--ladder-spec", help="with --property: vary one size param, e.g. n=1..100000:8"
    )
    parser.add_argument(
        "--budget", type=int, default=500, help="with --fuzz: how many inputs to try"
    )
    parser.add_argument("--seed-group", help="with --fuzz: corpus seed group (default: baseline)")
    parser.add_argument(
        "--from",
        dest="mutate_from",
        help="with --mutate: source group of inputs (default baseline)",
    )
    parser.add_argument("--schema", help="with --mutate: a schema (from gen --infer) for edits")
    parser.add_argument("--ops", help="with --mutate: comma-separated mutation operators")
    parser.add_argument(
        "--split", action="store_true", help="with --import: split multi-test files"
    )
    parser.add_argument(
        "--keep-answers",
        action="store_true",
        help="with --import: keep bundled .out/.ans as ADVISORY only (never expected answers)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="with --import: preview without writing anything"
    )
    parser.add_argument("--name", help="name for a drafted generator/grammar (infer/suggest)")
    parser.add_argument(
        "--as-grammar", action="store_true", help="with --infer: also try writing a grammar draft"
    )
    parser.add_argument("--hook", help="with --suggest: path to YOUR executable model hook")
    parser.add_argument("--prompt", help="with --suggest: free-text guidance for the hook")
    parser.add_argument(
        "--i-understand",
        action="store_true",
        help="with --suggest: confirm model output is unverified, INPUT-only",
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
    if args.validate is not None:
        return _do_validate(ctx, project, args)
    if args.new_validator is not None:
        return _do_new_validator(ctx, project, args)
    if args.pin is not None:
        return _do_pin(ctx, project, args)
    if args.diff_pin:
        return _do_diff_pin(ctx, project, args)
    if args.list_snapshots:
        return _do_list_snapshots(ctx, project, args)
    if args.lib:
        return _do_lib(ctx, project, args)
    if args.list_lib:
        return _do_list_lib(ctx, project, args)
    if args.export_pack:
        return _do_export_pack(ctx, project, args)
    if args.import_pack:
        return _do_import_pack(ctx, project, args)
    if args.metamorphic:
        return _do_metamorphic(ctx, project, args)
    if args.property:
        return _do_property(ctx, project, args)
    if args.fuzz:
        return _do_fuzz(ctx, project, args)
    if args.mutate:
        return _do_mutate(ctx, project, args)
    if args.infer:
        return _do_infer(ctx, project, args)
    if args.import_path:
        return _do_import(ctx, project, args)
    if args.suggest is not None:
        return _do_suggest(ctx, project, args)
    if args.dedup:  # no generating mode: prune existing duplicate generated cases
        return _do_dedup(ctx, project, args)

    raise UserError(
        "No generation mode given.",
        hint="Pick one of --manual, --random, --generator, --grammar, --boundary, "
        "--exhaustive, --pairwise, --multi, --ladder, --expected, --stress, --crash, "
        "--shrink, --validate, --pin, --new-generator, --new-grammar.",
    )


def _do_manual(ctx, project, args):
    group = args.group or "baseline"
    content = args.content
    # In one-shot use, accept input piped on stdin so `printf ... | gen --manual x`
    # works instead of silently creating an empty case. Reading stdin can fail when
    # it is a terminal or captured (e.g. under a test runner); fall back to empty.
    if content is None and not ctx.interactive:
        import sys

        try:
            if not sys.stdin.isatty():
                piped = sys.stdin.read()
                content = piped if piped else None
        except (OSError, ValueError):
            content = None
    case = generators.gen_manual(ctx, project, args.manual, group=group, content=content)
    ctx.save_project()
    ctx.messenger.success(f"Created manual case {case.id}.")
    if content is None and not ctx.interactive:
        ctx.messenger.warning(
            "The case input is empty.",
            hint="Pass --content, pipe it in (printf ... | gen --manual NAME), or edit the file.",
        )
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

    _post_generate(ctx, project, args, group)
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
    _post_generate(ctx, project, args, group)
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

    result = generators.gen_expected(
        ctx,
        project,
        use_hash=args.hash,
        check_stable=args.check_stable,
        repeat=args.repeat,
        changed_only=args.changed,
        force_all=args.all,
    )
    ctx.save_project()

    how = "hashes" if args.hash else "output files"
    msg = f"Computed {result['computed']} expected answer(s) ({how})."
    if result["reused"]:
        msg += f" Reused {result['reused']} unchanged."
    ctx.messenger.success(msg)

    # Cases that crashed under the solution now carry an exit/signal expectation.
    crashing = [
        c.id
        for c in project.cases
        if (c.expected_exit is not None or c.expected_signal is not None) and c.id not in before
    ]
    if crashing:
        suggestions.suggest_exit_status(ctx, project, crashing)
    return 0


# --- integrity: validator, snapshots, dedup --------------------------------


def _do_validate(ctx, project, args):
    explicit = args.validate or None
    path = validators.resolve_validator(project, explicit)
    cases = [c for c in project.cases if c.primary_input()]
    results = validators.validate_cases(project, cases, path)
    bad = [r for r in results if not r.valid and not r.degraded]
    degraded = [r for r in results if r.degraded]
    if degraded and len(degraded) == len(results):
        ctx.messenger.warning(
            "Could not run the validator.", hint=degraded[0].message or "Check the toolchain."
        )
        return 0
    if bad:
        ids = ", ".join(r.case_id for r in bad[:8])
        ctx.messenger.warning(f"{len(bad)} input(s) failed validation: {ids}", hint="Inspect them.")
    else:
        ctx.messenger.success(f"All {len(results)} input(s) are well-formed.")
    return 0


def _do_new_validator(ctx, project, args):
    rel = validators.new_validator(ctx, project, args.new_validator)
    project.validator = rel
    ctx.save_project()
    ctx.messenger.success(f"Wrote a starter validator: {rel}")
    ctx.messenger.info("Edit it to check your input format, then: gen --validate")
    return 0


def _do_pin(ctx, project, args):
    path = snapshots.pin(project, args.pin)
    ctx.messenger.success(f"Pinned snapshot '{args.pin}' ({os.path.basename(path)}).")
    ctx.messenger.info("Later: gen --diff-pin %s to see what drifted." % args.pin)
    return 0


def _do_diff_pin(ctx, project, args):
    d = snapshots.diff(project, args.diff_pin)
    if not d.drifted:
        ctx.messenger.success(f"Nothing changed since snapshot '{args.diff_pin}'.")
        return 0
    if d.solution_changed:
        ctx.messenger.warning("The solution changed - frozen answers may be stale.")
    for label, ids in (
        ("inputs changed", d.inputs_changed),
        ("expected answers changed", d.expected_changed),
        ("added", d.added),
        ("removed", d.removed),
    ):
        if ids:
            ctx.messenger.info(f"{label}: {', '.join(ids[:10])}")
    return 0


def _do_list_snapshots(ctx, project, args):
    names = snapshots.list_snapshots(project)
    if not names:
        ctx.messenger.info("No snapshots yet. Create one with: gen --pin <name>")
    else:
        for n in names:
            ctx.messenger.info(n)
    return 0


def _do_dedup(ctx, project, args):
    removed = hygiene.dedup_pool(project)
    ctx.save_project()
    ctx.messenger.success(f"Removed {removed} duplicate generated case(s).")
    return 0


# --- catalog & packs -------------------------------------------------------


def _do_lib(ctx, project, args):
    group = args.group or "baseline"
    params = _parse_params(args.param)
    cases = generators.gen_catalog(ctx, project, args.lib, args.count, args.seed, group, params)
    _post_generate(ctx, project, args, group)
    ctx.save_project()
    ctx.messenger.success(f"Generated {len(cases)} case(s) from catalog '{args.lib}'.")
    ctx.messenger.info("Next: run 'gen --expected' to compute their answers.")
    return 0


def _do_list_lib(ctx, project, args):
    entries = catalog.list_entries()
    if not entries:
        ctx.messenger.info("The catalog is empty.")
        return 0
    for entry in entries:
        ctx.messenger.info(catalog.describe(entry.name))
    return 0


def _do_export_pack(ctx, project, args):
    out = pack.export_pack(project, args.export_pack, with_catalog=args.with_catalog)
    ctx.messenger.success(f"Exported generator pack to {os.path.basename(out)}.")
    return 0


def _do_import_pack(ctx, project, args):
    report = pack.import_pack(project, args.import_pack, force=args.force)
    ctx.messenger.success(f"Imported {len(report.imported)} generator file(s).")
    if report.skipped:
        ctx.messenger.info(
            f"Skipped {len(report.skipped)} existing file(s) (use --force to overwrite)."
        )
    if report.dropped_answers:
        ctx.messenger.info(f"Ignored {len(report.dropped_answers)} bundled answer file(s).")
    return 0


# --- oracle-free bug finding, inference, import, model-assist ---------------


def _shape_source(args):
    """A seed->input callable from --shape/--param (+ dials), for stress-like modes."""
    shape, params = _apply_dials(args, args.shape, _parse_params(args.param))
    return lambda i: shapes.generate(shape, args.seed + i, params)  # noqa: E731


def _do_metamorphic(ctx, project, args):
    if not args.relation:
        raise UserError(
            "--metamorphic needs --relation.",
            hint="Relations: " + ", ".join(metamorphic.list_relations()),
        )
    group = args.group or "metamorphic"
    cases = generators.gen_metamorphic(
        ctx,
        project,
        args.relation,
        _shape_source(args),
        args.count,
        args.seed,
        group,
        keep=args.keep,
    )
    ctx.save_project()
    if cases:
        ctx.messenger.warning(
            f"Found {len(cases)} input(s) where '{args.relation}' is violated (group '{group}').",
            hint="The solution depends on something it shouldn't - inspect and fix.",
        )
    else:
        ctx.messenger.success(f"No '{args.relation}' violations in {args.count} trial(s).")
    return 0


def _do_property(ctx, project, args):
    group = args.group or "property"
    if args.ladder_spec:
        var, lo, hi, steps = _parse_ladder(args.ladder_spec)
        shape, params = _apply_dials(args, args.shape, _parse_params(args.param))
        sizes = generators._geometric_sizes(lo, hi, steps)

        def source(i):
            p = dict(params)
            p[var] = sizes[i % len(sizes)]
            return shapes.generate(shape, args.seed + i, p)

        count = len(sizes)
    else:
        source = _shape_source(args)
        count = args.count
    cases = generators.gen_property(
        ctx, project, args.property, source, count, args.seed, group, keep=args.keep
    )
    ctx.save_project()
    if cases:
        ctx.messenger.warning(
            f"Found {len(cases)} input(s) where '{args.property}' fails (group '{group}').",
            hint="Inspect them.",
        )
    else:
        ctx.messenger.success(f"Property '{args.property}' held over {count} input(s).")
    return 0


def _parse_ladder(spec):
    from morvix.properties import parse_ladder

    return parse_ladder(spec)


def _do_fuzz(ctx, project, args):
    group = args.group or "fuzz"
    seed_group = args.seed_group or "baseline"
    seeds = [
        _read_file(project.abspath(c.primary_input()))
        for c in project.cases
        if c.group == seed_group and c.primary_input()
    ]
    if not seeds:  # nothing to seed from: start from a few generated inputs
        src = _shape_source(args)
        seeds = [src(i) for i in range(5)]
    cases = generators.gen_fuzz(ctx, project, seeds, args.budget, args.seed, group, keep=args.keep)
    ctx.save_project()
    if cases:
        ctx.messenger.warning(
            f"Kept {len(cases)} input(s) with new observable behaviour (group '{group}').",
            hint="Run 'gen --expected' then 'run' to see what they do.",
        )
    else:
        ctx.messenger.success(f"No new behaviour found in {args.budget} trial(s).")
    return 0


def _do_mutate(ctx, project, args):
    group = args.group or "baseline"
    src = args.mutate_from or "baseline"
    ops = [o.strip() for o in args.ops.split(",")] if args.ops else None
    cases = generators.gen_mutate(
        ctx, project, src, args.count, args.seed, group, schema_path=args.schema, ops=ops
    )
    _post_generate(ctx, project, args, group)
    ctx.save_project()
    ctx.messenger.success(f"Mutated {len(cases)} new case(s) into group '{group}' from '{src}'.")
    ctx.messenger.info("Next: run 'gen --expected' to compute their answers.")
    return 0


def _do_infer(ctx, project, args):
    for p in args.infer:
        if not os.path.isfile(p):
            raise UserError(f"Sample not found: {p}", hint="Pass real sample input files.")
    rel = generators.infer_and_draft(
        ctx, project, args.infer, name=args.name or "gen", as_grammar=args.as_grammar
    )
    ctx.messenger.success(f"Wrote a draft from {len(args.infer)} sample(s): {rel}")
    ctx.messenger.info("Review and edit it (the inferred ranges may be too narrow), then:")
    ctx.messenger.info(f"  gen --generator {rel} --count 1000")
    return 0


def _do_import(ctx, project, args):
    group = args.group or "imported"
    summary = importers.import_corpus(
        ctx,
        project,
        args.import_path,
        group=group,
        split=args.split,
        keep_answers=args.keep_answers,
        dry_run=args.dry_run,
        dedup=True,
    )
    if not args.dry_run:
        ctx.save_project()
    importers.report_import(ctx, summary)
    return 0


def _do_suggest(ctx, project, args):
    if not args.hook:
        raise UserError(
            "--suggest needs --hook (your own executable that contacts a model).",
            hint="Morvix makes no network calls; the hook does, with your key.",
        )
    if not args.i_understand and not (ctx.interactive and _confirm_suggest(ctx)):
        raise UserError(
            "Model output is unverified and INPUT-only; pass --i-understand to proceed.",
            hint="Answers still come only from 'gen --expected' running your solution.",
        )
    kind = args.suggest or "scaffold"
    if kind not in ("scaffold", "inputs"):
        raise UserError("--suggest KIND must be 'scaffold' or 'inputs'.")
    samples = [
        _read_file(project.abspath(c.primary_input()))[:2000]
        for c in project.cases[:3]
        if c.primary_input()
    ]
    request = assist.build_request(kind, project, prompt=args.prompt, samples=samples)
    clean = assist.sanitize_response(kind, assist.call_hook(args.hook, request))
    if kind == "scaffold":
        rel = assist.write_scaffold(project, args.name or "suggested", clean.get("generator", ""))
        ctx.messenger.success(f"Wrote an UNVERIFIED suggested generator: {rel}")
        ctx.messenger.info("Review it carefully, then: gen --generator %s --count 100" % rel)
    else:
        cases = generators.gen_suggested_inputs(
            project, clean.get("inputs", []), group="suggested", seed=args.seed
        )
        ctx.save_project()
        ctx.messenger.success(f"Added {len(cases)} suggested input(s) in group 'suggested'.")
        ctx.messenger.info("These are inert until you run 'gen --expected'.")
    return 0


def _confirm_suggest(ctx):
    from morvix.components.confirm import confirm

    return confirm(
        ctx,
        "Run your model hook? Output is treated as unverified INPUT only; answers still "
        "come from gen --expected.",
        default=False,
    )


# Post-generation hooks shared by the generating modes.
def _post_generate(ctx, project, args, group):
    if args.require_valid:
        path = validators.resolve_validator(project, None)
        cases = [c for c in project.cases if c.group == group and c.primary_input()]
        results = validators.validate_cases(project, cases, path)
        invalid = {r.case_id for r in results if not r.valid and not r.degraded}
        if invalid:
            for c in list(project.cases):
                if c.id in invalid:
                    generators.clean_one(project, c)
            suggestions.suggest_invalid_inputs(ctx, list(invalid))
    if args.dedup:
        hygiene.dedup_pool(project, group=group)


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
    _post_generate(ctx, project, args, group)
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
