"""Items operation router."""

from fastapi import APIRouter, Depends, HTTPException

from rest_api_bridge.models.requests import GetItemsRequest, PutItemsRequest
from rest_api_bridge.models.responses import AcceptedResponse, ErrorResponse
from rest_api_bridge.services.mock_service import MockService


def create_medicine_router(service: MockService, jwt_auth) -> APIRouter:
    """
    Create items operation router.

    Args:
        service: Service implementation (mock or real)
        jwt_auth: JWT authentication dependency

    Returns:
        FastAPI router for items endpoints
    """
    router = APIRouter(tags=["Items Operations"])

    @router.post(
        "/get_items",
        response_model=AcceptedResponse,
        dependencies=[Depends(jwt_auth)],
        responses={
            202: {"model": AcceptedResponse},
            400: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse}
        },
        status_code=202,
        summary="Get items",
        description="Task to extract items from specific box in warehouse (background task)"
    )
    async def get_items(request: GetItemsRequest):
        """Execute get items operation."""
        try:
            return service.get_items(request)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"status": "error", "error_code": "internal_error", "message": str(e)}
            )

    @router.post(
        "/put_items",
        response_model=AcceptedResponse,
        dependencies=[Depends(jwt_auth)],
        responses={
            202: {"model": AcceptedResponse},
            400: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse}
        },
        status_code=202,
        summary="Put items",
        description="Task to place items into specific box in warehouse (background task)"
    )
    async def put_items(request: PutItemsRequest):
        """Execute put items operation."""
        try:
            return service.put_items(request)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"status": "error", "error_code": "internal_error", "message": str(e)}
            )

    return router
