# gen command: make test inputs and compute expected answers (Section 13).
#
# One mode per invocation (mutually exclusive):
#   --manual NAME    hand-written, permanent case
#   --random         random inputs from a built-in shape
#   --generator PROG run a custom generator program
#   --expected       (re)compute expected answers from the reference
#   --stress         pit the solution against the brute force, keep first failure
#   --crash          mangle inputs into malformed variants
#
# All mutating modes save the project afterwards and print a summary.

import glob
import os

from morvix import generators, shapes, suggestions
from morvix.components.progress import progress_bar
from morvix.errors import UserError

NAME = "gen"

# Above this many random cases we show a progress bar.
LARGE_COUNT = 50


def configure(parser):
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--manual", metavar="NAME",
                      help="create a permanent hand-written case named NAME")
    mode.add_argument("--random", action="store_true",
                      help="generate random inputs from a built-in shape")
    mode.add_argument("--generator", metavar="PROG",
                      help="run a custom generator program to produce inputs")
    mode.add_argument("--expected", action="store_true",
                      help="(re)compute expected answers from the reference")
    mode.add_argument("--stress", action="store_true",
                      help="stress the solution against the brute force")
    mode.add_argument("--crash", action="store_true",
                      help="generate malformed inputs to probe error handling")

    parser.add_argument("--hash", action="store_true",
                        help="with --expected: store output digests instead of files")
    parser.add_argument("--count", type=int, default=10,
                        help="how many cases to generate (default 10)")
    parser.add_argument("--seed", type=int, default=1,
                        help="base random seed (default 1)")
    parser.add_argument("--group",
                        help="target group (default depends on mode)")
    parser.add_argument("--shape", default="ints", choices=shapes.list_shapes(),
                        help="with --random: input shape (default ints)")
    parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE",
                        help="shape parameter, repeatable (e.g. --param lo=0)")


# Parse repeated KEY=VALUE strings into a dict, coercing ints/floats.
def _parse_params(items):
    params = {}
    for item in items:
        if "=" not in item:
            raise UserError(f"Bad --param '{item}': expected KEY=VALUE.",
                            hint="For example: --param lo=0 --param hi=100")
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

    raise UserError("No generation mode given.",
                    hint="Pick one of --manual, --random, --generator, "
                         "--expected, --stress, --crash.")


def _do_manual(ctx, project, args):
    group = args.group or "baseline"
    case = generators.gen_manual(ctx, project, args.manual, group=group)
    ctx.save_project()
    ctx.messenger.success(f"Created manual case {case.id}.")
    return 0


def _do_random(ctx, project, args):
    group = args.group or "baseline"
    params = _parse_params(args.param)
    count = args.count

    # Show a progress bar only when there's enough work to be worth it.
    if count >= LARGE_COUNT:
        with progress_bar(ctx, count, "generating") as step:
            cases = generators.gen_random(ctx, project, args.shape, count,
                                          args.seed, group, params)
            step(count)
    else:
        cases = generators.gen_random(ctx, project, args.shape, count,
                                      args.seed, group, params)

    ctx.save_project()
    ctx.messenger.success(
        f"Generated {len(cases)} '{args.shape}' case(s) in group '{group}'."
    )
    ctx.messenger.info("Next: run 'gen --expected' to compute their answers.")
    return 0


def _do_generator(ctx, project, args):
    group = args.group or "baseline"
    path = os.path.abspath(args.generator)
    if not os.path.isfile(path):
        raise UserError(f"Generator not found: {args.generator}",
                        hint="Check the path and try again.")
    cases = generators.gen_from_generator(ctx, project, path, args.count,
                                          args.seed, group)
    ctx.save_project()
    ctx.messenger.success(
        f"Generated {len(cases)} case(s) in group '{group}' "
        f"from {os.path.basename(path)}."
    )
    ctx.messenger.info("Next: run 'gen --expected' to compute their answers.")
    return 0


def _do_expected(ctx, project, args):
    # Remember which cases already carried a crash expectation so we only flag
    # the ones gen_expected discovered this run.
    before = {c.id for c in project.cases
              if c.expected_exit is not None or c.expected_signal is not None}

    computed = generators.gen_expected(ctx, project, use_hash=args.hash)
    ctx.save_project()

    how = "hashes" if args.hash else "output files"
    ctx.messenger.success(f"Computed {computed} expected answer(s) ({how}).")

    # Cases that crashed under the reference now carry an exit/signal expectation.
    crashing = [c.id for c in project.cases
                if (c.expected_exit is not None or c.expected_signal is not None)
                and c.id not in before]
    if crashing:
        suggestions.suggest_exit_status(ctx, project, crashing)
    return 0


def _do_stress(ctx, project, args):
    group = args.group or "regression"
    case = generators.gen_stress(ctx, project, args.count, args.seed, group=group)
    ctx.save_project()
    if case is None:
        ctx.messenger.success(
            f"No failing case found in {args.count} random trial(s)."
        )
    else:
        ctx.messenger.warning(
            f"Found a failing case: saved as {case.id}.",
            hint="Inspect it and fix the solution, then rerun.",
        )
    return 0


def _do_crash(ctx, project, args):
    group = args.group or "bad-input"
    cases = generators.gen_crash(ctx, project, args.count, args.seed, group=group)
    ctx.save_project()
    ctx.messenger.success(
        f"Generated {len(cases)} malformed case(s) in group '{group}'."
    )
    return 0


def complete(ctx, prev_words, word):
    prev = prev_words[-1] if prev_words else ""

    # --shape: suggest the known shapes.
    if prev == "--shape":
        return [(s, "shape") for s in shapes.list_shapes()
                if s.startswith(word or "")]

    # --generator: suggest filesystem paths.
    if prev == "--generator":
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
