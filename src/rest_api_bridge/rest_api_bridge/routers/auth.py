"""Authentication router for JWT token generation."""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from typing import Dict

from rest_api_bridge.models.requests import TokenRequest
from rest_api_bridge.models.responses import TokenResponse, ErrorResponse

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_auth_router(config: Dict, logger) -> APIRouter:
    """
    Create authentication router.

    Args:
        config: Application configuration
        logger: ROS2 logger

    Returns:
        FastAPI router for authentication
    """
    router = APIRouter(prefix="/auth", tags=["Authentication"])

    auth_config = config.get('auth', {})
    jwt_config = auth_config.get('jwt', {})
    clients = auth_config.get('clients', {})
    allowed_clients = auth_config.get('allowed_clients', [])

    @router.post(
        "/token",
        response_model=TokenResponse,
        responses={401: {"model": ErrorResponse}},
        summary="Generate JWT token",
        description="Authenticate with client_id and client_secret to receive a JWT token"
    )
    async def get_token(request: TokenRequest):
        """Generate JWT access token for authenticated clients."""
        # Check if client is allowed
        if request.client_id not in allowed_clients:
            logger.warning(f'Authentication failed: client {request.client_id} not in allowed list')
            raise HTTPException(
                status_code=401,
                detail="Invalid client credentials"
            )

        # Check if client exists
        if request.client_id not in clients:
            logger.warning(f'Authentication failed: client {request.client_id} not found')
            raise HTTPException(
                status_code=401,
                detail="Invalid client credentials"
            )

        # Verify client secret
        stored_hash = clients[request.client_id]
        if not pwd_context.verify(request.client_secret, stored_hash):
            logger.warning(f'Authentication failed: invalid secret for client {request.client_id}')
            raise HTTPException(
                status_code=401,
                detail="Invalid client credentials"
            )

        # Generate JWT token
        expire_minutes = jwt_config.get('access_token_expire_minutes', 60)
        expire = datetime.utcnow() + timedelta(minutes=expire_minutes)

        token_data = {
            'sub': request.client_id,
            'exp': expire,
            'iat': datetime.utcnow(),
            'type': 'access'
        }

        secret_key = jwt_config.get('secret_key', 'default-secret')
        algorithm = jwt_config.get('algorithm', 'HS256')

        access_token = jwt.encode(token_data, secret_key, algorithm=algorithm)

        logger.info(f'JWT token generated for client: {request.client_id}')

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expire_minutes * 60
        )

    return router
