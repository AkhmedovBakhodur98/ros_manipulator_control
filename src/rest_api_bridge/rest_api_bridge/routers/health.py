"""Health check router."""

from fastapi import APIRouter, Depends, HTTPException

from rest_api_bridge.models.responses import HealthResponse, IsReadyResponse, ErrorResponse
from rest_api_bridge.services.mock_service import MockService


def create_health_router(service: MockService, config: dict, jwt_auth) -> APIRouter:
    """
    Create health check router.

    Args:
        service: Service implementation (mock or real)
        config: Application configuration
        jwt_auth: JWT authentication dependency

    Returns:
        FastAPI router for health endpoints
    """
    router = APIRouter(tags=["Health"])

    @router.get(
        "/health",
        response_model=HealthResponse,
        summary="Health check",
        description="Check if the API service is running"
    )
    async def health_check():
        """Check service health status."""
        return HealthResponse(status="ok")

    @router.get(
        "/is_ready",
        response_model=IsReadyResponse,
        dependencies=[Depends(jwt_auth)],
        summary="Readiness check",
        description="Check readiness of robotic system modules to receive commands"
    )
    async def is_ready():
        """Check if system is ready for operations."""
        try:
            return service.is_ready()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"status": "error", "error_code": "internal_error", "message": str(e)}
            )

    return router
