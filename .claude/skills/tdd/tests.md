# Good and Bad Tests

## Good Tests

**Integration-style**: Test through real interfaces, not mocks of internal parts.

```python
# GOOD: Tests observable behavior
def test_user_can_checkout_with_valid_cart():
    checkout = Checkout(payments=FakePayments.ok(), mailer=FakeMailer())
    cart = Cart()
    cart.add(product())

    receipt = checkout.checkout(cart, payment_method())

    assert receipt.status == Status.CONFIRMED
```

Characteristics:

- Tests behavior callers care about
- Uses public API only (no reaching into `_private` attributes, no monkeypatching internals)
- Survives internal refactors
- Describes WHAT, not HOW
- One logical assertion per test

Notes on Python specifics:

- Prefer top-level `tests/` directory mirroring the package structure — these can only see your package's public API, which forces good interface boundaries
- Keep tests inside the package only for truly internal helpers (e.g., a parser combinator that isn't exposed)
- Use `pytest.mark.parametrize` for table-driven cases instead of for-loops in tests; failures point at the failing case
- For async code, use `pytest-asyncio` (`@pytest.mark.asyncio`) — don't manually drive `asyncio.run()` inside tests

## Bad Tests

**Implementation-detail tests**: Coupled to internal structure.

```python
# BAD: Tests implementation details
def test_checkout_calls_payment_client_charge(mocker):
    mock_client = mocker.Mock()
    checkout(cart, mock_client)
    mock_client.charge.assert_called_once_with(cart.total_cents)
    # No assertion on observable outcome — only that a method was called.
```

Red flags:

- Mocking internal collaborators
- `mock.assert_called_with(...)` / `call_count == N` on internal methods (asserting call counts/order)
- Reaching into `obj._private` or monkeypatching module-level functions a test should never see
- Test breaks when refactoring without behavior change
- Test name describes HOW not WHAT
- Verifying through external means (DB row, log lines, file bytes) instead of the interface

```python
# BAD: Bypasses interface to verify
def test_create_user_saves_to_database(db_conn):
    create_user(NewUser(name="Alice"))

    row = db_conn.execute("SELECT name FROM users WHERE name = ?", ("Alice",)).fetchone()
    assert row[0] == "Alice"

# GOOD: Verifies through interface
def test_create_user_makes_user_retrievable():
    user = create_user(NewUser(name="Alice"))

    retrieved = get_user(user.id)

    assert retrieved.name == "Alice"
```

## Useful libraries

- `pytest` — de-facto standard runner; fixtures, parametrize, rich assertion introspection
- `pytest-asyncio` — `@pytest.mark.asyncio` for async tests; configure `asyncio_mode = "auto"` to skip the marker boilerplate
- `pytest.mark.parametrize` — parameterized tests; prefer over loops or per-case test functions
- `hypothesis` — property-based testing; great for parsers, serializers, anything with an input grammar
- `syrupy` (or `pytest-snapshot`) — snapshot tests for stable serialized output
- `respx` / `responses` — HTTP-level fakes for `httpx` / `requests`; usually a better behavioral boundary than mocking your own HTTP client class
- `freezegun` / `time-machine` — control `datetime.now()` without injecting a clock everywhere
- `testcontainers-python` — throwaway real Postgres/Redis/etc. when in-memory stand-ins would diverge from prod
