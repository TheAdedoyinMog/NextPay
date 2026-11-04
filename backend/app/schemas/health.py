from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    engine_version: str
