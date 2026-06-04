# Built-in random-data shape library (Section 13.2).
#
# Common input shapes so you do not write a generator from scratch for trivial
# cases. Everything is seeded for reproducibility. Shapes are composable
# building blocks; the list is meant to grow.
#
# API (implement in Workflow B):
#   list_shapes() -> list[str]
#   generate(shape: str, seed: int, params: dict) -> str   # the input text
#   SHAPES: dict[str, callable]   # name -> fn(rng: random.Random, params: dict) -> str


SHAPES = {}


def list_shapes():
    raise NotImplementedError


def generate(shape, seed, params):
    raise NotImplementedError
