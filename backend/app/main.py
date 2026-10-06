from fastapi import FastAPI

from nextpay_engine import ENGINE_VERSION

app = FastAPI(title="NextPay API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine_version": ENGINE_VERSION}
