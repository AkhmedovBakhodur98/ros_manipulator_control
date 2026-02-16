"""Response models for REST API Bridge."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str = Field(..., description="Service health status: 'ok' or 'not ready'")


class IsReadyResponse(BaseModel):
    """Response model for readiness check."""
    status: str = Field(..., description="System readiness status: 'ok' or 'not ready'")


class AcceptedResponse(BaseModel):
    """Response model for accepted async operations."""
    status: str = Field("ok", description="Operation status")
    accepted: bool = Field(True, description="Whether task was accepted")


class TaskInfo(BaseModel):
    """Task information model."""
    task_id: str = Field(..., description="Unique task identifier")
    progress: int = Field(..., ge=0, le=100, description="Task progress (0-100)")
    current_operation: str = Field(..., description="Current operation: get_items, is_ready, getcontainer, put_items, retcontainer")
    started_at: Optional[str] = Field(None, description="Task start timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    finished_at: Optional[str] = Field(None, description="Task completion timestamp")
    error_code: Optional[str] = Field(None, description="Error code if failed")
    message: Optional[str] = Field(None, description="Status or error message")
    medicine_qr: List[str] = Field(default_factory=list, description="List of DataMatrix IDs (for get_items)")
    container_id: Optional[str] = Field(None, description="Container QR code (for getcontainer)")


class TaskStatusResponse(BaseModel):
    """Response model for task status query."""
    status: str = Field("ok", description="Request status")
    task: TaskInfo = Field(..., description="Task information")


class TaskCancelResponse(BaseModel):
    """Response model for task cancellation."""
    status: str = Field("ok", description="Cancellation status")


class ErrorResponse(BaseModel):
    """Response model for errors."""
    status: str = Field("error", description="Error status")
    error_code: str = Field(..., description="Error code")
    message: Optional[str] = Field(None, description="Error message")


class TokenResponse(BaseModel):
    """Response model for JWT token."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
