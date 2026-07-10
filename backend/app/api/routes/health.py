"""Liveness endpoint.

Exists for three consumers: docker-compose healthchecks, Azure Container Apps
probes, and humans checking "is it up?". Deliberately does NOT touch the
database — a liveness probe that fails when the DB blips causes restart storms;
readiness (with dependency checks) can be added separately if needed.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")
