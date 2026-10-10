"""FastAPI dependencies: how routes get services and the current user.

Each piece is its own dependency so tests can override it (a cheaper hasher, a
controllable clock, a rollback session).
"""

from datetime import timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.clock import Clock, utc_now
from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError
from app.core.security import AccessTokenCodec, PasswordHasher
from app.db.session import get_session
from app.models import User
from app.repositories import (
    BalanceSnapshotRepository,
    BillRepository,
    DebtRepository,
    EssentialExpenseRepository,
    GoalRepository,
    IncomeSourceRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.services.auth import AuthService
from app.services.balances import BalanceSnapshotService
from app.services.bills import BillService
from app.services.debts import DebtService
from app.services.essential_expenses import EssentialExpenseService
from app.services.goals import GoalService
from app.services.income_sources import IncomeSourceService


def get_clock() -> Clock:
    return utc_now


@lru_cache
def get_password_hasher() -> PasswordHasher:
    return PasswordHasher()


def get_auth_service(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AuthService:
    return AuthService(
        users=UserRepository(session),
        refresh_tokens=RefreshTokenRepository(session),
        transaction=session,
        hasher=hasher,
        access_tokens=AccessTokenCodec(
            settings.jwt_secret.get_secret_value(),
            timedelta(minutes=settings.access_token_ttl_minutes),
        ),
        refresh_token_ttl=timedelta(days=settings.refresh_token_ttl_days),
        clock=clock,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

# auto_error=False: a missing or non-Bearer header gets our own error envelope.
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth: AuthServiceDep,
) -> User:
    """The user whose access token came with the request; 401 otherwise."""
    if credentials is None:
        raise AuthenticationError()
    return auth.authenticate(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


SessionDep = Annotated[Session, Depends(get_session)]


def get_income_source_service(session: SessionDep) -> IncomeSourceService:
    return IncomeSourceService(income_sources=IncomeSourceRepository(session), transaction=session)


def get_bill_service(session: SessionDep) -> BillService:
    return BillService(bills=BillRepository(session), transaction=session)


def get_essential_expense_service(session: SessionDep) -> EssentialExpenseService:
    return EssentialExpenseService(
        essentials=EssentialExpenseRepository(session), transaction=session
    )


def get_debt_service(session: SessionDep) -> DebtService:
    return DebtService(debts=DebtRepository(session), transaction=session)


def get_goal_service(session: SessionDep) -> GoalService:
    return GoalService(goals=GoalRepository(session), transaction=session)


def get_balance_snapshot_service(
    session: SessionDep, clock: Annotated[Clock, Depends(get_clock)]
) -> BalanceSnapshotService:
    return BalanceSnapshotService(
        snapshots=BalanceSnapshotRepository(session), transaction=session, clock=clock
    )


IncomeSourceServiceDep = Annotated[IncomeSourceService, Depends(get_income_source_service)]
BillServiceDep = Annotated[BillService, Depends(get_bill_service)]
EssentialExpenseServiceDep = Annotated[
    EssentialExpenseService, Depends(get_essential_expense_service)
]
DebtServiceDep = Annotated[DebtService, Depends(get_debt_service)]
GoalServiceDep = Annotated[GoalService, Depends(get_goal_service)]
BalanceSnapshotServiceDep = Annotated[BalanceSnapshotService, Depends(get_balance_snapshot_service)]
