# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Morvix is a Python CLI that lets a student build test cases from their own solution, run their code
against them, and package the harness to share with classmates. The full design lives in
`documentation.md` (831 lines) - read the relevant section before changing behavior; the code is
organized to mirror it and many comments cite section numbers (e.g. "Section 14.6").

## Dev commands

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # set up
.venv/bin/morvix                 # interactive shell
.venv/bin/morvix <cmd> ...       # one-shot (same verbs as the shell)
.venv/bin/python -m compileall -q morvix   # quick syntax check of everything
.venv/bin/pytest                 # run the test suite
.venv/bin/pytest tests/test_x.py::test_y   # a single test
```

The toolchains used by the language adapters (`gcc`/`g++`, `nasm`, `javac`/`java`, `rustc`,
`valgrind`) must be on PATH to exercise those paths. `rustc` and `valgrind` are commonly absent on
macOS; those features degrade with an honest warning rather than faking results.

## The architecture that matters

Everything hangs on **three orthogonal axes that never multiply against each other** (Section 4.1).
When adding capability, add to exactly one axis:

- **Language adapter** (`morvix/adapters/<lang>.py`) - turns source into something runnable. Knows
  nothing about tests. Subclass `Adapter`, implement `build/run_spec/describe`, call `register()`.
- **Execution model** (`morvix/models.py` for `stdio`; `morvix/execmodels/<name>.py` for the rest) -
  how a runnable thing is driven and what its observable output is. A function
  `(case, env, limits) -> Observation` registered with `register_model`.
- **Comparison strategy** (`morvix/compare.py` for exact/whitespace; `morvix/comparators.py` for
  float/hash/checker) - given output + expected, decide pass/fail. A function
  `(CompareInput) -> Verdict` registered with `register_comparator`.

`morvix/judge.py` is the engine that ties them together: build once, run each case through the
model, then combine the enabled dimensions (output match + expected exit/signal + memory) so a case
can require all of them at once (Section 14.7). `morvix/process.py` is the bottom layer (spawn,
rlimits, timing, `wait4`-based per-child memory, `LC_ALL=C` locale) and is the single place that
papers over Linux/macOS differences.

The stack, top to bottom: shell/CLI (`app`, `shell`, `registry`) -> shared components
(`components/`) -> commands (`commands/`) -> orchestration (`project`, `generators`, `manifest`,
`packaging`, `workflow`, `results`) -> the three axes -> `process`.

## Key conventions and invariants

- **Two entry points, one vocabulary.** `morvix/registry.py` builds one argparse parser used by both
  the REPL and one-shot mode. Each command module exposes `NAME`, `configure(parser)`,
  `run(ctx, args) -> int`, and an optional `complete(ctx, prev_words, word)`. Errors raise (they do
  not `sys.exit`) so the shell survives them.
- **One shared UI layer.** Commands never hand-roll a menu, prompt, table, or message. They compose
  from `morvix/components/` (selection, choice, form, confirm, table, progress) and print only via
  `ctx.messenger`. Each component has a non-interactive fallback driven by `ctx.interactive`.
- **The directory is the state, hidden under `.morvix/`.** No database. Everything (config,
  tests, expected, runner, results, ... and the generated `morvix.json` manifest) lives under a
  single `.morvix/` dir so the project root stays clean. `layout.py` roots every path there via
  `STATE_DIR`; stored case paths are `.morvix/...`-prefixed. A **package archive is flat**, though
  (`packaging.py` strips the `.morvix/` prefix): run.sh, README, morvix.json and the
  tests/expected/runner trees sit at the archive root so a receiver sees the harness directly; a
  Morvix-equipped receiver that opens one re-adopts it back into `.morvix/` (`adopt_manifest`
  re-prefixes the paths). `Project.load` auto-migrates a pre-0.2 flat layout into `.morvix/`. Config
  is JSON throughout.
- **Warn, don't mislead.** `gen --expected` calls `suggestions.warn_degenerate_expected`: when
  almost every computed answer is empty or identical, the inputs likely don't match the program's
  format, so it points the user at `gen --new-generator`. That scaffold is the on-ramp for the
  common "random shapes don't fit structured input" case.
- **The runner core is sacred and standalone.** `morvix/runner_core/morvix_runner.py` ships verbatim
  inside packages, must import **nothing** from `morvix`, must be **stdlib-only**, and must run on a
  clean machine with just Python 3. It re-implements the judge logic; if you change judging behavior
  in `judge.py`/`process.py`/`compare.py`, keep the runner core in sync. `run.sh` is its wrapper and
  is placed at the package root by `packaging.py` so `./run.sh` works.
- **A package never contains the author's source** (`solutions/`), the brute-force reference, or
  `config/`. See `packaging.build_package`.
- **Honesty is a feature.** Expected answers come from one peer's solution, not an authority. The
  correctness disclaimer is always included in the generated README (`readme.py`). Smart suggestions
  (`suggestions.py`) explain and ask - they never change behavior silently.
- **Help text has one home.** `morvix/help_text.py` powers both `help` and the autocomplete meta
  column; keep summaries there in sync with what a command actually does.
- **Rivals are perf-only, never correctness.** A `Rival` (`project.rivals`) is an alternative
  implementation compared for time/memory; it never touches tests or expected answers. `reference`
  defines answers; a rival tagged `stress` is the stress oracle (the old `bruteforce`, auto-migrated).
  `morvix/comparison.py` runs the solution + rivals (sequential by default - parallel skews numbers);
  `results.comparison_block` renders it and is **mirrored** in the runner core. Packages stay
  code-free: `rival precompute` records numbers that ship by default; shipping rival *code* is opt-in
  and warned (`package --rivals code`).

## Style

Comments are plain-English header blocks per file/function with occasional `# - bullet` lists for
multi-step logic; sparse inline comments; no heavy docstrings. Keep code simple - this is open
source and meant to be readable by a newcomer. Commit messages are conventional (`feat:`, `fix:`,
`chore:`, `refactor:`, `docs:`, `test:`), lowercase, no body or trailers.

## Releasing

The package is on PyPI (https://pypi.org/project/morvix/) and publishes automatically via PyPI
Trusted Publishing - no API token is stored. `.github/workflows/publish.yml` builds and uploads
when a GitHub Release is published, authenticating through OIDC against a registered publisher
(repo `Krzysztof-Ad/morvix`, workflow `publish.yml`, environment `pypi`).

To cut a release:
1. Bump the version in BOTH `pyproject.toml` and `morvix/version.py` (they must match; PyPI refuses
   to re-upload an existing version).
2. Commit and push.
3. Create a GitHub Release on the new tag: `gh release create vX.Y.Z --title vX.Y.Z --notes "..."`.
4. The publish workflow runs on the release and uploads the sdist + wheel.

`pyproject.toml` force-includes `morvix/runner_core/{morvix_runner.py,run.sh}` as package data - the
shipped runner must travel in the wheel, so do not break that include.

## Keeping the docs current (do this every session / PR)

`morvix docs` and the committed `GUIDE.md` are the user guide. The command reference and capability
tables are GENERATED from `help_text.py` and the registries, so they self-maintain; the conceptual
prose is the `CONCEPTS` list in `morvix/docs.py` (and the deeper design lives in `documentation.md`).

At the end of any session/PR that changes behavior, before you finish:
1. If you changed the command surface (added/renamed a command, changed flags or `help_text`) or a
   `CONCEPTS` fragment, regenerate the guide: `morvix docs --out GUIDE.md`, and commit it. CI's
   `docs --check` job fails the build if `GUIDE.md` is stale, so this is enforced - but regenerate it
   yourself so the PR is green.
2. If the change is conceptual (a new model/strategy, a changed mental model), update the relevant
   `CONCEPTS` fragment in `morvix/docs.py` and review `documentation.md` for accuracy.
The generated parts cannot drift; only the hand-written `CONCEPTS`/`documentation.md` need judgement.
