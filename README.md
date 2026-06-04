# Morvix

[![PyPI version](https://img.shields.io/pypi/v/morvix.svg)](https://pypi.org/project/morvix/)
[![Python versions](https://img.shields.io/pypi/pyversions/morvix.svg)](https://pypi.org/project/morvix/)
[![CI](https://github.com/Krzysztof-Ad/morvix/actions/workflows/ci.yml/badge.svg)](https://github.com/Krzysztof-Ad/morvix/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A test-authoring, test-running, and test-sharing CLI for university programming assignments.

Most courses don't hand out test suites, so students end up writing their own: they build test
cases from their own solution, run their program against them, and share the cases on GitHub so
classmates can check their code too. Morvix automates that whole loop - building, running, and
sharing these self-made test harnesses - quickly and consistently, across languages and platforms.

It's an honest tool. The "expected answers" come from one student's own solution, so passing every
test does **not** prove a solution is correct - it proves it agrees with that one reference on the
cases tried. Morvix says so plainly (it's baked into every package's README) and makes the real
signal - lots of independent solutions agreeing - easy to see.

> Morvix is not an online judge, not a grading server, and not an AI tool. It runs locally and
> offline. Linux and macOS are the primary targets; Windows works on a best-effort basis.

## Install

```sh
pip install morvix          # or, from a clone:
pip install .
```

Needs Python 3.9+. The only dependencies are `prompt_toolkit` and `rich`. The runner that ships
inside shared packages is pure standard library, so whoever you share with needs nothing but
Python 3.

## Quick start (the Author)

Run `morvix` with no arguments to open the interactive shell (live autocomplete, history, a status
bar), or use any command one-shot from your normal shell. What you can do one way is identical the
other way.

```sh
cd my-assignment
morvix init                       # create a project here (guided)
morvix config cpp                 # how to build/run your language
morvix import solution.cpp        # the solution under test
morvix reference solution.cpp     # it also defines the expected answers
morvix gen --random --count 100   # generate inputs from the built-in shapes
morvix gen --expected             # compute answers by running the reference
morvix run --all                  # build, run, judge - with a live table
morvix runner new full            # a named, shareable run profile
morvix package --zip              # bundle it up to share (your source is left out)
```

## Quick start (the Receiver)

You got a package from a classmate. You don't need Morvix at all:

```sh
unzip their-tests.zip && cd their-tests
./run.sh my_solution.cpp          # builds your code, runs every test, reports
```

If you *do* have Morvix, open it in the unpacked directory and you get the rich view - browse the
tests, re-run selectively, and diff your per-case results against the author's.

## What's in the box

- **Languages**: C, C++, NASM, Python, Java, Rust - each a small adapter. Adding one is one file.
- **Execution models**: `stdio`, `library` (link & assert), `args`, `file`, `interactive`.
- **Comparison**: byte-exact, whitespace-insensitive, float-tolerant, hash, a custom checker, and
  expected exit status / crash - combinable per case.
- **Limits & checks**: wall/CPU time, peak memory (approximate), hard memory caps, output caps, and
  an optional valgrind memory-correctness pass.
- **Generation**: a built-in random-shape library, custom generators, stress testing against a
  brute force, and crash-case candidates.
- **Sharing**: zip / tar / tar.gz / tar.xz packages with an auto-generated README and a manifest.
- **Workflows**: record a sequence of commands and replay it on the next assignment.

These three axes - language, execution model, comparison - are kept independent, so they never
multiply against each other. That's the design decision everything else hangs on.

## Design

The full design is in [documentation.md](documentation.md): the architecture, every command, the
file formats, and the reasoning behind each choice.

## License

[MIT](LICENSE) (c) Krzysztof Adamczyk
