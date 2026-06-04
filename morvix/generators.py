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


def gen_manual(ctx, project, name, group="baseline", content=None):
    raise NotImplementedError


def gen_random(ctx, project, shape, count, seed, group, params):
    raise NotImplementedError


def gen_from_generator(ctx, project, generator_path, count, seed, group, modes=None):
    raise NotImplementedError


def gen_expected(ctx, project, use_hash=False, groups=None):
    raise NotImplementedError


def gen_stress(ctx, project, count, seed, group="regression"):
    raise NotImplementedError


def gen_crash(ctx, project, count, seed, group="bad-input"):
    raise NotImplementedError


def clean_generated(project, group=None):
    raise NotImplementedError
