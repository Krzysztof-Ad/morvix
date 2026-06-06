<!--
Thanks for contributing to Morvix! A few notes:
- We squash-merge, so THIS PR's title becomes the commit message. It must be a valid
  conventional commit: type(optional scope): lowercase summary
  Allowed types: feat, fix, chore, refactor, docs, test
- Keep changes simple and readable; see CONTRIBUTING.md.
-->

## What and why

<!-- A short description of the change and the motivation. Link any issue: Fixes #123 -->

## Which axis does this touch?

<!-- Capability should land on exactly one axis. Tick all that apply. -->

- [ ] Language adapter (`morvix/adapters/`)
- [ ] Execution model (`morvix/models.py`, `morvix/execmodels/`)
- [ ] Comparison strategy (`morvix/compare.py`, `morvix/comparators.py`)
- [ ] Runner core (`morvix/runner_core/`)
- [ ] CLI / commands / UI
- [ ] Docs / CI
- [ ] None of the above

## Checklist

- [ ] The PR title is a valid conventional commit (it becomes the squash commit message).
- [ ] `ruff check .` and `ruff format --check .` pass.
- [ ] `mypy` passes.
- [ ] `pytest` passes locally (tests for missing toolchains skip, that's fine).
- [ ] If I changed the command surface or a concept, I regenerated `GUIDE.md`
      (`morvix docs --out GUIDE.md`) so `docs --check` stays green.
- [ ] If I changed judging logic, I updated `morvix/runner_core/morvix_runner.py` to mirror
      it (and it stays stdlib-only, Python 3.6-compatible).
- [ ] I did **not** bump the version in `pyproject.toml` / `morvix/version.py`
      (release-please owns those).
- [ ] No author/rival source or `config/` leaks into a built package.
- [ ] The change preserves the honesty principle (Morvix is not an authority on correctness).
