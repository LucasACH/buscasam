# Interface Design for Testability

Good interfaces make testing natural:

1. **Accept dependencies via Protocols, don't construct them**

   ```python
   # Testable — any PaymentGateway impl works (real, fake, mock)
   def process_order(order: Order, gateway: PaymentGateway) -> Receipt:
       return gateway.charge(order.total_cents())

   # Hard to test — concrete type, env coupling, no seam to swap
   def process_order(order: Order) -> Receipt:
       gateway = StripeGateway.from_env()
       return gateway.charge(order.total_cents())
   ```

2. **Return values, don't mutate arguments for results**

   ```python
   # Testable — pure function, easy to assert on the return
   def calculate_discount(cart: Cart) -> Discount: ...

   # Harder to test — must construct mutable state, then read it back
   def apply_discount(cart: Cart) -> None:
       cart.total_cents -= ...
   ```

3. **Use value objects instead of primitive parameters**

   Python's "newtype" pattern via `typing.NewType` or a frozen dataclass. Prevents passing the wrong id type and gives you a place to hang validation.

   ```python
   # Primitive obsession — easy to mix up, no validation seam
   def get_user(id: str) -> User: ...

   # NewType — type checker enforces the right id; cheap, no runtime overhead
   UserId = NewType("UserId", str)

   def get_user(id: UserId) -> User: ...

   # Frozen dataclass — runtime validation lives here
   @dataclass(frozen=True)
   class UserId:
       value: str
       def __post_init__(self) -> None:
           if not self.value:
               raise ValueError("UserId cannot be empty")

   def get_user(id: UserId) -> User: ...
   ```

4. **Small surface area**
   - Fewer protocol methods = fewer fakes/mocks to wire up
   - Fewer parameters = simpler test setup
   - Prefer one protocol per role (`PaymentGateway`, `Mailer`) over a single god-protocol
   - Use keyword-only args (`def f(*, flag: bool)`) for booleans — call sites stay readable, tests can't transpose positional args
