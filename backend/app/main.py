from fastapi import FastAPI

from app.api import auth, balances, bills, debts, essential_expenses, goals, income_sources, me
from app.api.errors import install_error_handlers
from nextpay_engine import ENGINE_VERSION

app = FastAPI(title="NextPay API", version="0.1.0")
install_error_handlers(app)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(income_sources.router)
app.include_router(bills.router)
app.include_router(essential_expenses.router)
app.include_router(debts.router)
app.include_router(goals.router)
app.include_router(balances.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine_version": ENGINE_VERSION}
