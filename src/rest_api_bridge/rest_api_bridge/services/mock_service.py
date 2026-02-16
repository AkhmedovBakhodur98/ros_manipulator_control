"""Mock service implementation for testing without ROS2 dependencies."""

import uuid
from typing import Dict, Optional, Any
from datetime import datetime
from rclpy.node import Node

from rest_api_bridge.models.requests import (
    GetContainerRequest,
    ReturnContainerRequest,
    GetItemsRequest,
    PutItemsRequest
)
from rest_api_bridge.models.responses import (
    AcceptedResponse,
    TaskStatusResponse,
    TaskCancelResponse,
    IsReadyResponse,
    TaskInfo
)


class MockService:
    """
    Mock service that simulates robot operations.

    Returns successful responses immediately without actual robot interaction.
    Useful for API testing and frontend development.
    """

    def __init__(self, node: Node):
        """
        Initialize mock service.

        Args:
            node: ROS2 node for logging
        """
        self.node = node
        self.logger = node.get_logger()
        self.current_task: Optional[TaskInfo] = None

    def get_container(self, request: GetContainerRequest) -> AcceptedResponse:
        """
        Mock get container operation.

        Args:
            request: Container request

        Returns:
            Accepted response
        """
        task_id = str(uuid.uuid4())
        self.logger.info(f'Mock: Get container (unload={request.unload}, task: {task_id})')

        self.current_task = TaskInfo(
            task_id=task_id,
            progress=100,
            current_operation='getcontainer',
            started_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            finished_at=datetime.utcnow().isoformat(),
            message='Container retrieved successfully (mock)',
            container_id=f'CNT-{uuid.uuid4().hex[:8].upper()}'
        )

        return AcceptedResponse(status="ok", accepted=True)

    def return_container(self, request: ReturnContainerRequest) -> AcceptedResponse:
        """
        Mock return container operation.

        Args:
            request: Return container request

        Returns:
            Accepted response
        """
        task_id = str(uuid.uuid4())
        self.logger.info(f'Mock: Return container (unload={request.unload}, task: {task_id})')

        self.current_task = TaskInfo(
            task_id=task_id,
            progress=100,
            current_operation='retcontainer',
            started_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            finished_at=datetime.utcnow().isoformat(),
            message='Container returned successfully (mock)'
        )

        return AcceptedResponse(status="ok", accepted=True)

    def get_items(self, request: GetItemsRequest) -> AcceptedResponse:
        """
        Mock get items operation.

        Args:
            request: Items extraction request

        Returns:
            Accepted response
        """
        self.logger.info(
            f'Mock: Get items from box {request.box_id} '
            f'({len(request.medicine_list)} items, task: {request.task_id})'
        )

        # Generate mock QR codes for extracted items
        medicine_qr = [f'DM-{uuid.uuid4().hex[:12].upper()}' for _ in request.medicine_list]

        self.current_task = TaskInfo(
            task_id=request.task_id,
            progress=100,
            current_operation='get_items',
            started_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            finished_at=datetime.utcnow().isoformat(),
            message=f'Retrieved {len(request.medicine_list)} item(s) from {request.box_id} (mock)',
            medicine_qr=medicine_qr
        )

        return AcceptedResponse(status="ok", accepted=True)

    def put_items(self, request: PutItemsRequest) -> AcceptedResponse:
        """
        Mock put items operation.

        Args:
            request: Items placement request

        Returns:
            Accepted response
        """
        self.logger.info(
            f'Mock: Put items to box {request.box_id} '
            f'({len(request.medicine_list)} items, task: {request.task_id})'
        )

        self.current_task = TaskInfo(
            task_id=request.task_id,
            progress=100,
            current_operation='put_items',
            started_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            finished_at=datetime.utcnow().isoformat(),
            message=f'Placed {len(request.medicine_list)} item(s) to {request.box_id} (mock)'
        )

        return AcceptedResponse(status="ok", accepted=True)

    def get_task_status(self) -> TaskStatusResponse:
        """
        Get status of current/last task.

        Returns:
            Task status response
        """
        if not self.current_task:
            # Return default empty task if no task exists
            self.current_task = TaskInfo(
                task_id='no-task',
                progress=0,
                current_operation='none',
                message='No task executed yet'
            )

        return TaskStatusResponse(
            status="ok",
            task=self.current_task
        )

    def cancel_task(self) -> TaskCancelResponse:
        """
        Cancel current task.

        Returns:
            Task cancellation response
        """
        self.logger.info('Mock: Cancel task')

        if self.current_task and self.current_task.progress < 100:
            self.current_task.progress = 0
            self.current_task.message = 'Task cancelled'
            self.current_task.finished_at = datetime.utcnow().isoformat()

        return TaskCancelResponse(status="ok")

    def is_ready(self) -> IsReadyResponse:
        """
        Check if system is ready for operations.

        Returns:
            System readiness status
        """
        self.logger.info('Mock: Readiness check')

        return IsReadyResponse(status="ok")
