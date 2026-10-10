from fastapi import FastAPI

from app.api import auth, me
from app.api.errors import install_error_handlers
from nextpay_engine import ENGINE_VERSION

app = FastAPI(title="NextPay API", version="0.1.0")
install_error_handlers(app)
app.include_router(auth.router)
app.include_router(me.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine_version": ENGINE_VERSION}
