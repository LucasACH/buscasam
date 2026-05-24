# Python Review Pitfalls

Annotated bad-vs-good examples for the highest-impact findings. Each entry maps to a checklist item in [SKILL.md](SKILL.md). The reviewer cites these to write concrete, actionable comments.

---

## 1. Bare `except` / `except Exception` swallowing

**Category**: errors • **Severity**: BLOCKING in request/IO paths, WARN elsewhere

```python
# BAD — hides every failure, including KeyboardInterrupt, type errors, bugs
try:
    user = db.get_user(user_id)
except:
    user = None
```

```python
# GOOD — narrow the exception, log or re-raise, preserve cause
try:
    user = db.get_user(user_id)
except UserNotFound:
    user = None
except DatabaseError as e:
    logger.exception("user lookup failed")
    raise AuthError("could not load user") from e
```

**Comment template**:
```
### [BLOCKING] R### — src/handlers/auth.py:42 — bare except swallows all errors
**Category**: errors
**Why**: hides programmer errors and KeyboardInterrupt; failures become silent corruption.
**Fix**: catch the specific exceptions (UserNotFound, DatabaseError) and re-raise with `from e`.
**Status**: open
```

Acceptable broad `except Exception` only when paired with logging AND re-raise, or at a top-level boundary that converts to a response:
```python
try:
    return await handle(req)
except Exception:
    logger.exception("request failed")
    return Response(status=500)
```

---

## 2. Mutable default arguments

**Category**: errors • **Severity**: BLOCKING (silent state leakage between calls)

```python
# BAD — the list is shared across every call that omits `items`
def add_item(item, items=[]):
    items.append(item)
    return items
```

```python
# GOOD — sentinel pattern
def add_item(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items
```

Same trap with `{}`, `set()`, and any dataclass field without `field(default_factory=...)`.

---

## 3. `assert` used for runtime invariants

**Category**: errors • **Severity**: BLOCKING in security/auth paths

```python
# BAD — `python -O` strips this; auth check disappears in optimized builds
def withdraw(account, amount):
    assert account.balance >= amount, "insufficient funds"
    account.balance -= amount
```

```python
# GOOD — explicit raise survives -O
def withdraw(account, amount):
    if account.balance < amount:
        raise InsufficientFunds(account.id, amount)
    account.balance -= amount
```

`assert` is fine in tests and for documenting impossible-by-construction invariants in non-security code. Never for input validation, authorization, or anything a caller can trigger.

---

## 4. Blocking work inside `async`

**Category**: async • **Severity**: BLOCKING

```python
# BAD — requests is sync; blocks the event loop for the whole HTTP call
async def fetch_user(user_id: int) -> User:
    r = requests.get(f"/users/{user_id}")
    return User(**r.json())
```

```python
# GOOD — use an async HTTP client
async def fetch_user(user_id: int) -> User:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"/users/{user_id}")
        return User(**r.json())
```

Same trap with `open()`, `time.sleep`, sync DB drivers (`psycopg2` vs `asyncpg`), and `subprocess.run`.

CPU-bound work inside async: wrap in `asyncio.to_thread(fn, *args)` or `loop.run_in_executor(...)`.

---

## 5. `pickle` / `eval` / `exec` on untrusted input

**Category**: security • **Severity**: BLOCKING

```python
# BAD — RCE: any unpickle on attacker-controlled bytes executes arbitrary code
def load_session(blob: bytes) -> Session:
    return pickle.loads(blob)
```

```python
# GOOD — use a structured, safe serializer
def load_session(blob: bytes) -> Session:
    data = json.loads(blob)
    return Session.model_validate(data)  # pydantic
```

Rules:
- `pickle.loads` / `marshal.loads` / `shelve` on bytes from clients, queues, caches you don't fully control = RCE.
- `eval` / `exec` on any string derived from input = RCE.
- `yaml.load` without `Loader=SafeLoader` (or `yaml.safe_load`) = RCE.

---

## 6. Broad `except` plus `pass` (silent failure)

**Category**: errors • **Severity**: BLOCKING in libraries, WARN in scripts

```python
# BAD — surfaces nothing; tomorrow's incident has no breadcrumb
def parse(input: str) -> Config:
    try:
        return Config.from_yaml(input)
    except Exception:
        pass
    return Config.default()
```

```python
# GOOD — return error with context
def parse(input: str) -> Config:
    try:
        return Config.from_yaml(input)
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid yaml: {e}") from e
```

If the fallback is intentional, log it and narrow the except so unrelated bugs still surface.

---

## 7. Public API leaks of third-party types

**Category**: api • **Severity**: WARN (BLOCKING for `1.0+` libraries)

```python
# BAD — bumping httpx forces a SemVer break on us
def fetch(url: str) -> httpx.Response:
    ...
```

```python
# GOOD — own the boundary
@dataclass(frozen=True)
class Response:
    status: int
    body: bytes

class FetchError(Exception): ...

def fetch(url: str) -> Response: ...
```

Exception: re-exporting a protocol the caller must implement (e.g., `typing.Protocol` definitions) is fine — that coupling is intended.

---

## 8. String concatenation in hot loops

**Category**: performance • **Severity**: WARN (BLOCKING with profiling evidence)

```python
# BAD — quadratic: each += copies the whole accumulator
out = ""
for line in lines:
    out += prefix + line + "\n"
```

```python
# GOOD — join is linear
out = "\n".join(f"{prefix}{line}" for line in lines) + "\n"
```

Or build a list and `"".join(parts)` at the end. Same shape applies to `bytes` (`b"".join(...)`).

---

## 9. Mocking internal collaborators

**Category**: testing • **Severity**: WARN

```python
# BAD — patches our own storage; test passes while real Storage is broken
def test_process(mocker):
    storage = mocker.Mock()
    storage.save.return_value = None
    svc = Service(storage)
    assert svc.process(input) == expected
```

```python
# GOOD — use a real in-memory implementation; mock only the boundary
def test_process():
    storage = InMemoryStorage()
    svc = Service(storage)
    assert svc.process(input) == expected
    assert storage.get(input.id) == expected_record
```

Mock only at process boundaries: network calls, filesystem (when slow), system clock, randomness. Mocking owned code is how you ship green tests with broken behavior.

---

## 10. SQL injection via string interpolation

**Category**: security • **Severity**: BLOCKING

```python
# BAD — attacker controls `user_id` → arbitrary SQL
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
```

```python
# GOOD — parameterized; driver escapes
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

ORMs (SQLAlchemy, Django) handle this correctly when you use their query builders. The hole opens when someone reaches for `.execute(raw_sql)` or `text(f"...")` with interpolated input.

---

## 11. `subprocess` with `shell=True` on untrusted input

**Category**: security • **Severity**: BLOCKING

```python
# BAD — filename "; rm -rf /" wins
subprocess.run(f"convert {user_filename} out.png", shell=True)
```

```python
# GOOD — list form, no shell interpretation
subprocess.run(["convert", user_filename, "out.png"], check=True)
```

If you must use `shell=True` for shell features (pipes, globs), pre-validate inputs with a strict allowlist and use `shlex.quote` — but the list form is almost always available.
