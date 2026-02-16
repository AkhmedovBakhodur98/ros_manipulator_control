"""JWT authentication middleware."""

from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from typing import Dict, Optional
from datetime import datetime


security = HTTPBearer(auto_error=False)


class JWTAuthMiddleware:
    """JWT authentication middleware for FastAPI."""

    def __init__(self, config: Dict, logger):
        """
        Initialize JWT auth middleware.

        Args:
            config: Application configuration
            logger: ROS2 logger
        """
        self.config = config
        self.logger = logger
        self.auth_config = config.get('auth', {})
        self.jwt_config = self.auth_config.get('jwt', {})
        self.enabled = self.auth_config.get('enabled', True)

    async def __call__(self, request: Request, credentials: Optional[HTTPAuthorizationCredentials]):
        """
        Validate JWT token from request.

        Args:
            request: FastAPI request
            credentials: HTTP authorization credentials

        Returns:
            Decoded token data if valid

        Raises:
            HTTPException: If authentication fails
        """
        # Skip auth check if disabled
        if not self.enabled:
            return {'sub': 'anonymous', 'auth_disabled': True}

        # Skip auth for token endpoint and health check
        if request.url.path in [
            f"{self.config.get('api_base_path', '/api/v1')}/auth/token",
            f"{self.config.get('api_base_path', '/api/v1')}/health"
        ]:
            return {'sub': 'public', 'auth_skipped': True}

        # Check if credentials provided
        if not credentials:
            self.logger.warning('Authentication failed: No credentials provided')
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Verify token
        try:
            token = credentials.credentials
            secret_key = self.jwt_config.get('secret_key', 'default-secret')
            algorithm = self.jwt_config.get('algorithm', 'HS256')

            payload = jwt.decode(token, secret_key, algorithms=[algorithm])

            # Check token expiration
            exp = payload.get('exp')
            if exp:
                exp_datetime = datetime.fromtimestamp(exp)
                if exp_datetime < datetime.utcnow():
                    self.logger.warning('Authentication failed: Token expired')
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token expired",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

            # Check if client is allowed
            client_id = payload.get('sub')
            allowed_clients = self.auth_config.get('allowed_clients', [])
            if client_id not in allowed_clients:
                self.logger.warning(f'Authentication failed: Client {client_id} not allowed')
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Client not authorized",
                )

            self.logger.debug(f'Authentication successful for client: {client_id}')
            return payload

        except JWTError as e:
            self.logger.warning(f'Authentication failed: Invalid token - {str(e)}')
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )


def create_jwt_dependency(config: Dict, logger):
    """
    Create JWT authentication dependency.

    Args:
        config: Application configuration
        logger: ROS2 logger

    Returns:
        FastAPI dependency for JWT authentication
    """
    middleware = JWTAuthMiddleware(config, logger)

    async def jwt_auth(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
    ) -> Dict:
        """JWT authentication dependency."""
        return await middleware(request, credentials)

    return jwt_auth
