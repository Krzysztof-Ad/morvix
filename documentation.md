# MORVIX — Design Documentation

*A test-authoring, test-running, and test-sharing CLI for university programming assignments.*

**by Krzysztof Adamczyk**

> This is the **design doc**: the architecture and the reasoning behind each
> decision, for contributors. For day-to-day usage — every command, its options
> and examples — run `morvix docs` or read [GUIDE.md](GUIDE.md), which is
> generated from the tool and always current. Code comments cite the sections
> here (e.g. "Section 14.6"), so the numbering is stable.

---

## Table of Contents

1. What Morvix is (and is not)
2. The two-sided model: Author and Receiver
3. The core mental model: the project, and the four pipeline stages
4. System architecture (the layers, and why they're separated)
5. The interactive shell (REPL) and the one-shot mode
6. Shared interaction components (the consistent UI layer)
7. Errors, warnings, and messages
8. Languages under test
9. The `config` system
10. Execution models (how a program is invoked and judged)
11. Importing code under test
12. Test cases: structure and storage
13. Test generation
14. Comparison strategies (how "correct" is decided)
15. Resource limits and memory-correctness
16. Runners (the shareable execution artifact)
17. Results and reporting
18. Workflows (record-and-replay automation)
19. Packaging and the package format
20. The Receiver experience (with and without Morvix)
21. Cross-platform and locale handling
22. Smart suggestions (the "Morvix noticed…" behaviors)
23. Full command reference
24. The project directory layout on disk
25. Configuration file formats (the schemas)
26. Optional capabilities and extension points
27. Glossary

---

## 1. What Morvix is (and is not)

### 1.1 The problem

At university, most programming courses **do not hand out test suites**. You finish your code, and you have no official way to know whether it's actually correct until it's graded. So students build their own checking setups: they write test cases based on *their own* solution and *their own* reading of the assignment, run their program against those cases, and then share the cases on GitHub so classmates can run the *same* inputs against *their* code and compare notes.

This is the crucial point about where "expected answers" come from. They are produced by **one student's own solution** and reflect **one student's interpretation** of the problem — there is no authoritative source. That is exactly why a shared test set is never guaranteed correct: the "truth" it encodes is a peer's, not the course's. The real value is comparison across many people: when lots of independent solutions agree with each other but disagree with one shared expected answer, that's strong evidence the *expected answer* (and the solution that produced it) is the thing that's wrong — not everyone else's code.

Building these harnesses by hand is repetitive and fiddly. The shell scripts differ subtly each time, break between Linux and macOS, and mishandle cases like "this malformed input is *supposed* to make the program crash." The work is redone from scratch for every assignment and every language, eating time that should go into solving the actual problem.

**Morvix automates the construction, execution, and sharing of these self-made test harnesses.** It does, quickly and consistently, what students already do by hand.

### 1.2 What Morvix is

- An **interactive command-line tool** (a persistent shell, similar in feel to a REPL) that a student uses to: import their solution, generate test cases, define how those cases are judged, build a runner, run the tests, produce a results report, and package everything to share.
- A **test-harness generator**. Its primary *output* is a self-contained package a classmate can run — even if that classmate has never heard of Morvix.
- A tool for **both sides** of the sharing exchange: the person who *creates and distributes* tests (the Author) and the person who *receives and runs* them (the Receiver). See §2.

### 1.3 What Morvix is not

- **Not an online judge or grading server.** It runs locally, offline. There is no submission, no leaderboard, no central authority deciding correctness.
- **Not an oracle of correctness.** This is the single most important honesty point, baked into every generated README (§17.4). The reference whose outputs define the "expected answers" is, in practice, **a peer's own solution** — not an authority. Passing 100% of the tests does **not** prove a solution is correct; it proves it agrees with that one reference on the cases tried. The genuine signal is statistical and social (§1.1, §13.5). Morvix surfaces this honestly rather than pretending to be a source of truth.
- **Not an AI tool.** There is no built-in model, no required network, no "magic." (An *optional, developer-supplied* LLM hook is described in §26 as an extension — bring-your-own key or local model, off by default, never required.)
- **Not Windows-first.** Linux and macOS are the primary targets because they share a bash/POSIX environment, so a generated runner behaves identically on both. Windows is supported on a best-effort basis (§21).

---

## 2. The two-sided model: Author and Receiver

Morvix exists to move a self-made test harness from one student to another. The two roles are:

### 2.1 The Author

A student who has a solution they believe works and wants to build tests from it and share them. Because the course usually provides no official tests, **the Author's own solution is the de facto reference** — the thing that defines the "expected" answers, with the standing caveat that this truth is one student's and therefore fallible. The Author:

1. Imports their solution into a Morvix project.
2. Configures how their language is built and run.
3. Generates and/or hand-writes test cases.
4. Decides how outputs are judged (comparison strategy, expected exit status, memory checks, resource limits).
5. Builds a **runner** — the executable artifact that compiles-and-tests a solution.
6. Runs the tests against their own solution to produce the **expected answers** and an optional results report.
7. **Packages** the harness — *without their own source code* — and shares it.

The package contains the tests, the expected answers (or hashes thereof), the runner, and a README. It does **not** contain the Author's solution source. The point is for the Receiver to test *their own* code against the Author's tests.

### 2.2 The Receiver

A student who downloads the package and wants to check their own solution. There are two sub-cases, and Morvix is designed so both work well:

- **Receiver without Morvix installed.** They unpack the package and run the runner directly (`./run.sh`, or the runner core). It compiles their code, runs all tests, compares against the bundled expected answers, reports pass/fail and timings, and can save a results file. They never need Morvix at all. *This is the common case and it must "just work."*
- **Receiver with Morvix installed.** The package also contains a Morvix manifest (a JSON descriptor). When the Receiver opens Morvix in the unpacked directory, Morvix reads the manifest and immediately understands the whole harness: which tests exist, how they're judged, what limits apply, what the runner does. They get the rich interactive view — inspect individual tests, see what's included, modify or extend, re-run selectively, diff their results against the Author's, and re-package. The manifest is a convenience layer for Morvix users, *on top of* the always-present plain runner.

### 2.3 Why the package is "code-free"

The Author's solution is the thing being kept private — it's their own graded work. The tests and expected answers are derived *from* it but don't contain it. The Receiver supplies their *own* solution and tests it against the Author's expectations. This is exactly the GitHub-test-repo pattern students already use, made one-command.

---

## 3. The core mental model: the project, and the four pipeline stages

### 3.1 The project

Everything Morvix does happens inside a **project** — a directory on disk holding one assignment's worth of state: configuration, generators, test cases, expected answers, runners, results, and the manifest. A project maps one-to-one to "one assignment." You `cd` into a directory and run Morvix; if a project exists there, Morvix loads it; if not, you initialize one.

State lives on disk (files and JSON), loaded into memory for the session and written back as you go. There is no database. The directory *is* the state, which is what makes it trivially shareable, inspectable, and version-controllable (you can `git` a Morvix project directly).

### 3.2 The four pipeline stages

Conceptually, work flows through four stages. Most commands belong to exactly one stage, which keeps the mental model clean:

1. **Define** — what language, how to build it, how to run it, how to judge it. (`config`, `import`, execution-model selection.)
2. **Generate** — produce test cases, either by hand, by random generators, or by analyzing the solution. (`gen`.)
3. **Run** — execute the solution against the cases under chosen limits, compare, and record. (`run`, `runner`.)
4. **Share** — assemble a report, a README, and a distributable package. (`result`, `package`.)

A **workflow** (§18) is simply a recorded sequence of these commands that can be replayed against a different solution.

---

## 4. System architecture (the layers, and why they're separated)

Morvix is built as a stack of layers, each depending only on the ones below it. The separation is not academic — it's what keeps the tool maintainable as features pile up, and what lets a single judging engine serve every language and every execution model.

```
┌─────────────────────────────────────────────────────────┐
│  Shell / CLI layer                                        │
│  REPL (live autocomplete) + one-shot parser. Same verbs.  │
├─────────────────────────────────────────────────────────┤
│  Shared interaction components                            │
│  selection list · single-choice · guided form ·          │
│  confirmation · live table · progress · message display   │
├─────────────────────────────────────────────────────────┤
│  Command layer                                            │
│  import / config / gen / run / runner / result /          │
│  workflow / package / help …                              │
├─────────────────────────────────────────────────────────┤
│  Orchestration layer                                      │
│  project state, generators, comparison, results, manifest │
├─────────────────────────────────────────────────────────┤
│  Execution-model layer        │  Comparison layer         │
│  stdio / library / args /     │  exact / ws / float /     │
│  file / interactive           │  hash / checker / exit …   │
├───────────────────────────────┴───────────────────────────┤
│  Language-adapter layer                                   │
│  C / C++ / NASM / Python / Java / Rust …                  │
│  build(source) → artifact ;  describe build/run env       │
├─────────────────────────────────────────────────────────┤
│  Process layer                                            │
│  spawn, feed stdin, capture stdout/stderr, apply rlimits, │
│  measure time/memory, enforce timeouts, set locale        │
└─────────────────────────────────────────────────────────┘
```

### 4.1 The central design principle: three orthogonal axes

The whole tool is the product of keeping three concerns independent:

- **Language adapter** — *how to turn source into something runnable* (compile flags, interpreter, linker). Knows nothing about tests.
- **Execution model** — *how a runnable thing is invoked and what counts as its observable behavior* (does it read stdin and write stdout? is it a library linked into a harness? does it take argv? does it write to a file? does it converse with a judge?). Knows nothing about which language.
- **Comparison strategy** — *given observed behavior and a reference, how do we decide pass/fail* (byte-exact, whitespace-insensitive, float-tolerant, hashed, custom checker, expected exit status). Knows nothing about language or execution model.

A C program can be `stdio`-judged-byte-exact, or `library`-judged-by-valgrind, or `args`-judged-float-tolerant. Because the three axes are independent, supporting a new language is "write one adapter," supporting a new way of running is "write one execution model," and supporting a new way of judging is "write one comparator" — none of them multiply against each other. **This is the architectural decision that everything else hangs on.** If these three were tangled together, every feature would have to be re-implemented per language and the tool would collapse under its own option count.

### 4.2 The second design principle: one shared interaction layer

Every interactive moment in the CLI — picking which tests go in a package, choosing an archive format, answering a multi-field setup, confirming a destructive action, watching a run, reading an error — is rendered by a **shared component** defined once and reused everywhere (§6). No command re-implements selection, prompting, or message display. This guarantees the CLI feels identical everywhere: a behavior learned in one place transfers to every other, and there is one place to fix or improve any interaction.

### 4.3 Why Python is the implementation language

Morvix itself is written in **Python 3**. The reasoning:

- Morvix's own job is *orchestration* — it spends nearly all its wall-clock time waiting on external compilers (`gcc`, `nasm`, `javac`, `rustc`) and on the program under test. The interpreter's raw speed is irrelevant; the subprocess it launches dominates by orders of magnitude. Optimizing Morvix's own footprint would be polishing a doorknob next to a vault.
- The standard library already contains the hard parts: `subprocess` (spawning), `resource` (rlimits on POSIX), `tempfile`, `tarfile`/`zipfile` (packaging), `hashlib` (hash comparison), `difflib` (diffs), `argparse` (one-shot parsing), `json`.
- The interactive shell with live autocomplete and the shared interaction components are well served by the `prompt_toolkit` library (§5, §6).
- Colored tables and progress output are well served by `rich`.
- The closest existing reference tool, `online-judge-tools` (`oj`), is Python — so its proven patterns can be borrowed directly.
- The runner core that ships *inside packages* is also stdlib-only Python 3, which is present on essentially every Linux/macOS machine with zero install (§16).

### 4.4 External dependencies

Kept deliberately small. For Morvix itself: `prompt_toolkit` (interactive shell and components) and `rich` (output formatting). Configuration is JSON throughout, so no extra parser is needed; everything else is standard library. The **runner core that ships in packages has zero third-party dependencies** — stdlib only — so a Receiver never installs anything.

---

## 5. The interactive shell (REPL) and the one-shot mode

### 5.1 Two ways to invoke, one set of commands

Morvix is **hybrid**: it works as a persistent interactive shell *and* as a one-shot command-line tool, using the **same command vocabulary** in both. There is no separate "REPL language" and "CLI language" to maintain — one parser, two entry points.

- **Interactive (REPL).** You run `morvix` with no command and land in a prompt. You type commands, they execute, the session stays alive holding project state, and you keep going. This is the primary, intended way to use it — the place where live autocomplete, the shared components, and suggestions make the experience fast.
- **One-shot.** You run `morvix run --all --time` (for example) from your normal shell; Morvix executes that single command and exits. This is what scripts, Makefiles, CI, and muscle-memory power-users use. It's also what a recorded workflow replays.

Whatever you can do interactively, you can do one-shot, and vice versa.

### 5.2 The banner

On launching the interactive shell, Morvix prints a banner — the kind of ASCII identity block typical of interactive CLIs — containing the name **MORVIX** and the attribution **"by Krzysztof Adamczyk"**, plus the version and a one-line hint (e.g. "type `help` to begin"). This is cosmetic but expected; it's the first thing a user sees.

### 5.3 The prompt and command style

- The prompt is clean — `morvix ❯ ` (exact glyph configurable) — with **no slash prefix**. The slash convention in AI tools exists to distinguish typed *commands* from typed *natural-language prompts*; Morvix has no natural-language input, so every line is a command and a slash would be a meaningless extra keystroke. Decision: **no slash.**
- Commands are **flat and unique** — `import`, `config`, `gen`, `run`, `runner`, `result`, `workflow`, `package`, `help`, `exit`, etc. Flat (not namespaced like `test gen`) because the verb set is small enough to stay unambiguous, and flat names are faster to type and to autocomplete. The same flat verbs take flags in one-shot mode (`morvix gen --random --count 1000`).

### 5.4 Live autocomplete with inline descriptions

As you type (live, not only on Tab — with a small debounce so it isn't jittery), Morvix shows a completion menu. Each entry has the **command (or option) name on the left and a short description on the right**, wrapped to at most two lines, column-aligned so the description never collides with the name. Conceptually:

```
┌──────────────────────────────────────────────────────────────────┐
│ package        Bundle tests, runner, expected answers and README   │
│                into a shareable archive (zip or tar).               │
│ result         Produce or export a results report from the last     │
│                run; share as JSON or Markdown.                      │
│ runner         Create / edit / inspect a runner profile.            │
└──────────────────────────────────────────────────────────────────┘
```

This is implemented with `prompt_toolkit`'s completion system (the right-hand description is its `display_meta` field). The autocomplete is **context-aware**: after you type a command, it completes that command's *options*; where an option expects a value, it suggests the kind of value (a file name, a test name, a runner name, a language, an enum of valid choices). The user is always shown what to type where.

### 5.5 Help, everywhere

`help` lists all commands with descriptions. `help <command>` explains one command, its options, examples, and which pipeline stage it belongs to. The same descriptions power both `help` and the autocomplete meta column — single source of truth, so they never drift apart.

### 5.6 History and session niceties

Command history persists across sessions (per project and global). Standard line-editing (arrow keys, search-back, clear). The bottom of the screen carries a status toolbar (current project, current solution under test, selected runner) so you always know the context you're operating in.

---

## 6. Shared interaction components (the consistent UI layer)

Every interactive moment in Morvix is built from a **single shared set of components**, defined once and reused by every command. This is a hard rule, not a preference: a command never hand-rolls its own selection menu, its own question flow, or its own error box. The payoff is consistency — the same keys do the same things everywhere, and any interaction the user learns once works identically in every other command. It also means each interaction pattern has exactly one implementation to build, fix, and refine.

The components below are the complete toolkit. Each command composes from these; none invent their own.

### 6.1 Selection list (multi-select)

A scrollable list of items the user toggles on/off. Used wherever the user picks **several** things out of many: which tests or test groups go in a package, which runners to include, which generators to bundle, which cases a run should cover.

Navigation and behavior:

- **Up/Down** moves the cursor; **Space** toggles the item under the cursor.
- **Bulk operations are first-class**, because selecting among thousands of tests by hand is unacceptable: select **all**, select **none**, **invert** selection; select an entire **group** at once; select by **glob/pattern** (e.g. `tricky/*`); **range** select (mark a start, extend to an end). 
- **Type-to-filter**: start typing to narrow the visible list, then apply a bulk operation to just the filtered subset.
- A persistent **count** is shown (e.g. "847 of 1000 selected"), so the user always knows the scope of what they're about to act on.
- **Enter** confirms; **Esc** cancels.

This is the component your packaging flow uses to choose contents, and the one a Receiver uses to choose which tests to re-run.

### 6.2 Single-choice list

Pick exactly **one** option from a set. Used for: archive format (zip / tar / tar.gz / tar.xz), default comparison strategy, runner backend, execution model. Up/Down to move, Enter to choose. Visually consistent with the selection list, minus the multi-toggle.

### 6.3 Guided form (multi-field navigable prompt)

For any setup that asks **several related questions at once** — most importantly `config <language>`, `runner new`, and `init`. Rather than a rigid one-question-at-a-time interrogation, the user moves freely:

- **Left/Right** switches between fields (questions).
- **Up/Down** changes the value of the current field when it's a choice; fields can also be free-text (typed) or numeric.
- Fields can have defaults pre-filled (from global config), can be revisited and changed before submitting, and validate inline.
- **Enter** submits the whole form; **Esc** cancels.

This is the navigable, arrow-driven multi-question pattern (move between questions horizontally, between a question's options vertically) used consistently for every multi-field setup. One implementation; every configuration screen reuses it.

### 6.4 Confirmation

A clear yes/no (or accept/decline) prompt. Used for destructive actions (`clean`, overwriting a runner) and to deliver the **smart suggestions** of §22 ("output is large — switch this group to hashing? [y/N]"). Defaults are shown explicitly and chosen safely (destructive actions default to "no").

### 6.5 Live results table

The colored, updating table that shows a run in progress and its outcome (§17.2): per-case status, timing, memory, verdict, with per-group and overall summaries. Built on `rich`. It is itself a shared component — every command that shows results uses this one table, not a bespoke variant.

### 6.6 Progress indicator

For long-running operations — generating thousands of cases, a stress-test loop, running a large suite — a consistent progress display (counts, elapsed, current item, cancellable). Reused everywhere a long operation runs.

### 6.7 Message display

The single rendering path for all informational, success, warning, and error output (§7). Every message in the tool goes through it, so warnings always look like warnings and errors always look like errors, everywhere.

### 6.8 Plain / non-interactive fallback

Every component degrades gracefully when there's no interactive terminal (piped output, CI, the one-shot path): selection becomes flags, forms become flags, the live table becomes plain text, colors switch off. The same command works interactively and scripted; the components simply render in their non-interactive form.

---

## 7. Errors, warnings, and messages

Because students will hit compiler errors, missing tools, malformed commands, and crashing programs constantly, the quality of error and warning display is a first-class feature, not an afterthought. All of it flows through the shared message-display component (§6.7) so it's uniform everywhere.

### 7.1 Errors

- **Clearly marked** — distinct color and a leading marker so an error is unmistakable at a glance.
- **State what failed, why, and the fix** — not just "error," but what was attempted, what went wrong, and the next action. A bad flag points at the correct flag; a missing compiler says which tool to install; an unreadable file gives the path.
- **Compiler/assembler/linker diagnostics are surfaced verbatim** — when a build fails, the toolchain's own output is shown unmodified (that's the information the student actually needs), framed by Morvix's note of which build command produced it.
- **No raw stack traces at the user.** Internal Morvix failures are translated into actionable messages; the raw Python traceback is available only under a debug/verbose flag, never dumped by default.
- **Errors are categorized** so the message can be appropriately specific: *user errors* (bad command, bad flag, bad path), *environment errors* (compiler/interpreter/tool missing, permission denied), and *run failures* (the program under test crashed, timed out, or exceeded a limit — which may itself be an *expected* outcome per §14.6, in which case it is not reported as an error at all).

### 7.2 Warnings

- **Visually distinct from errors** and **non-blocking** — a warning informs and lets the operation continue.
- Used for advisory situations: an imprecise runner backend was chosen for metrics that need a precise one (§16.3); the deterministic locale default is in force (§21.3); a setting was overridden by a higher-precedence source; a tool needed for an optional feature (e.g. valgrind) isn't installed so that feature is skipped.
- The **smart suggestions** of §22 are delivered as warnings paired with a confirmation (§6.4): Morvix explains the situation, suggests the better option, and lets the user decide — it never changes behavior silently.

### 7.3 Success and info

Consistent, low-noise confirmations for completed actions (a package written, a workflow saved), and plain informational notes. The tool is not chatty; it reports what matters and stays quiet otherwise.

---

## 8. Languages under test

Morvix can build and run solutions written in several languages. Each is supported through a **language adapter** — a small module that knows how to turn that language's source into something runnable, and what its build/run environment needs.

### 8.1 Supported languages

- **C** — compiled with `gcc` (configurable: compiler, standard e.g. `gnu23`, flags, libraries, include paths).
- **C++** — compiled with `g++`/`clang++` (configurable: standard e.g. `c++20`, optimization, flags).
- **NASM (x86-64 assembly)** — assembled with `nasm` (e.g. `-f elf64`), then linked. Two linking modes are both supported because both occur in real coursework: **pure `ld`** (syscall-only programs, no libc) and **`gcc`-linked** (programs that call libc). Which one is a per-project config choice.
- **Python** — run with a configured interpreter (system, or a specific virtual environment's `python`). "Build" is a no-op or an optional syntax check.
- **Java** — `javac` to compile, `java` to run; classpath, source/target version configurable.

### 8.2 Rust

**Rust** uses the identical adapter pattern — `rustc` for single-file assignments, `cargo` for project-style ones, with edition and release/debug configurable. It is the next language adapter to add; nothing else in the system changes to accommodate it, which is the point of the adapter design.

### 8.3 The adapter contract

Every adapter exposes the same small interface to the layers above it:

- **build(source, config) → artifact** — compile/assemble/link, or no-op for interpreted languages. Returns a runnable artifact (a binary, a `.class`, a script path) or a build error with the compiler's diagnostics surfaced verbatim (§7.1).
- **run-spec(artifact, config) → how to invoke** — the command and environment needed to actually execute the artifact (interpreter prefix, `LD_LIBRARY_PATH`, classpath, etc.). The process layer consumes this; the execution model decides *how* to drive it.
- **describe() → text** — human-readable summary used in help, READMEs, and manifests ("C, gcc, -std=gnu23, -O2").

Because the adapter is the only language-aware part of the system, **adding a language is writing one adapter** — nothing else changes. The escape hatch in §9.3 (raw build command) means even a language without a dedicated adapter can be used immediately.

---

## 9. The `config` system

### 9.1 Purpose

Compiling C++ with the right standard and flags, pointing at the right Python venv, choosing NASM's link mode — these are language-specific settings you'd otherwise retype constantly. The whole point of Morvix is to *stop* retyping them. The `config` system captures them once.

### 9.2 How it works

`config <language>` opens the **guided form** (§6.3) for that language in the current project — or sets values directly via flags in one-shot mode:

- `config cpp` — compiler, standard, optimization level, extra flags, include/library paths.
- `config python` — interpreter / virtual-environment path.
- `config nasm` — object format, link mode (`ld` vs `gcc`), extra assembler/linker flags.
- `config java` — `javac`/`java` paths, classpath, source/target version.
- `config rust` — `rustc`/`cargo`, edition, release vs debug.

`config` with **no language** sets the project-wide *judging* defaults instead, so they can be changed (and baked into a shared package) without hand-editing JSON: `--compare <strategy>` (with `--checker`, `--epsilon-abs`, `--epsilon-rel`) and the default limits `--wall`/`--cpu`/`--memkb`/`--output-kb`. Previously these were reachable only at `init` or per-run.

Settings are stored as JSON in the project (§25). There is also a **global config** for personal defaults (your usual C++ standard, your preferred color theme, your default Python) that every new project inherits and can override. Order of precedence: explicit command flags **>** project config **>** global config **>** built-in defaults.

### 9.3 The raw-command escape hatch

Real coursework sometimes needs a build that no preset captures — a specific `Makefile` target, an unusual link line, a multi-step build. So in addition to the structured presets, Morvix accepts a **raw build command** and a **raw run command** per project. If set, Morvix uses exactly what you give it instead of inferring. This guarantees Morvix can handle anything the developer could do manually, while the presets keep the common cases one-word-simple. (This reflects real repos: one studied harness compiles with a hand-written `gcc tests/test*.c --std=gnu23 -L. -lrstack -o tester` line — exactly what the escape hatch exists for.)

Raw commands travel in the package manifest, which means a Receiver who runs such a package would be executing the *author's* shell commands, not just their own solution. The shipped runner therefore refuses a raw package until the Receiver passes `--allow-raw`, always shows the commands verbatim before running them, and `open` warns at adoption time. Raw commands need a POSIX shell and are reported as unsupported on Windows.

### 9.4 Everything configured is replayable

Every setting set via `config` is recordable into a workflow (§18) and serialized into the package manifest (§20), so a configured project can be replayed against another solution or understood by another Morvix user without re-entry.

---

## 10. Execution models (how a program is invoked and judged)

Programs are not all "read stdin, write stdout." Morvix supports **five execution models**, selectable per project (and a project can mix them per test group where it makes sense). The execution model is independent of language (§4.1). All five are part of the tool.

### 10.1 `stdio` — standard input/output

The classic model. The program is fed an input on **stdin** (or a named input file), and its **stdout** is captured and compared to the expected output. Exit status is also captured. This covers the majority of algorithmic assignments. A single test case can supply **multiple named input streams/files** (one studied harness uses two per case — an `.n` file and a `.stdin` file), so the model supports more than one input artifact per case (§12).

### 10.2 `library` — link-and-assert

The "program" is not an executable but a **library** (e.g. a C `.so` with a header). The test is a **harness source file** that links against the library, calls its functions, and asserts on the results; pass/fail is the harness's exit status, optionally combined with a memory check (§15). This requires compiling the harness against the library, setting `LD_LIBRARY_PATH` (or platform equivalent), and running under an optional memory checker. This model is common in C coursework (one studied repo is exactly this: a `.so` library + compiled C test files + valgrind). Without it, Morvix would be useless for a large fraction of C/assembly assignments.

### 10.3 `args` — command-line arguments

The program takes its input as **argv** rather than stdin, and its output is stdout (or an exit code, or a file). Selectable for assignments built around argument parsing.

### 10.4 `file` — file in / file out

The program reads from and/or writes to **named files** on disk rather than stdio; comparison targets the produced output file (`output.txt` by convention). This matters for the "expected to write a file" case, and pairs naturally with the crash/exit checks of §14.6.

### 10.5 `interactive` — back-and-forth

The program **converses** with a judge process: the judge sends something, reads the program's reply, sends the next thing based on that reply, and so on (adaptive/interactive problems). Morvix supports a custom interactor program supplied by the Author (the `interactor` key in the project config; its exit code is the per-case verdict).

### 10.6 Extensibility

Execution models are pluggable, like adapters and comparators. New models can be added without touching languages or comparators.

---

## 11. Importing code under test

### 11.1 What "import" does

`import <path>` registers a solution as the code currently under test in the project. Two modes, the user's choice:

- **Reference (point-at)** — Morvix remembers the path and uses the file in place. Good while you're actively editing the solution.
- **Copy-in** — Morvix copies the source into the project (under a `solutions/` area). Good for capturing a frozen reference, or for the Receiver dropping in their own code.

### 11.2 One solution at a time, switchable

A project tests **one solution at a time**, but switching is a one-liner: `import other_solution.cpp` and everything else — tests, expected answers, comparison rules, runner, limits — stays exactly as configured. There is deliberately **no multi-solution mode**, because "compare two solutions" reduces to "import one, run, import the other, run, diff results" without any extra machinery. This is also precisely how a Receiver uses the tool: they `import` their own file into a received project and re-run; nothing else changes. Keeping it single-solution keeps the model honest and simple.

### 11.3 The solution defines the answers

For generation and comparison, the **solution under test** is also what *defines* the expected answers — there is no separate "reference" to register. In practice this is the Author's own solution, since no official answers exist; its "truth" is therefore one student's and fallible (§1.3). The expected answers (or their hashes) are computed by running the solution over every case (`gen --expected`), then frozen into the project and the package. After that, comparison needs neither the source nor any network — the frozen answers travel inside the package. (To freeze answers from a *different* solution, import it, run `gen --expected`, then import your own back.)

### 11.4 The stress oracle (for stress testing)

For stress testing (§13.4) the user can register a **rival tagged `--stress`** — typically a slow brute-force solution trusted *because* it's simple (`rival add brute.c --stress`). Stress testing generates a random input, runs both the solution and the oracle, and flags any disagreement. The oracle is an authoring aid; its source is **not** shipped in the package. (A rival is otherwise a performance-comparison solution, §16.)

---

## 12. Test cases: structure and storage

### 12.1 What a test case is

A test case is a named bundle of:

- **Inputs** — one or more named input artifacts (e.g. an `.in`/`.stdin`, or several named files, or argv, depending on execution model). Supporting *multiple* named inputs per case is required (one studied harness uses two).
- **Expected behavior** — depending on comparison strategy: an expected output (full text), or an expected **hash** of the output, or "expected to crash / expected exit status N / expected signal," or a custom-checker verdict. A case can combine these (e.g. "exit 0 *and* output matches").
- **Metadata** — its group (§12.3), whether it's manual or generated, and any per-case limit overrides.

### 12.2 Manual vs generated cases

- **Manual** cases are hand-written and **permanent** — they survive regeneration. (One studied repo marks these `*manual.*` and its clean script preserves them.)
- **Generated** cases are produced by generators and are **disposable** — a "clean" operation removes them so they can be regenerated deterministically (from a seed) without bloating the repo. Generated cases are typically git-ignored; manual cases are committed.

### 12.3 Test groups / categories

Cases can be organized into **named groups** by intent — mirroring real practice, where one studied repo split tests into baseline, bad-input, small-correctness, and tricky groups. Groups let a runner select "run only the bad-input group" or "time only the big group," let the selection list (§6.1) select a whole group at once, and let the report break results down by category. Groups are a labeling/selection convenience layered on the flat case pool.

### 12.4 Storage

Cases live as files in the project's `tests/` area, grouped into subdirectories. Expected answers (full outputs or hashes) live in a parallel `expected/` area. Everything is plain files so it's inspectable, diffable, and git-friendly. The manifest indexes them for Morvix's rich view, but the files are the truth.

---

## 13. Test generation

Generation is the part that genuinely cannot be *fully* automated — the tool can produce inputs, but the *correct answer* for an input has to come from a reference solution, not from thin air, and that reference is a peer's own solution (§1.3). Morvix is honest about that boundary and makes everything around it fast.

### 13.1 The generator model

A **generator** is a program that prints a test input to stdout, parameterized by arguments and a **seed** (so generation is reproducible). Generators can be written in **any supported language** — Python is the common choice, but following the studied repos' escape hatch, a generator in C/C++/Rust is built and run the same way. One generator can expose multiple modes (e.g. "emit the `.n` file" vs "emit the `.stdin` file") and many on/off knobs, so a single rich generator can cover a whole family of cases — the "one generator with lots of functionality, toggled" approach.

### 13.2 Built-in random-data library

So you don't write a generator from scratch for trivial shapes, Morvix ships a built-in library of common random-data primitives, parameterized and seeded:

- integers and integer ranges; arrays/sequences of given length and value bounds
- strings over a chosen alphabet/charset; lengths and patterns
- permutations; sorted / reverse-sorted / nearly-sorted sequences
- trees (random, path-like, star-like, by degree); graphs (directed/undirected, weighted/unweighted, connected, DAGs); grids
- edge-case templates: empty input, single element, maximum-size input, all-equal, boundary values

These are composable building blocks; a generator picks and combines them. The list is meant to grow to match the assignment families actually encountered.

### 13.3 Expected-answer generation

Once inputs exist, expected answers are produced by running the **solution under test** (§11.3) over every input and freezing the result — as full output, or, on your opt-in, as a **hash** (§14.5, §22). For the crash/file models, "expected behavior" is the solution's observed exit status / produced file. This is the step that turns raw inputs into a judged test set.

### 13.4 Stress testing (the bug-finding mode)

The highest-value generation mode. In a loop: generate a random input → run the real solution → run the **stress oracle** (a `--stress` rival, §11.4) → compare. On the first disagreement, Morvix **saves the failing input** as a permanent regression case and reports it. Running thousands of random cases this way finds bugs no fixed test set will, because the oracle is simple enough to trust. This is differential testing, and it's mostly tool-provided once an oracle exists.

### 13.5 Cross-solution agreement (the "many people, same result" signal)

This is the actual mechanism by which correctness is triangulated given there is no official answer (§1.1). When *many independent* solutions are run against the same generated set and they **all agree** on a case but **disagree with the expected answer**, that is evidence the *expected answer* (and the reference that produced it) is wrong — not the solutions. Morvix can't gather other people's runs by itself, but it makes this explicit: results are shareable (§17), the README states it honestly (§17.4), and the manifest lets a Morvix-equipped Receiver diff their per-case results against the Author's so disagreements are visible. Agreement across implementations raises confidence; it never *proves* correctness (§1.3).

### 13.6 Input/output and code-aware assistance

You raised the idea of a generator/analysis that "looks at the provided code and tries to match tests to it." Scoped honestly: Morvix can offer **heuristic input/output scaffolding** — inferring input *shape* from how the program reads (e.g. it reads an int then that many lines), proposing boundary cases around the limits it detects, and seeding the crash-case generator with malformed variants of valid inputs (truncated, oversized, wrong-type, extra-whitespace). This is *assistance that proposes candidate cases*, never an oracle for their answers — the answers still come from running the solution. The firm line is that Morvix never invents a correct answer it can't derive by running a solution. (An optional, developer-supplied LLM could later draft candidate edge cases under this same "propose, don't oracle" rule — §26.)

### 13.7 The generation toolkit (the practical surface)

The model above is realised as a single `gen` command with many input sources, all sharing the one rule — **they produce inputs only; expected answers come solely from `gen --expected`** (enforced by a static guard, `tests/test_honesty.py`). The command reference in the generated `GUIDE.md` is authoritative; the categories are:

- **Describe-don't-code:** a declarative **grammar** (`--grammar`/`--new-grammar`, `morvix/grammar.py`) samples correct-by-construction structured input, with counts that drive repetition ("N then N numbers", "R C then an R×C grid"). A vetted **catalog** (`--lib`/`--list-lib`, `morvix/catalog.py` over `morvix/genlib.py`) gives ready-made trees/graphs/etc.
- **Richer random:** distribution control and a difficulty dial (`--dist`/`--difficulty`, `morvix/distributions.py`) and worst-case **adversary** shapes (`morvix/adversaries.py`).
- **Deliberate coverage:** the **bound-spec** mini-language (`--axis`, `morvix/boundspec.py`) feeds boundary-value (`--boundary`), bounded-exhaustive (`--exhaustive`), and pairwise/t-wise (`--pairwise`) generation; `--multi` wraps multi-test files and `--ladder` sweeps sizes.
- **Failure tooling:** `--stress` (vs a `--stress` rival oracle) and `--crash` (triaged) both auto-**shrink** (`morvix/shrink.py`); `--shrink` minimises any failing case.
- **Oracle-free checks:** **metamorphic** relations (`--metamorphic`, `morvix/metamorphic.py` — a relation between two of the solution's own outputs), a **property** oracle (`--property`), and diversity-guided **fuzz** (`--fuzz`).
- **From real data:** `--import` (answers stripped), `--infer` (drafts a generator from samples), `--mutate` (structure-aware corpus mutation).
- **Integrity:** input **validators** (`--validate`), answer-stability (`--expected --check-stable`), incremental recompute (`--changed`), and **snapshots** (`--pin`/`--diff-pin`); every case records its provenance.
- **Model-assist (off by default, §26):** `--suggest` runs a developer-supplied hook; output is treated as unverified input/generator code only (`morvix/assist.py`).

---

## 14. Comparison strategies (how "correct" is decided)

Comparison is a **menu of selectable strategies**, chosen per project (and overridable per test group or per case). The execution model determines *what* is observed; the comparison strategy determines *how it's judged*. All of the following are first-class options.

### 14.1 Exact (byte-for-byte)

Output must match the expected bytes exactly. Strictest; used when format is rigidly specified.

### 14.2 Whitespace-insensitive

Trailing whitespace trimmed, runs of spaces/newlines normalized before comparison. The sane default for most text output, where "two spaces vs one" shouldn't fail a correct answer.

### 14.3 Float-tolerant

Numeric tokens compared within an absolute and/or relative epsilon. Required for any assignment producing floating-point results, where exact bytes are meaningless. Epsilon is configurable.

### 14.4 Custom checker (special judge)

When **multiple outputs are valid** (any shortest path, any valid permutation, any correct factorization), exact comparison is wrong. The user supplies a **checker program** that receives the input and the candidate output and decides accept/reject. Morvix runs the checker instead of diffing. This is the standard "special judge" mechanism.

### 14.5 Hash

Instead of storing and comparing full expected output, store and compare a **hash** of it. Essential when output is enormous (one studied assignment produces strings via `"text" * 1000000` — storing full expected output is infeasible; a hash is tiny). Trade-off, stated plainly: a hash gives OK/FAIL but **no diff** on failure. Morvix therefore treats hash as **opt-in**, and when it detects output exceeding a size threshold it **suggests** switching (§22) rather than switching silently — silent switching would surprise the Receiver and break the ability to diff.

### 14.6 Expected exit status / crash

A first-class outcome, not an afterthought: a case can expect the program to **exit non-zero, or crash with a specific signal** (e.g. segfault on malformed input). For C/assembly especially, "rejects bad input by crashing" is sometimes the *correct* behavior. One studied harness explicitly encodes "crash is the expected behavior." So every case carries an **expected exit status / signal** dimension, checkable on its own or combined with output matching. When a crash is the expected outcome, it is judged as a pass, not reported as an error (§7.1).

### 14.7 Combinations

Strategies combine. A case can require "exit 0 AND output matches (whitespace-insensitive) AND no memory errors (§15)." The judge evaluates each enabled dimension and the case passes only if all pass. This compositionality is why the dimensions are kept separate rather than baked into one monolithic "compare" step.

---

## 15. Resource limits and memory-correctness

Two distinct concerns that are easy to conflate but must be separated: **how many resources a run is allowed to use** (limits), and **whether the program's memory behavior is correct** (memory-correctness). Both are toggleable per runner — that toggleability is the entire point of the runner abstraction (§16).

### 15.1 Resource limits (measure and/or enforce)

For each run, Morvix can **measure** and optionally **enforce hard caps** on:

- **Wall-clock time** — elapsed real time; a timeout kills the run and marks it as timed-out.
- **CPU time** — processor time consumed (separate from wall time; relevant under load).
- **Peak memory** — peak resident set size. Stated honestly: this is **approximate** (via `getrusage`/`/usr/bin/time`-style measurement on POSIX). Truly precise accounting needs cgroups, which Morvix does not require for coursework. The report labels memory as "peak, approximate."
- **Hard memory kill** — an enforced cap (`ulimit`-style address-space limit) that *kills* a run exceeding it, so a runaway or leaking program (e.g. one that never frees) is terminated rather than hanging the machine. This is enforcement, distinct from the correctness check below.
- **Output size cap** — guards against a program spewing unbounded output.

All caps are configurable, can be set globally for a runner or overridden per test group/case, and every chosen value is **recordable into a workflow** so "the limits I used" travel with replay.

### 15.2 Memory-correctness (a judged dimension)

Separate from "how much memory," this is "did the program use memory *correctly*" — no leaks, no invalid reads/writes, no use-after-free. For C/C++/assembly, Morvix can run the program under a **memory checker (valgrind/memcheck)** as a toggleable pass whose verdict becomes part of pass/fail. One studied repo does exactly this — valgrind on by default, leaks count as failure — and exposes it as a runner toggle alongside a diff toggle. Morvix generalizes that: a runner can switch the memory-checker pass on or off, and the report shows memory-correctness as its own column.

### 15.3 Why these are runner toggles

A given assignment cares about different things: an algorithms task cares about time; a memory-management task cares about leaks; a parsing task cares about crash-on-bad-input. Rather than one rigid behavior, the **runner** (next section) bundles a chosen set of these toggles, so the user builds exactly the runner the assignment needs — and the Receiver runs that same configured behavior.

---

## 16. Runners (the shareable execution artifact)

### 16.1 What a runner is

A **runner** is the concrete, shareable thing that *executes the tests*. It's what the Receiver actually runs. The user **builds** a runner (via the guided form, §6.3) by choosing: which tests/groups it covers (via the selection list, §6.1), which comparison strategy, which limits, whether timing is reported, whether the memory checker runs, output verbosity, color scheme, and any flags. A runner is a *named profile* configured once and re-invokable and re-shareable.

### 16.2 The two-file form (and why it isn't a single bash script)

A pure-bash runner that also measures peak memory, enforces hard caps, runs valgrind, handles float/hash/checker comparison, manages `LD_LIBRARY_PATH`, and behaves *identically* on Linux and macOS becomes a large, fragile script — and cross-platform bash differences (`time`, `ulimit`, `stat`, `sed`) are exactly the breakage to escape. So the runner is **two pieces**:

- **A portable runner core** — a single, self-contained **Python 3 script, stdlib-only**, that does the real work: build the solution (via the recorded build command/config), run each case under the chosen limits, apply the chosen comparison, optionally run the memory checker, and write results. Python 3 is present on essentially every Linux/macOS machine, handles rlimits/locale/subprocess robustly, and is one file with zero install.
- **A thin `run.sh` wrapper** — locates a Python 3 interpreter and invokes the core, so the Receiver's habitual `./run.sh [args]` works exactly as expected. The wrapper passes through the same on/off arguments (which tests, valgrind on/off, diff on/off, etc.) the studied repos use.

The Receiver thus gets familiar `./run.sh` ergonomics **and** correct, portable measurement — without installing Morvix.

### 16.3 Per-language runner capabilities (honest about what each can do)

What a runner can measure depends on the toolchain, and Morvix says so. Different runner backends offer different functionality, and Morvix is upfront about the trade-offs rather than pretending every backend is equal:

- **bash backend** — `run.sh` doing the work directly, no Python. The most portable, but Morvix states clearly it is **not precise for timing/memory** (shell-level `time` is coarse, peak-memory is unreliable across platforms). It gets the job done for pass/fail and rough timing. Offered because most people expect a `.sh` and many assignments only need OK/FAIL.
- **Python-core backend** — the recommended choice for anything needing real numbers: proper per-run timing, approximate peak memory via `getrusage`, hard caps via `setrlimit`, structured results. Still zero-install for the Receiver.
- **valgrind-augmented** (C/C++/asm) — adds memory-correctness verdicts; only meaningful where valgrind applies.

When the user builds a runner, Morvix shows which capabilities the chosen backend supports and which it can't (a warning per §7.2), so the choice is informed. (E.g. "You picked the bash backend; peak-memory will be reported as ‘n/a’ — use the Python backend for memory metrics.")

### 16.4 Results built into the runner

Every runner can **write a results file** (§17) when it runs — so the Receiver's run automatically produces a shareable report, with no extra step. This is what makes "run it and send me the results" a single action.

### 16.5 Multiple runners per project

A project can hold several named runners — e.g. a fast `quick` runner (whitespace compare, no valgrind, no timing) for iteration, and a thorough `full` runner (exact compare + valgrind + timing + memory caps) for final checking. The selection list (§6.1) chooses which runner(s) to package.

---

## 17. Results and reporting

### 17.1 What a result is

After a run, Morvix has, per case: pass/fail, the comparison verdict (and a diff when available — not for hash compares, §14.5), exit status/signal, wall time, CPU time, approximate peak memory, memory-checker verdict (if run), and timing/aggregate stats per group and overall.

### 17.2 Live view (interactive)

In the shell, results render through the shared live table component (§6.5): per-case status, timings, and summary counts, updating as the run proceeds. Color and verbosity are configurable (and disabled automatically for plain terminals/CI). The summary ends with a **failure-mode rollup** — `Failures: wrong output 953, crashed 480` — so a big run tells you *how* it failed at a glance rather than only *that* it failed. `run --quiet` (and the shipped runner's `--quiet`/`--summary-only`) prints just that summary block, not the per-case stream, which keeps a thousand-case suite readable.

### 17.3 Saved/exported results

Results can be saved and shared. Formats:

- **JSON** — the canonical machine-readable form, ideal for a Morvix-equipped Receiver to diff against the Author's results, and for cross-solution agreement analysis (§13.5).
- **Markdown** — the human-readable report (the default for a written report), with a summary table and per-group breakdown.
- **Plain text** — for minimal environments. (Markdown is the default; plain text is the option.)

The runner itself can emit these automatically (§16.4), so "here are my results" is a file the Receiver already has after running.

### 17.4 The auto-generated README and its honesty clause

When packaging (§19), Morvix assembles a **README** from canned fragments keyed to the choices made — each runner option, comparison strategy, and execution model contributes one or more pre-written sentences describing what it does and how to use it. This is the "README built as you go" idea: pick the pieces, and the prose assembles itself (Markdown by default, plain text optional). The README always includes how to run the package (with and without Morvix), what the tests cover and how they're judged, the limits and checks in force, and a **standard correctness disclaimer** — the universal note every studied repo writes by hand: *these tests come from one student's own solution and one interpretation of the assignment; there is no official answer key; passing all tests does not prove correctness; widespread disagreement across many independent solutions is the real signal that a test may be wrong.* This fragment is included by default because it's true and because every real harness says it.

### 17.5 The README is template fragments, not a content system

To be explicit about scope: README assembly is **string templates keyed to chosen options**, concatenated into Markdown. It is deliberately *not* a general content-management or "blog" system. One fragment per feature, assembled in order.

---

## 18. Workflows (record-and-replay automation)

### 18.1 The idea

A **workflow** is "a Makefile, but for tests/generation/running" — a saved, ordered sequence of Morvix actions that can be **replayed**, including against a *different* solution. It turns "the twelve things I did to set up this assignment's tests" into one repeatable unit you can reuse next week on the next assignment, or hand to someone else.

### 18.2 How it's represented

A workflow is **a recorded list of Morvix commands** (the same command strings you'd type), with their arguments, stored as **JSON**. This is deliberately not a new invented language: because a workflow is just recorded commands, **anything Morvix can do is automatically workflow-able**, with no per-feature work — including every config setting, every limit, every comparison choice (options are just arguments on the recorded commands, so "any option I use is saved in my workflow" falls out for free).

### 18.3 Recording and editing

- **Record mode** — Morvix captures what you do as you do it, producing the workflow automatically.
- **Manual edit** — because it's plain JSON of readable commands, you can hand-edit, reorder, parameterize, and trim it.
- **Replay** — run the workflow start to finish (e.g. against a freshly imported solution). Replaying re-runs the recorded commands in order.

### 18.4 Why this matters across assignments

The setup work (configure language, set limits, choose comparison, build a runner, generate a standard battery of cases) is similar across many assignments. A workflow lets you codify *your* standard methodology once and apply it everywhere — the automation-of-repetition that is Morvix's whole reason to exist.

---

## 19. Packaging and the package format

### 19.1 What packaging does

`package` assembles a single, shareable archive containing everything a Receiver needs — and deliberately **excluding the Author's solution source** (§2.3). The contents are chosen through the shared selection list (§6.1) and the archive format through the single-choice list (§6.2), so packaging uses the same interaction patterns as everything else.

### 19.2 What's inside

- the **test cases** (inputs) and their **expected answers** (full outputs and/or hashes),
- the selected **runner(s)** — the portable Python core plus the `run.sh` wrapper,
- the generators (optional, so the Receiver can regenerate/extend),
- the auto-generated **README** (with the honesty clause),
- the **Morvix manifest** (`morvix.json`) — the descriptor that lets a Morvix-equipped Receiver get the rich view (§20); harmless and ignored by a Receiver without Morvix,
- **not** the Author's solution source; **not** any rival source (only opt-in precomputed numbers, §16).

### 19.3 Archive formats and space-saving

Packaging supports multiple archive formats so the user can trade compatibility against size: **zip** (universal, double-click-openable everywhere), and **tar**, **tar.gz**, **tar.xz** (better compression for large test sets; standard on Linux/macOS). Morvix picks a sensible default and lets you choose. As with hashing, when a package (especially its expected-output files) is large, Morvix **suggests** the space-saving move — a more aggressive compression format, or switching big expected outputs to hashes (§14.5, §22) — rather than deciding silently. The goal is to keep shared packages small without surprising anyone.

### 19.4 Re-importable

A package is both a human artifact *and* re-openable by Morvix: a Morvix user can open the unpacked package as a project (via the manifest) and work with it directly. So packaging is reversible — what you ship can be re-loaded, inspected, extended, and re-packaged.

---

## 20. The Receiver experience (with and without Morvix)

### 20.1 Without Morvix (the must-work baseline)

The Receiver unpacks the archive, drops in their own solution (or points the runner at it), and runs `./run.sh` (optionally with the same on/off arguments the README documents — which tests, valgrind on/off, diff on/off, etc.). The runner compiles their code, runs every case under the Author's chosen limits and comparison, prints pass/fail and timings, and writes a results file. **No Morvix, no third-party installs** — just Python 3, which is already present. This path is sacred: it must work on a clean machine.

### 20.2 With Morvix (the enhanced path)

The package's **`morvix.json` manifest** describes the entire harness: tests and groups, comparison strategy, execution model, limits, memory-check settings, runner definitions, and the Author's own per-case results. When the Receiver opens Morvix in the unpacked directory, Morvix reads the manifest and **immediately understands everything** — because the manifest tells it directly, before it ever looks at code. The Receiver can then: browse exactly which tests are included and what each checks, import their own solution and re-run selectively, **diff their per-case results against the Author's** (powering the cross-solution agreement signal of §13.5), tweak limits or add cases, and re-package to pass along. The manifest is purely additive — it enriches the experience for Morvix users and is silently ignored by everyone else.

### 20.3 Auto-detection

Opening Morvix in a directory that contains a `morvix.json` auto-loads it as a project with full context. Opening it in a directory with a runner but no manifest still lets Morvix recognize the harness structure and offer to adopt it.

---

## 21. Cross-platform and locale handling

### 21.1 Primary targets: Linux and macOS

These share a bash/POSIX environment, so a generated runner behaves the same on both — that's why they're primary. The Python runner core papers over the remaining differences (e.g. macOS vs GNU `time`, `stat`, `ulimit` quirks) by doing the measurement in Python rather than shelling out to platform-specific utilities.

### 21.2 Windows: best-effort secondary

Windows lacks the shared bash environment, so the `run.sh` wrapper doesn't apply directly. The Python core can still run there (it's stdlib Python), and a `.bat`/PowerShell wrapper can be emitted as an option. Some features (valgrind, certain rlimits, signal semantics) don't map cleanly to Windows and are reported as unavailable rather than faked. Windows is supported where it can be, honestly degraded where it can't.

### 21.3 Locale — a real correctness hazard, pinned by default

Different platforms and locales change sort order and number formatting (decimal comma vs point), which silently breaks comparison when an Author on one machine and a Receiver on another disagree purely because of locale. To prevent this, Morvix **forces a deterministic locale (`LC_ALL=C`) by default** for running and comparison, so byte ordering and numeric formatting are reproducible everywhere. This is overridable when an assignment genuinely needs a specific locale, but the safe default kills a whole class of phantom Linux↔macOS↔Windows mismatches. The manifest records the locale used so the Receiver reproduces the Author's environment exactly.

---

## 22. Smart suggestions (the "Morvix noticed…" behaviors)

Morvix proactively notices situations where a better option exists and **offers** it — never silently changing behavior, always asking. Each suggestion is delivered as a warning paired with a confirmation (§6.4, §7.2): detect → explain → suggest → let the user decide. Examples:

- **Large output → suggest hashing.** When a test's expected output exceeds a size threshold, Morvix says, in effect: *"This test's output is larger than [threshold]. Storing it in full will make the package big and slow to share. Switch this group to hash comparison to save space? (You'll lose per-failure diffs.)"* Opt-in only (§14.5).
- **Large package → suggest stronger compression.** When a package would be large, Morvix suggests a more aggressive archive format (e.g. `tar.xz`) or moving big expected outputs to hashes (§19.3).
- **Backend mismatch → warn about metrics.** If the user builds a bash-backed runner but enables timing/memory reporting, Morvix warns those metrics will be imprecise/unavailable and suggests the Python backend (§16.3).
- **Crash-shaped cases with no exit-status expectation → suggest adding one.** If the solution exits non-zero or crashes on some generated inputs, Morvix points out those cases and offers to record the expected exit status/signal (§14.6) rather than treating the crash as a generation failure.
- **Locale-sensitive output detected → confirm locale.** If output contains locale-dependent formatting, Morvix confirms the deterministic-locale default (§21.3).
- **Missing stress oracle → explain the gap.** If you ask to stress-test without a registered `--stress` rival, Morvix explains that stress testing needs an independent trusted oracle and offers to register one (`rival add <path> --stress`).
- **Whitespace comparison on space-free output → suggest exact.** After `gen --expected`, if the default `whitespace` strategy is in force but no computed answer contains a space or tab, Morvix notes that a stray space or a missing newline would still pass and points at `config --compare exact` (§14.2). This is the common case where the lenient default quietly weakens a suite.
- **Multi-line answers → mention a checker.** Conversely, when every answer spans several lines under exact/whitespace comparison, a valid answer in a different order would be judged wrong; Morvix mentions that a `checker` (§14.4) accepts any valid answer if order isn't significant. Surfacing the checker — which already exists — is the point; it is otherwise easy to miss.

These suggestions encode the judgment an experienced person would apply, surfaced at the moment it's relevant. They are advisory; the user always decides.

---

## 23. Full command reference

The complete, always-current reference — every command, its options and
examples — is **generated from the tool**: run `morvix docs` (or read
[GUIDE.md](GUIDE.md)); `help <command>` explains one in the shell. It lives there
rather than here so it can't drift from the implementation.

The verbs, by stage (flat, identical in REPL and one-shot — one-shot adds flags,
interactive use opens the relevant shared component):

- **Project & session** — `init`, `open`, `status`, `docs`, `help`, `exit`.
- **Define** — `config <language>` (incl. the raw build/run escape hatch, §9.3),
  `import`, `rival`, `model` (§10).
- **Generate** — `gen` (`--manual` / `--random` / `--generator` / `--expected`
  / `--stress` / `--crash` / `--new-generator`), `clean`.
- **Run** — `run` (scope + limit + compare flags), `runner` (new/edit/show/list/
  build/backend, §16.3).
- **Share** — `result` (export + `result diff`, §20.2), `package` (§19).
- **Automation** — `workflow` (record/stop/run/list/show/edit, §18).

---

## 24. The project directory layout on disk

A project keeps **all** of its state inside a single hidden `.morvix/` directory,
so the project root stays clean — just your own source next to `.morvix/`:

```
my-assignment/
├── solution.c                  # your own source (you edit this; never packaged)
├── .gitignore                  # written by `morvix init`
└── .morvix/
    ├── morvix.json             # generated manifest / descriptor (§20, §25)
    ├── config/
    │   ├── project.json        # language/build/run settings, model, locale (§25.1)
    │   ├── cases.json          # the case index
    │   └── runners/            # one file per named runner profile (quick.json, full.json)
    ├── solutions/              # imported solutions when --copy is used (NOT packaged)
    ├── generators/             # generator programs (any language)
    ├── tests/                  # input cases, grouped (baseline, tricky, bad-input, …)
    ├── expected/               # expected outputs and/or hashes, paralleling tests/
    ├── runner/                 # the shippable runner: morvix_runner.py + run.sh
    ├── results/                # saved results (JSON / Markdown / text)
    └── workflows/              # recorded command sequences (JSON)
```

The directory *is* the state — inspectable and git-friendly. A **package** is laid
out **flat** instead: `run.sh`, `README.md`, `morvix.json` and the `tests/`,
`expected/` and `runner/` trees sit at the archive root, so a Receiver sees the
harness directly. A package never contains the Author's source, any rival source,
or `config/`. Opening a package with Morvix re-adopts it back into a `.morvix/`
project.

---

## 25. Configuration file formats (the schemas)

> Illustrative shapes — the point is *what information is captured*, not the exact field names. JSON is used throughout (project and global config, the case index, the manifest, workflows). All of these live under `.morvix/` (§24).

### 25.1 Project config (`.morvix/config/project.json`)
Captures: project name; active language; chosen **execution model**; **per-language build/run settings** (compiler, standard, flags, include/lib paths, venv path, link mode, classpath, edition…); **raw build/run command** overrides; default **comparison strategy** and its parameters (epsilon, whitespace mode); default **limits** (wall, CPU, memory, hard-kill, output cap); **locale** setting; the current solution location and any registered **rivals** (one optionally tagged as the stress oracle). The case index is a sibling, `.morvix/config/cases.json`.

### 25.2 Runner profile (`.morvix/config/runners/<name>.json`)
Captures: which tests/groups it covers; comparison strategy; **backend** (bash/python/valgrind) and its capability set; toggles (timing on/off, memory measure on/off, hard-kill on/off, memory-checker on/off, diff on/off, color, verbosity); limit values; results-output settings (format, path).

### 25.3 Manifest (`morvix.json`)
The descriptor that makes a package self-describing to a Morvix-equipped Receiver. It lives at `.morvix/morvix.json` in a project and at the root of a (flat) package. Holds: project metadata; execution model; comparison strategy; limits; locale; the index of test cases and groups (with, per case, the expected-behavior kind — output/hash/exit-status/checker); runner definitions; and the Author's own per-case results (for diffing). Designed so opening Morvix in the directory yields full understanding **before** any code is inspected. (Case paths are stored package-relative in a package and `.morvix/`-relative in a project.)

### 25.4 Workflow (`.morvix/workflows/<name>.json`)
An ordered list of recorded Morvix commands with their arguments — readable, hand-editable, replayable (§18).

### 25.5 Global config (personal defaults)
Your usual language settings, default color theme, default archive format, default comparison mode, default Python interpreter. Inherited by every new project; overridable per project and per command. Precedence: command flags > project > global > built-in defaults.

---

## 26. Optional capabilities and extension points

These are designed-in extension points and optional capabilities. They are part of the design's intent, bounded by the same principles as the rest of the tool.

- **New languages, execution models, and comparators are pluggable.** Adding a language is one adapter; a new way of running is one execution model; a new way of judging is one comparator (§4.1). The three axes never multiply against each other, so the tool grows by addition, not rewriting.
- **The built-in shape library grows** to match the assignment families actually encountered (§13.2). The list given is a starting set, not a ceiling.
- **Optional, developer-supplied LLM hook.** A developer may plug in **their own** API key or a local model to (a) draft candidate edge-case inputs and (b) polish README prose — strictly under the "propose, don't oracle" rule (§13.6): a model may *suggest* cases, but expected answers still come from running the solution, never from the model. This is off by default, never required, and Morvix ships and works fully without it. It is the developer's choice and the developer's key; Morvix only provides the hook.
- **Windows support deepens where it can.** The baseline (Python core, emitted `.bat`/PowerShell wrapper) works; platform-specific facilities that don't exist on Windows are reported as unavailable rather than faked (§21.2).
- **External test-format interop.** If a course mandates a specific external test-file layout, an import/export adapter can be added without disturbing the core.

---

## 27. Glossary

- **Author** — the student creating and sharing tests built from their own solution (there is usually no official test set).
- **Receiver** — the student running received tests against their own solution.
- **Project** — one assignment's worth of Morvix state in a directory.
- **Language adapter** — module that builds/runs one language; the only language-aware part.
- **Execution model** — how a program is invoked and what behavior is observed (`stdio`, `library`, `args`, `file`, `interactive`).
- **Comparison strategy** — how pass/fail is decided (exact, whitespace, float, checker, hash, exit-status, combinations).
- **Expected answers** — defined by running the solution under test; in practice the Author's own, hence fallible.
- **Rival** — an alternative solution kept only for performance comparison (time/memory); never affects answers. One may be tagged `--stress` to act as the stress oracle.
- **Stress oracle** — a slow, simple, trusted rival (tagged `--stress`) used for stress testing.
- **Runner** — the shareable artifact (Python core + `run.sh`) that executes the tests; a named, configured profile.
- **Backend** — the runner's measurement engine (bash / python / valgrind-augmented), each with different capabilities.
- **Manifest (`morvix.json`)** — the package descriptor that makes a package self-describing to Morvix.
- **Workflow** — a recorded, replayable sequence of Morvix commands (JSON), "a Makefile for tests."
- **Stress testing** — random-input differential testing of the solution against a `--stress` rival oracle.
- **Shared interaction components** — the single reused set of UI primitives (selection list, single-choice, guided form, confirmation, live table, progress, message display) every command composes from.

---

*End of design documentation.*
