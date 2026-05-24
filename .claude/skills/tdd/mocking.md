# When to Mock

Mock at **system boundaries** only:

- External APIs (payment, email, etc.)
- Databases (often — prefer a real test DB via `testcontainers-python` or in-memory SQLite when feasible)
- Time/randomness (inject a `Clock` / `Random` protocol, or use `freezegun` / `time-machine`)
- File system (sometimes — `tmp_path` fixture / `tempfile` is often better than mocking)

Don't mock:

- Your own classes/modules
- Internal collaborators
- Anything you control end-to-end

## Designing for Mockability

At system boundaries, design protocols/ABCs that are easy to fake or mock:

**1. Inject collaborators via Protocols (or ABCs), don't construct them inside**

Pass external dependencies in rather than constructing them internally:

```python
# Easy to swap in tests
def process_payment(order: Order, client: PaymentClient) -> Receipt:
    return client.charge(order.total_cents())

# Hard to swap — concrete type baked in, env coupling
def process_payment(order: Order) -> Receipt:
    client = StripeClient.from_env()
    return client.charge(order.total_cents())
```

**Choosing the injection shape:**

| Shape | When to use |
|-------|-------------|
| `Protocol` (structural) | Default. Duck-typed, no inheritance required, friendly to in-test fakes. |
| `ABC` (nominal) | When you want explicit registration / runtime `isinstance` checks. |
| Concrete class with default arg | Tiny seams where a Protocol would be overkill — pass a real default, swap in tests. |

**2. Prefer SDK-style protocols over a generic fetcher**

One method per external operation, not one stringly-typed `fetch`:

```python
# GOOD: each method is independently mockable, types are specific
class UserApi(Protocol):
    async def get_user(self, id: UserId) -> User: ...
    async def get_orders(self, user_id: UserId) -> list[Order]: ...
    async def create_order(self, data: NewOrder) -> Order: ...

# BAD: tests must know URL paths and JSON shapes — couples tests to transport
class HttpFetcher(Protocol):
    async def fetch(self, endpoint: str, body: dict) -> dict: ...
```

The SDK approach means:

- Each fake/mock returns one specific typed shape
- No conditional logic in test setup
- Easy to see which endpoints a test exercises
- Type safety per endpoint

## Fakes vs `unittest.mock`

Reach for a hand-written fake first when the dependency is stateful or reused across tests:

```python
@dataclass
class FakePayments:
    charges: list[int] = field(default_factory=list)

    def charge(self, cents: int) -> TxId:
        self.charges.append(cents)
        return TxId("fake")
```

Then assert on the recorded state:

```python
def test_checkout_charges_correct_total():
    payments = FakePayments()
    checkout = Checkout(payments=payments)
    checkout.process(cart_with_total(1000))
    assert payments.charges == [1000]
```

Use `unittest.mock` / `pytest-mock` for one-off cases where building a fake is overkill:

```python
def test_payment_propagates_failure(mocker):
    client = mocker.Mock(spec=PaymentClient)
    client.charge.side_effect = PayError("declined")

    with pytest.raises(PayError):
        process_payment(order, client)
```

Heuristic: if the test asserts on `call_count` or `assert_called_with` for an internal method, it's probably testing implementation. Prefer fakes that record state, then assert on behavior observed through the public interface.

Tips:

- Always pass `spec=` (or `spec_set=`) when using `Mock` — catches typos and signature drift against the real class.
- Prefer `mocker.patch.object(module.Class, "method")` over `mocker.patch("module.Class.method")` — the object form fails loudly if the attribute doesn't exist.
- Patch where the name is *used*, not where it's defined: `mocker.patch("myapp.handlers.requests.get")`, not `mocker.patch("requests.get")`.

## Async fakes

For `async def` interfaces, fakes use `async def` too — no special machinery needed:

```python
class FakeUserApi:
    async def get_user(self, id: UserId) -> User:
        return User(id=id, name="fake")
```

For `Mock`, use `AsyncMock` (or `mocker.AsyncMock`) so awaiting the call doesn't blow up:

```python
client = mocker.AsyncMock(spec=UserApi)
client.get_user.return_value = User(id=UserId(1), name="Alice")
```
