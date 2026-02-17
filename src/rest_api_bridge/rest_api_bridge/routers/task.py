"""Task management router."""

from fastapi import APIRouter, Depends, HTTPException

from rest_api_bridge.models.responses import (
    TaskStatusResponse,
    TaskCancelResponse,
    ErrorResponse
)
from rest_api_bridge.services.mock_service import MockService


def create_task_router(service: MockService, jwt_auth) -> APIRouter:
    """
    Create task management router.

    Args:
        service: Service implementation (mock or real)
        jwt_auth: JWT authentication dependency

    Returns:
        FastAPI router for task endpoints
    """
    router = APIRouter(prefix="/task", tags=["Task Management"])

    @router.get(
        "/status",
        response_model=TaskStatusResponse,
        dependencies=[Depends(jwt_auth)],
        responses={403: {"model": ErrorResponse}},
        summary="Get task status",
        description="Status of current/last task"
    )
    async def get_task_status():
        """Get status of current or last task."""
        try:
            return service.get_task_status()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"status": "error", "error_code": "internal_error", "message": str(e)}
            )

    @router.get(
        "/cancel",
        response_model=TaskCancelResponse,
        dependencies=[Depends(jwt_auth)],
        responses={
            409: {"model": ErrorResponse}
        },
        summary="Cancel task",
        description="Cancel current task execution"
    )
    async def cancel_task():
        """Cancel current task."""
        try:
            return service.cancel_task()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"status": "error", "error_code": "internal_error", "message": str(e)}
            )

    return router
