# Changelog

## [0.8.0](https://github.com/Krzysztof-Ad/morvix/compare/morvix-v0.7.0...morvix-v0.8.0) (2026-06-06)


### Features

* add docs command and a generated GUIDE.md user guide, kept fresh by a CI gate; bump to 0.4.0 ([02a9ca8](https://github.com/Krzysztof-Ad/morvix/commit/02a9ca87d6f425fd154fafcd5d9a06f5bdcf0692))
* docs now documents positional arguments and option value placeholders/choices, not just flag names; bump to 0.4.1 ([2242591](https://github.com/Krzysztof-Ad/morvix/commit/22425917d3bd0c2eb931f57848349efad2132fc6))
* flatten the package archive so the harness sits at the root, not under .morvix; re-adopt flat packages on open; bump to 0.3.0 ([ef9d250](https://github.com/Krzysztof-Ad/morvix/commit/ef9d250aab2d5058c33743d956088283afae32c1))
* hide project state under .morvix with auto-migration, warn on degenerate expected outputs, and add gen --new-generator scaffold ([65b1ba1](https://github.com/Krzysztof-Ad/morvix/commit/65b1ba1d86d72bcc1a25da47f3d6b3f87441331d))
* implement all command modules and the interactive prompt_toolkit shell ([51418df](https://github.com/Krzysztof-Ad/morvix/commit/51418df369524adce4cfab03b87b5d76aa58aee6))
* implement language adapters, comparators, execution models, shapes, and the stdlib runner core ([c435aee](https://github.com/Krzysztof-Ad/morvix/commit/c435aeef6cde989b7bdfa0881ef64bf50ebef55d))
* implement shared interaction components and orchestration modules ([fa9a39b](https://github.com/Krzysztof-Ad/morvix/commit/fa9a39bf77ecdd6b3e965c116915c689edbaddbf))
* morvix init writes a sensible .gitignore (build artifacts, transient and private state); bump to 0.2.1 ([363a90b](https://github.com/Krzysztof-Ad/morvix/commit/363a90ba32cd6d6c4a089200ad64e7c5dacb0dec))
* performance reporting - per-case time/CPU/memory inline plus a configurable summary (totals, min/avg/max, peak memory, slowest cases, pass %), shown in run and the shipped runner and auto-emitted by configured runners; bump to 0.5.0 ([5714792](https://github.com/Krzysztof-Ad/morvix/commit/5714792742cd14c17d77db26e5d4f40c2a1799ab))
* rival comparison (phase 2) - precompute + three packaging ship modes (precomputed default, code opt-in, none), runner-core mirror so ./run.sh shows the comparison, and --no-rivals; bump to 0.6.0 ([9590504](https://github.com/Krzysztof-Ad/morvix/commit/95905048cce78944be1785e3de3e1ed932a72e7d))
* rival performance comparison (phase 1) - rival model + command, bruteforce folded into a stress-tagged rival with migration, and author-side solution-vs-rivals comparison in run (sequential default, --parallel/--no-rivals) ([7bb02ea](https://github.com/Krzysztof-Ad/morvix/commit/7bb02ead0a3630a366050e19ef3777460f6f40bf))


### Bug Fixes

* drop removed 'reference' command from the build-package ci step ([4a3597c](https://github.com/Krzysztof-Ad/morvix/commit/4a3597c9a374e5ebff907a52cd498831062c6828))
* enforce clean exit-0 by default and resolve review findings across judge, runner core, comparators, packaging, and commands ([5f06f62](https://github.com/Krzysztof-Ad/morvix/commit/5f06f626eb6ae6da2fd84dcf644e1ed466b3b790))
* rival comparison aggregate now aligns each column to the cases actually run, so a filtered run vs precomputed rivals compares the same case set; bump to 0.6.1 ([f3f499b](https://github.com/Krzysztof-Ad/morvix/commit/f3f499b80de82246e2154307812e17cde6d828fc))


### Refactoring

* remove reference and bruteforce commands; gen --expected now always uses the solution under test ([7374fce](https://github.com/Krzysztof-Ad/morvix/commit/7374fce822c9dff3174897572f5703bb249b920c))


### Documentation

* add contributing guide, code of conduct, and security policy ([abd1393](https://github.com/Krzysztof-Ad/morvix/commit/abd1393a27e81865fb0b42f4bf5d3ddb53865465))
* add contributing section and switch releasing to release-please ([aba11f6](https://github.com/Krzysztof-Ad/morvix/commit/aba11f66b75d9bbccdce00f7515e84993b19883d))
* add exact-cover example and document the .morvix layout; bump to 0.2.0 ([e7274ef](https://github.com/Krzysztof-Ad/morvix/commit/e7274efff97f1687c7158a48db5529cfc60bd03f))
* add PyPI/CI/license badges to README and record the release process in CLAUDE.md ([bfcf831](https://github.com/Krzysztof-Ad/morvix/commit/bfcf831934fc9bb76184bc04186c33fb2e4e5cff))
* add README and CLAUDE.md ([d5c5b75](https://github.com/Krzysztof-Ad/morvix/commit/d5c5b75a5f38740e81703f8e012303fa410caf3b))
* trim documentation.md to a lean design doc - defer the command reference to GUIDE.md, fix the .morvix/flat-package layout, drop the TOML mention ([a09cb5e](https://github.com/Krzysztof-Ad/morvix/commit/a09cb5e1438d8d7cde767a57ee8e5d7e5e6ef522))

## Changelog

This file is maintained automatically by [release-please]; entries are generated
from conventional commit messages. Releases before automation was adopted (up to
0.7.0) are recorded on the [GitHub releases page].

[release-please]: https://github.com/googleapis/release-please
[GitHub releases page]: https://github.com/Krzysztof-Ad/morvix/releases
