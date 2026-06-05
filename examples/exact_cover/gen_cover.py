#!/usr/bin/env python3
# Generator for the Algorithm X (exact cover) program.
#
# Prints ONE test instance to stdout: a filter line, then the matrix rows.
#   - filter:  one char per column, '+' = print this column, '-' = hide it
#   - row:     same length, '_' = does not cover, any other char = covers with that symbol
#
# Most instances are built to be SOLVABLE (so the program actually prints
# something), with a few decoy rows mixed in. Edge cases are keyed off the seed
# so a batch of many seeds naturally covers the corners.
#
# Usage: gen_cover.py <seed> [mode]

import random
import sys

SYMBOLS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def solvable(rng, max_cols=40):
    """A guaranteed-solvable instance: partition the columns into solution rows."""
    cols = rng.randint(1, max_cols)
    order = list(range(cols))
    rng.shuffle(order)

    # Split the columns into non-empty blocks; each block becomes one solution row.
    nblocks = rng.randint(1, cols)
    sizes = [1] * nblocks
    for _ in range(cols - nblocks):
        sizes[rng.randrange(nblocks)] += 1

    rows = []
    i = 0
    for s in sizes:
        block = order[i:i + s]
        i += s
        row = ["_"] * cols
        sym = rng.choice(SYMBOLS)
        for c in block:
            row[c] = sym
        rows.append("".join(row))

    # A handful of decoy rows (random partial covers) to make the search real.
    for _ in range(rng.randint(0, cols)):
        row = ["_"] * cols
        for c in range(cols):
            if rng.random() < 0.3:
                row[c] = rng.choice(SYMBOLS)
        if any(ch != "_" for ch in row):
            rows.append("".join(row))

    rng.shuffle(rows)
    flt = "".join("+" if rng.random() < 0.7 else "-" for _ in range(cols))
    return flt, rows


def edge_case(rng, kind):
    if kind == "single":                 # one column, one covering row
        return "+", ["A"]
    if kind == "all_plus":               # print every column
        flt, rows = solvable(rng, 12)
        return "+" * len(flt), rows
    if kind == "no_plus":                # solvable, but nothing is printed
        flt, rows = solvable(rng, 12)
        return "-" * len(flt), rows
    if kind == "one_row_covers_all":
        cols = rng.randint(1, 20)
        return "+" * cols, [rng.choice(SYMBOLS) * cols]
    if kind == "unsolvable":             # decoys only -> no exact cover -> no output
        cols = rng.randint(2, 20)
        rows = []
        for _ in range(rng.randint(1, cols)):
            row = ["_"] * cols
            row[rng.randrange(cols)] = rng.choice(SYMBOLS)  # never covers everything
            rows.append("".join(row))
        return "+" * cols, rows
    if kind == "big":                    # larger structured instance
        return solvable(rng, 90)
    return solvable(rng)


# Seed buckets that sprinkle edge cases through a batch of consecutive seeds.
EDGE = {0: "single", 1: "all_plus", 2: "no_plus", 3: "one_row_covers_all",
        4: "unsolvable", 5: "big"}


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    mode = sys.argv[2] if len(sys.argv) > 2 else "auto"
    rng = random.Random(seed)

    if mode != "auto":
        flt, rows = edge_case(rng, mode)
    else:
        bucket = seed % 20          # ~1 in 20 is an edge case, the rest are random
        flt, rows = edge_case(rng, EDGE[bucket]) if bucket in EDGE else solvable(rng)

    sys.stdout.write(flt + "\n")
    for r in rows:
        sys.stdout.write(r + "\n")


if __name__ == "__main__":
    main()
