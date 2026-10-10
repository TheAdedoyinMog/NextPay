"""UserOwnedRepository against a real PostgreSQL, through BillRepository.

This is the tenant boundary every resource repository inherits (ADR 0010).
"""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Bill, User
from app.repositories import BillRepository, UserRepository


def make_bill(user: User, name: str = "Rent", priority: int = 1, day: int = 20) -> Bill:
    return Bill(
        user_id=user.id,
        name=name,
        amount_cents=80_000,
        priority=priority,
        first_due_date=date(2026, 10, day),
        repeat_every_months=1,
    )


def two_users(session: Session) -> tuple[User, User]:
    users = UserRepository(session)
    return users.add(User(email="ada@example.com")), users.add(User(email="bob@example.com"))


def test_add_stores_the_row_and_fills_in_its_defaults(db_session: Session) -> None:
    ada, _ = two_users(db_session)
    bills = BillRepository(db_session)
    rent = bills.add(make_bill(ada))
    assert rent.id is not None and rent.created_at is not None
    assert bills.get(ada.id, rent.id) is rent


def test_get_never_returns_another_users_row(db_session: Session) -> None:
    ada, bob = two_users(db_session)
    bills = BillRepository(db_session)
    rent = bills.add(make_bill(ada))
    assert bills.get(bob.id, rent.id) is None
    assert bills.get(ada.id, uuid.uuid4()) is None


def test_list_is_scoped_to_the_user_and_ordered(db_session: Session) -> None:
    ada, bob = two_users(db_session)
    bills = BillRepository(db_session)
    bills.add(make_bill(ada, "Phone", priority=2, day=5))
    bills.add(make_bill(ada, "Water", priority=1, day=25))
    bills.add(make_bill(ada, "Rent", priority=1, day=20))
    bills.add(make_bill(ada, "Power", priority=1, day=20))
    bills.add(make_bill(bob, "Bob's rent"))

    # By priority, then first due date, then name.
    assert [bill.name for bill in bills.list_for(ada.id)] == ["Power", "Rent", "Water", "Phone"]
    assert [bill.name for bill in bills.list_for(bob.id)] == ["Bob's rent"]
    assert bills.list_for(uuid.uuid4()) == []


def test_delete_removes_only_that_row(db_session: Session) -> None:
    ada, bob = two_users(db_session)
    bills = BillRepository(db_session)
    rent = bills.add(make_bill(ada))
    bills.add(make_bill(ada, "Phone"))
    bills.add(make_bill(bob, "Bob's rent"))

    bills.delete(rent)

    assert bills.get(ada.id, rent.id) is None
    assert db_session.scalar(select(func.count()).select_from(Bill)) == 2
