from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    auth,
    balances,
    bills,
    debts,
    essential_expenses,
    goals,
    income_sources,
    me,
    paychecks,
    payments,
    plans,
)
from app.api.errors import install_error_handlers
from app.core.config import get_settings
from app.schemas.health import HealthResponse
from nextpay_engine import ENGINE_VERSION


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Refuse to start without valid settings, instead of failing the first request.

    Runs only when the server starts, so importing the app (the OpenAPI export, tests)
    still needs no settings.
    """
    get_settings()  # raises SettingsError naming what is missing
    yield


app = FastAPI(title="NextPay API", version="0.1.0", lifespan=lifespan)
install_error_handlers(app)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(income_sources.router)
app.include_router(bills.router)
app.include_router(essential_expenses.router)
app.include_router(debts.router)
app.include_router(goals.router)
app.include_router(balances.router)
app.include_router(paychecks.router)
app.include_router(plans.router)
app.include_router(payments.router)


@app.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok", engine_version=ENGINE_VERSION)
