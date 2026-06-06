# Security Policy

## Supported versions

Morvix is a small project; only the latest released version receives fixes.

| Version | Supported |
| ------- | --------- |
| latest (on PyPI) | yes |
| older   | no        |

## Reporting a vulnerability

Please report security issues **privately** - do not open a public issue.

- Preferred: use GitHub's **private vulnerability reporting** ("Report a vulnerability" on
  the repository's **Security** tab).
- Or email the maintainer: **krzysiuadamczyk0@gmail.com**.

Please include the version, your platform, and the smallest steps that reproduce the issue.
You can expect an acknowledgement within a few days. Once a fix is ready, a new release is
cut and the advisory is published with credit to the reporter (unless you prefer to remain
anonymous).

## Trust model (please read)

Morvix builds and runs programs. It is a developer tool, **not a sandbox**. When you run a
solution or open a shared package, code compiles and executes on **your own machine** with
your own permissions:

- An author builds tests from their solution and shares a package. The package contains
  test inputs, expected answers, a README, a manifest, and the stdlib-only runner - never
  the author's source, and (unless the author explicitly opts in) never any rival source.
- A receiver drops their own code into a package and runs it locally. `run.sh` builds and
  runs **the receiver's own code** against the shared tests.

Only run packages and solutions you trust, the same way you would with any code you compile
and execute. Resource limits (time/memory/output) are guardrails against runaway programs,
not a security boundary against hostile code. Treat untrusted submissions accordingly (for
example, in a container or VM you control).
