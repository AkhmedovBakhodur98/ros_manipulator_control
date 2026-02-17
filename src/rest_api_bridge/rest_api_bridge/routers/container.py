"""Container operation router."""

from fastapi import APIRouter, Depends, HTTPException

from rest_api_bridge.models.requests import GetContainerRequest, ReturnContainerRequest
from rest_api_bridge.models.responses import AcceptedResponse, ErrorResponse
from rest_api_bridge.services.mock_service import MockService


def create_container_router(service: MockService, jwt_auth) -> APIRouter:
    """
    Create container operation router.

    Args:
        service: Service implementation (mock or real)
        jwt_auth: JWT authentication dependency

    Returns:
        FastAPI router for container endpoints
    """
    router = APIRouter(tags=["Container Operations"])

    @router.post(
        "/getcontainer",
        response_model=AcceptedResponse,
        dependencies=[Depends(jwt_auth)],
        responses={
            202: {"model": AcceptedResponse},
            400: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse}
        },
        status_code=202,
        summary="Get container",
        description="Task to attach empty container to platform (background task)"
    )
    async def get_container(request: GetContainerRequest):
        """Execute get container operation."""
        try:
            return service.get_container(request)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"status": "error", "error_code": "internal_error", "message": str(e)}
            )

    @router.get(
        "/retcontainer",
        response_model=AcceptedResponse,
        dependencies=[Depends(jwt_auth)],
        responses={
            202: {"model": AcceptedResponse},
            400: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse}
        },
        status_code=202,
        summary="Return container",
        description="Task to return container (background task)"
    )
    async def return_container(unload: bool):
        """Execute return container operation."""
        try:
            request = ReturnContainerRequest(unload=unload)
            return service.return_container(request)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"status": "error", "error_code": "internal_error", "message": str(e)}
            )

    return router
