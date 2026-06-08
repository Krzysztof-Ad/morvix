# Contributing to Morvix

Thanks for your interest in improving Morvix. It is a small, deliberately simple
codebase, and the goal is to keep it that way: readable by a newcomer, honest about what
it does, and easy to extend along well-defined seams. This guide explains how to set up,
where things live, the few invariants that matter, and how a change gets merged.

If anything here is unclear or out of date, that is itself a bug worth a PR.

## The one idea that shapes everything

Morvix is honest by design. The "expected answers" come from one student's own solution,
so passing every test does **not** prove a solution is correct - it proves it agrees with
that one solution on the cases tried. Please keep this principle intact: contributions
should never imply Morvix is an authority on correctness, a grading server, or an oracle.
The disclaimer in generated packages stays.

## Dev setup

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # set up
.venv/bin/morvix                 # interactive shell
.venv/bin/morvix <cmd> ...       # one-shot (same verbs as the shell)
.venv/bin/python -m compileall -q morvix   # quick syntax check of everything
.venv/bin/pytest                 # run the test suite
.venv/bin/pytest tests/test_x.py::test_y   # a single test
```

Python 3.9+ is required. The only runtime dependencies are `prompt_toolkit` and `rich`.

### Optional toolchains

The language adapters shell out to real compilers, so some tests need them on `PATH`:
`gcc`/`g++`, `nasm`, `javac`/`java`, `rustc`, `valgrind`. **You do not need all of them.**
Tests that require a missing toolchain skip themselves (via `@pytest.mark.skipif`), so a
clean local run on macOS without `rustc`/`valgrind` is still green. CI runs the full matrix
(Ubuntu + macOS x Python 3.9 + 3.12, with Java and Linux valgrind), so the complete suite
is exercised there.

## The architecture you need to know

Everything hangs on **three orthogonal axes that never multiply against each other**. When
you add a capability, add it to **exactly one** axis - that is what keeps the codebase
small. (`documentation.md` is the deep design doc; many code comments cite its sections.)

### 1. Add a language adapter - turns source into something runnable

New file `morvix/adapters/<lang>.py`. Subclass `Adapter`, implement `build`, `run_spec`,
and `describe`, then call `register()` at module level. Add the file extension(s) to the
extension map in `morvix/adapters/__init__.py`. The smallest reference is
`morvix/adapters/python.py`. An adapter knows nothing about tests.

If your language must also run inside a shared package on a clean machine, mirror the
extension mapping in `morvix/runner_core/morvix_runner.py` (see "the runner core is
sacred" below).

### 2. Add an execution model - how a runnable thing is driven and observed

A function `(case, env, limits) -> Observation`, registered with `register_model`.
`stdio` lives in `morvix/models.py`; everything else lives in
`morvix/execmodels/<name>.py`. Reference: `morvix/execmodels/args.py`.

### 3. Add a comparison strategy - decides pass/fail

A function `(CompareInput) -> Verdict`, registered with `register_comparator`. `exact` and
`whitespace` live in `morvix/compare.py`; `float`/`hash`/`checker` in
`morvix/comparators.py`. Use `make_diff(expected, observed)` for a unified diff in the
verdict.

### Adding to the generation toolkit

A new way to make tests is an **input source**, not a fourth axis - it produces inputs and
nothing else. The single most important rule: **only `gen --expected` may set an expected
answer.** Every generator/driver writes `inputs` and leaves `expected_*` unset; the static
guard in `tests/test_honesty.py` fails CI if an input-only module ever assigns one. (The
stress oracle and `gen --shrink` are the only documented carve-outs, and they live in
`generators.py`.) There is one mutation engine (`morvix/mutate.py`) and one tokenizer
(`schema.tokenize_lines`) - reuse them rather than adding parallel ones. New `gen` flags and
help text go in `morvix/help_text.py` + `gen_cmd.py`, and `GUIDE.md` is regenerated.

## Invariants (please don't break these)

- **The runner core is sacred.** `morvix/runner_core/morvix_runner.py` ships verbatim
  inside every package and is what a receiver runs with nothing but Python 3. It must
  import **nothing** from `morvix`, be **stdlib-only**, and stay **Python 3.6-compatible**
  (no walrus, no `match`, no 3.10 typing). It re-implements the judge, so if you change
  judging in `judge.py` / `process.py` / `compare.py` / `comparators.py` / `results.py`,
  update the runner core to match. Two guards enforce this: `tests/test_runner_stdlib.py`
  and the `receiver-clean` CI job.
- **The directory is the state.** No database. A project keeps everything under a single
  hidden `.morvix/` directory; a package is flat instead. A package never contains the
  author's source, any rival source, or `config/`.
- **Help text has one home.** `morvix/help_text.py` is the single source for command
  summaries; it powers both `help` and autocomplete. Keep it in sync with behavior.
- **The guide is generated.** `GUIDE.md` is produced by `morvix docs --out GUIDE.md` from
  `help_text.py`, the registries, and the `CONCEPTS` prose in `morvix/docs.py`. **Do not
  hand-edit `GUIDE.md`.** If you change the command surface or a concept, regenerate it and
  commit it - CI's `docs --check` job fails the build if it is stale.
- **Rivals are perf-only, never correctness.** Expected answers always come from the
  solution under test (`gen --expected`). A rival is only ever compared for time/memory.

## Code style and quality

- Plain-English header-block comments per file/function, with occasional `# - bullet`
  lists for multi-step logic; sparse inline comments; no heavy docstrings. Keep it simple
  and readable by a newcomer.
- Lint, format, and type checks run in CI and must pass:
  - `ruff check .` - catches real problems (unused imports, undefined names, broken
    f-strings) and sorts imports.
  - `ruff format --check .` - formatting. Run `ruff format .` before committing.
  - `mypy` - a lenient type check over `morvix/` (the runner core and tests are excluded).
- Optional but handy: `pip install pre-commit && pre-commit install` runs the same checks
  on commit. CI remains the source of truth.

## Commits and pull requests

- **Conventional commits**, lowercase, no body or trailers. Allowed types: `feat`, `fix`,
  `chore`, `refactor`, `docs`, `test`. Examples:
  `feat: add a haskell adapter`, `fix: handle empty stdin in the args model`.
- We **squash-merge**, so **the pull-request title becomes the commit message** - it must
  itself be a valid conventional commit. A CI check enforces this on every PR.
- A PR is ready to merge when all CI checks are green: the test matrix, `docs --check`, the
  `receiver-clean` sacred-path job, lint/format/type-check, and the PR-title check.
- `main` is protected: changes land through pull requests with passing checks and a linear
  history; merged branches are deleted automatically.
- **Do not bump the version** in `pyproject.toml` or `morvix/version.py`. Releases are
  automated (see below) and own those files.

## Releases (maintainer)

Releases are automated with [release-please]. Merging conventional-commit PRs to `main`
keeps a standing "release PR" that bumps both version files and updates `CHANGELOG.md`.
Merging that release PR tags the version and creates a GitHub Release, which triggers the
existing PyPI Trusted-Publishing workflow. See `CLAUDE.md` for the full maintainer notes.

[release-please]: https://github.com/googleapis/release-please

## Reporting bugs, requesting features, asking questions

- **Bugs and features:** open an issue using the forms in the issue tracker.
- **Questions and ideas:** use [Discussions](https://github.com/Krzysztof-Ad/morvix/discussions).
- **Security:** please follow [SECURITY.md](SECURITY.md) - do not open a public issue for a
  vulnerability.

By contributing, you agree your work is licensed under the project's [MIT License](LICENSE)
and that you will follow the [Code of Conduct](CODE_OF_CONDUCT.md).
