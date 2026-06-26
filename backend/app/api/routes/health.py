from fastapi import APIRouter
from backend.app.api.schemas.health import HealthResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="backend", version="0.1.0")
