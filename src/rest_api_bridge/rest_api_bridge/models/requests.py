"""Request models for REST API Bridge."""

from pydantic import BaseModel, Field
from typing import List, Optional


class GetContainerRequest(BaseModel):
    """Request model for getting a container."""
    unload: bool = Field(..., description="Container type: false = for loading, true = for unloading")


class ReturnContainerRequest(BaseModel):
    """Request model for returning a container."""
    unload: bool = Field(..., description="Container type: false = for loading, true = for unloading")


class ItemInfo(BaseModel):
    """Item information for extraction."""
    image_id: str = Field(..., description="Item image ID")
    raw_id: int = Field(..., ge=0, description="Row number in box")


class ItemPlacement(BaseModel):
    """Item information for placement."""
    image_id: str = Field(..., description="Item image ID")
    cell_id: int = Field(..., ge=0, description="Cell number in container")
    row_id: int = Field(..., ge=0, description="Row number in box")
    position: dict = Field(..., description="Position coordinates: {x_side: float, y_side: float}")


class GetItemsRequest(BaseModel):
    """Request model for extracting items from box."""
    medicine_list: List[ItemInfo] = Field(..., description="List of items to extract")
    box_id: str = Field(..., description="Unique box identifier on warehouse")
    task_id: str = Field(..., description="Unique task identifier")


class PutItemsRequest(BaseModel):
    """Request model for placing items into box."""
    medicine_list: List[ItemPlacement] = Field(..., description="List of items to place")
    box_id: str = Field(..., description="Unique box identifier on warehouse")
    task_id: str = Field(..., description="Unique task identifier")


class TokenRequest(BaseModel):
    """Request model for JWT token generation."""
    client_id: str = Field(..., description="Client identifier")
    client_secret: str = Field(..., description="Client secret")
