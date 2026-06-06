# Example: exact cover (a structured-input problem)

This example shows the Morvix workflow for a program whose input has real
**structure** - the case where the built-in random shapes don't help and you
want a **custom generator**. `solve.c` is a small Algorithm X (exact cover)
solver; `gen_cover.py` builds valid, mostly-solvable instances for it.

## The input format

- Line 1 is a **filter**: one char per column, `+` to print that column, anything
  else to hide it.
- Each later line is a **matrix row** of the same length: `_` means "doesn't
  cover this column", any other char "covers it with that symbol".
- A blank line or EOF ends the matrix.

A run finds every exact cover and prints the merged solution, showing only the
`+` columns:

```
$ printf '++++\nA_A_\n_B_B\n' | ./solve
ABAB
```

## Why random data fails here

If you point Morvix's random shapes at this program, the "inputs" won't be valid
exact-cover instances, the solver finds nothing, and every expected output comes
out **empty**. Morvix now warns you when that happens. The fix is a generator
that knows the format - which is the whole point of this example.

## Run it with Morvix

```sh
cd examples/exact_cover
morvix init --name exact_cover --language c --model stdio
morvix config c --std gnu17 --opt O2
morvix import solve.c                          # the solution under test (it also defines the answers)
morvix gen --generator gen_cover.py --count 1000   # 1000 structured inputs
morvix gen --expected                          # real answers from your solution
morvix run --all                               # build, run, judge
morvix package --zip                           # share it (without your source)
```

`gen --expected` computes the answers by running your solution, so the tests are
only as "correct" as that one solution - exactly the honesty point Morvix is
built around.

## Writing your own generator

For a different assignment, start from a scaffold and edit `build_input()`:

```sh
morvix gen --new-generator mygen
# edit .morvix/generators/mygen.py to match your program's input
morvix gen --generator .morvix/generators/mygen.py --count 1000
morvix gen --expected
```
