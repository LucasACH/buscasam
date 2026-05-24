---
name: code-review
description: Python-focused code review with structured PR comments and a merge gate. Use when reviewing a branch, PR, or diff before merge. Produces ID'd comments (BLOCKING/WARN/NIT) that the implementing agent must resolve before merge.
---

# Python Code Review

## Philosophy

**Push standards explicitly.** The reviewer carries the rules into the prompt; do not rely on the implementing agent having read them. Standards explicit in the prompt is the right mode for review (the implementation phase is the time to pull from references).

**Comments are contracts.** Every finding gets an ID, a severity, a category, and a fix. The implementing agent must reply with `resolved` + commit SHA. A merge gate enforces this — see [Merge Gate](#merge-gate).

**Reviewers don't fix code.** Write the comment; let the implementing agent fix it. If the reviewer fixes inline, the loop breaks and quality degrades.

## When to Use

- Before merging any branch into `main`
- On a GitHub PR (`/code-review <PR#>`)
- Re-running after the implementing agent claims `resolved` (merge gate verification)

Skip for: doc-only changes, generated files, dependency bumps with no code edits.

## Review Workflow

### 1. Triage

Before reading code:

- [ ] Read the issue linked in the PR description (`Closes #N`).
- [ ] Fetch its **parent issue** — slice issues are usually sub-issues of a PRD, and the PRD has cross-slice context (what's deferred to later slices, what's architecturally locked) that recalibrates severity. Without it, you risk flagging intentionally-deferred work as "missing."
  ```bash
  gh api graphql -f query='{ repository(owner:"OWNER",name:"REPO") { issue(number:N) { parent { number title body } } } }'
  ```
  If `parent` is null, the linked issue is the spec. Otherwise read the parent before the diff and treat its "Deferred" / "Out of scope" sections as hard constraints on what *not* to flag.
- [ ] If no context at all, **STOP and ask the user.**
- [ ] Establish the optimization axis: correctness, performance, maintainability? Different axes change which findings are BLOCKING.
- [ ] Identify the diff scope: `git diff main...HEAD` (or `gh pr diff <PR#>`).
- [ ] List touched modules. Cap review at one module at a time to stay in the smart zone.

### 2. Mechanical pass (push to tools, not humans)

Run these and treat any failure as BLOCKING:

```bash
ruff format --check .
ruff check .
mypy .            # or pyright, depending on the project
pytest
```

If `pip-audit`, `bandit`, or `safety` are configured, run them. Reviews must not flag findings ruff/mypy already catches — that is wasted attention.

### 3. Substantive pass

Walk the diff against the [Python Checklist](#python-checklist) below. For each finding, write a structured comment (see [Comment Format](#comment-format)).

### 4. Emit review

For a GitHub PR target, post the review directly via `gh pr review` — do **not** write a local file. For a local branch with no PR, write `review-<short-sha>.md` at the repo root. See [Output](#output).

### 5. Merge gate

Before merge, re-run the skill against the new HEAD. Every prior `BLOCKING` must be `resolved` AND verified. See [Merge Gate](#merge-gate).

---

## Comment Format

Every finding is a structured block. The implementing agent parses these IDs to drive fixes; deviating from the format breaks the loop.

```
### [SEVERITY] R### — path/to/file.py:LINE — Short title
**Category**: types | errors | concurrency | async | performance | api | testing | tooling | docs | security
**Why**: One sentence on the concrete failure mode (e.g., "uncaught KeyError in request path crashes worker").
**Fix**: One sentence with the prescribed change. Code snippet if non-obvious.
**Status**: open
```

### Severity rules

| Severity | Definition | Merge effect |
|----------|------------|--------------|
| BLOCKING | Correctness, security holes, crashes in prod, data loss, missing tests for new behavior, ruff/mypy failures, mutable default args, broad `except:` swallowing | **Blocks merge.** Must be `resolved` + verified. |
| WARN | Idiom violation, performance smell, missing edge-case test, weak API ergonomics, missing type hints on public API | Should fix. May be waived only with explicit `**Status**: waived — <reason>` from the user. |
| NIT | Style preference, naming, doc nits not covered by ruff | Optional. Default to skipping unless they cluster around one symbol. |

### ID rules

- Sequential per review file: `R001`, `R002`, …
- Stable across re-reviews: if `R007` is fixed, do **not** renumber.
- New findings on re-review continue the sequence.

---

## Output

The review body has this exact shape regardless of where it lands:

```markdown
# Review of <branch> @ <short-sha>
Reviewer: code-review skill
Reviewed: <ISO date>
Optimization axis: <correctness | perf | maintainability>

## Mechanical
- ruff format: pass | FAIL
- ruff check: pass | FAIL
- mypy: pass | FAIL
- pytest: pass | FAIL (N failures)

## Findings

<comment blocks here, sorted BLOCKING → WARN → NIT>

## Summary
- BLOCKING: N open
- WARN: N open
- NIT: N open
- Merge: BLOCKED | READY
```

**GitHub PR review (preferred)** → pipe the body straight into `gh pr review` and stop. No local file.
- Any BLOCKING: `gh pr review <PR#> --request-changes --body "$(cmd-that-prints-review)"`
- Otherwise: `gh pr review <PR#> --comment --body "..."`
- If `--request-changes` is rejected because the PR is the user's own, retry with `--comment`.
- For line-anchored comments, post each finding via `gh api` against the PR's review-comments endpoint.

**Local branch with no PR** → write `review-<short-sha>.md` at the repo root. The implementing agent reads and edits this file to drive fixes.

Do not produce both. A local file alongside a PR comment forks the source of truth; pick one based on the target.

---

## Merge Gate

The implementing agent **cannot merge** while any `BLOCKING` finding has `**Status**: open`. Enforcement:

1. Implementing agent fixes a finding, commits, and records the resolution:
   ```
   **Status**: resolved — <commit-sha>
   ```
   - PR target: post a reply on the PR review thread (or a new PR comment) with the resolved-line per finding ID. Do not edit prior review comments — append.
   - Local-file target: edit `review-<sha>.md` in place.
2. Re-run this skill against the new HEAD. The skill:
   - For PR targets, fetches the prior review body via `gh pr view <PR#> --json reviews,comments` and reconstructs status from the conversation (latest status per `R###` wins).
   - Verifies each `resolved` finding is actually fixed at the cited SHA. If not, mark `**Status**: regressed` and bump severity.
   - Adds new findings discovered in the new diff (continue ID sequence).
   - Posts the updated review as a new PR comment (or rewrites the local file).
3. Merge is permitted only when the latest review shows `BLOCKING: 0 open` AND no `regressed` entries.

**WARN waivers** require the user (not the implementing agent) to write:
```
**Status**: waived — <one-line justification>
```
A waiver from the agent itself does not count.

---

## Python Checklist

Use this as the substantive-pass spine. Each item maps to a `Category` value.

### Types & typing
- [ ] Public functions/methods have type hints on params and return value.
- [ ] No `Any` in public APIs without justification; prefer `TypeVar`, `Protocol`, or `Literal`.
- [ ] `Optional[T]` (or `T | None`) only when `None` is a real value, not a sentinel hiding errors.
- [ ] Generic containers use parametrized form (`list[int]`, not bare `list`).
- [ ] `TypedDict` / `dataclass` / `pydantic.BaseModel` for structured data instead of bare dicts.

### Error handling
- [ ] **No bare `except:` or `except Exception:` that swallows.** BLOCKING in request/IO paths.
- [ ] Custom exception hierarchies for library code; re-raise with `from` to preserve cause.
- [ ] No `pass` in `except` blocks without a comment explaining why it's safe.
- [ ] No `assert` for runtime invariants in production paths — `python -O` strips them. Use explicit `if/raise`.
- [ ] Error messages include the offending value when it's safe to log.
- [ ] Resources (files, connections, locks) acquired via `with` / context managers, not manual close.

### Concurrency & state
- [ ] No mutable default arguments (`def f(x=[])` is a trap).
- [ ] Shared mutable state across threads protected by `threading.Lock` or `queue.Queue`; document why mutation needs sharing.
- [ ] No global state mutated from request handlers — pass dependencies in.
- [ ] `multiprocessing` workers don't capture unpicklable closures.

### Async
- [ ] No blocking I/O (`open()`, `requests`, `time.sleep`, sync DB drivers) inside `async def`.
- [ ] CPU-bound work in async handlers offloaded via `asyncio.to_thread` or `run_in_executor`.
- [ ] Tasks created with `asyncio.create_task` have a documented cancellation/await story; no fire-and-forget without a tracking set.
- [ ] No `asyncio.run()` inside an already-running loop.
- [ ] `async with` / `async for` used for async context managers and iterators.

### Performance
- [ ] No O(n²) accidental loops over lists where a `set`/`dict` lookup works.
- [ ] No repeated `.append` inside a loop when a list comprehension or generator is clearer and faster.
- [ ] String building in hot loops uses `"".join(parts)`, not `+=`.
- [ ] No `pandas`/`numpy` `.iterrows()` / Python loops over arrays in hot paths; vectorize.
- [ ] Profiling note required for any "perf" PR — without `pytest-benchmark` / `cProfile` numbers, claim is rejected (BLOCKING).

### API design
- [ ] Public functions return values, not mutate-and-return-`None`.
- [ ] `dataclass(frozen=True)` or `pydantic` models for value objects; avoid passing many positional primitives.
- [ ] Keyword-only arguments (`*,`) for booleans and optional flags to prevent call-site ambiguity.
- [ ] `__all__` set on modules whose public surface differs from "everything not prefixed with `_`".
- [ ] Don't expose third-party library types in public APIs of a reusable library (creates version coupling).
- [ ] Deprecations use `warnings.warn(..., DeprecationWarning, stacklevel=2)`, not just a comment.

### Testing
- [ ] New behavior has a test exercising the **public interface** (per `tdd` skill).
- [ ] No mocks for internal collaborators. Mock only at process boundaries (network, FS, clock).
- [ ] `pytest.mark.parametrize` for any function with non-trivial input space; consider `hypothesis` for property-based tests.
- [ ] Fixtures live in `conftest.py` at the narrowest scope that works.
- [ ] `pytest.raises(SpecificError, match=...)` asserts on message, not just on the exception class.
- [ ] Async tests use `pytest-asyncio` (`@pytest.mark.asyncio`) and don't leak event loops.

### Security
- [ ] No `eval`, `exec`, `pickle.loads` on untrusted input.
- [ ] No string-built SQL — parameterized queries only.
- [ ] No `subprocess` with `shell=True` on untrusted input.
- [ ] Secrets sourced from env/secret manager, never hardcoded; not logged.
- [ ] Path traversal guarded when joining user input with `os.path.join`/`pathlib`.

### Tooling & docs
- [ ] `ruff check` clean (mechanical pass).
- [ ] `ruff format` clean.
- [ ] `mypy` (or `pyright`) clean on touched files; new `# type: ignore` carries a comment with the reason.
- [ ] First line of each public function/class docstring is a one-line summary.
- [ ] No `# noqa` / `# type: ignore` without justification.
- [ ] No commented-out code or `print` debugging left in the diff.

---

## Pitfalls (annotated)

For the worst offenders — bare excepts, mutable defaults, `pickle` on untrusted input, blocking-in-async, shared mutable state, monkeypatching internals in tests — see [pitfalls.md](pitfalls.md). Each shows the bad pattern, the fix, and which checklist item it maps to.

---

## Anti-patterns in the review itself

Watch your own output:

- **Don't fix the code.** Write a comment. The implementing agent fixes.
- **Don't flag what ruff/mypy catches.** Mechanical pass owns those.
- **Don't WARN a hypothetical.** Cite the actual line. If you can't, drop the finding.
- **Don't NIT-pile.** If the diff has >5 NITs, escalate one as WARN ("inconsistent naming across module") and drop the rest.
- **Don't waive your own findings.** Only the user waives.
