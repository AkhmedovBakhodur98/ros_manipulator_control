"""Real ROS2 service implementation connecting to action servers."""

import uuid
import time
import threading
from typing import Optional
from datetime import datetime

from rclpy.node import Node
from rclpy.action import ActionClient
from fastapi import HTTPException

from ros_control.action import GetContainer, PlaceContainer

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


class RosService:
    """
    Real ROS2 service that connects to action servers.

    Supports /get_container and /place_container actions.
    get_items/put_items return 'action_not_available' since PickItemsFromWarehouse
    action type does not exist yet.
    """

    def __init__(self, node: Node):
        self.node = node
        self.logger = node.get_logger()

        self._task_lock = threading.Lock()
        self._current_task: Optional[TaskInfo] = None
        self._cancel_requested = False
        self._goal_handle = None

        # Action clients for existing servers
        self._get_container_client = ActionClient(
            node, GetContainer, '/get_container'
        )
        self._place_container_client = ActionClient(
            node, PlaceContainer, '/place_container'
        )

        self.logger.info('RosService initialized with action clients')

    def _is_busy(self) -> bool:
        """Check if a task is currently running."""
        with self._task_lock:
            if self._current_task is not None and self._current_task.finished_at is None:
                return True
        return False

    def _assert_not_busy(self):
        """Raise HTTPException(409) if a task is already running."""
        if self._is_busy():
            raise HTTPException(
                status_code=409,
                detail={
                    "status": "error",
                    "error_code": "task_in_progress",
                    "message": "Another task is currently running"
                }
            )

    def _set_task(self, task: TaskInfo):
        """Set the current task (thread-safe)."""
        with self._task_lock:
            self._current_task = task
            self._cancel_requested = False
            self._goal_handle = None

    def _update_task(self, **kwargs):
        """Update current task fields (thread-safe)."""
        with self._task_lock:
            if self._current_task is not None:
                for key, value in kwargs.items():
                    setattr(self._current_task, key, value)

    def _send_goal(self, action_client: ActionClient, goal_msg, task_id: str, operation: str):
        """
        Send a goal to an action server and wait for result.

        Called from a worker thread. Uses polling on future.done() since
        rclpy.spin() on the main thread resolves futures.
        """
        self.logger.info(f'Sending goal for {operation} (task: {task_id})')

        # Wait for server availability
        if not action_client.wait_for_server(timeout_sec=5.0):
            self._update_task(
                progress=0,
                error_code='server_unavailable',
                message=f'Action server for {operation} not available',
                finished_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat()
            )
            self.logger.error(f'Action server for {operation} not available')
            return

        # Send goal
        send_goal_future = action_client.send_goal_async(
            goal_msg,
            feedback_callback=lambda fb: self._on_feedback(fb, operation)
        )

        # Poll until goal is accepted/rejected
        while not send_goal_future.done():
            if self._cancel_requested:
                self._update_task(
                    progress=0,
                    message='Task cancelled before goal was accepted',
                    finished_at=datetime.utcnow().isoformat(),
                    updated_at=datetime.utcnow().isoformat()
                )
                return
            time.sleep(0.05)

        goal_handle = send_goal_future.result()
        if not goal_handle.accepted:
            self._update_task(
                progress=0,
                error_code='goal_rejected',
                message=f'Goal rejected by {operation} server',
                finished_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat()
            )
            self.logger.warn(f'Goal rejected by {operation} server')
            return

        self.logger.info(f'Goal accepted for {operation}')
        with self._task_lock:
            self._goal_handle = goal_handle

        # Check for cancellation
        if self._cancel_requested:
            self._do_cancel(goal_handle)
            return

        # Wait for result
        result_future = goal_handle.get_result_async()
        while not result_future.done():
            if self._cancel_requested:
                self._do_cancel(goal_handle)
                return
            time.sleep(0.05)

        result = result_future.result()
        action_result = result.result

        if action_result.success:
            self._update_task(
                progress=100,
                message=action_result.message or f'{operation} completed successfully',
                finished_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat()
            )
            self.logger.info(f'{operation} completed: {action_result.message}')
        else:
            self._update_task(
                progress=0,
                error_code='action_failed',
                message=action_result.message or f'{operation} failed',
                finished_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat()
            )
            self.logger.warn(f'{operation} failed: {action_result.message}')

    def _on_feedback(self, feedback_msg, operation: str):
        """Handle feedback from action server."""
        feedback = feedback_msg.feedback
        progress = int(feedback.progress_percentage)
        self._update_task(
            progress=progress,
            message=feedback.current_step,
            updated_at=datetime.utcnow().isoformat()
        )
        self.logger.info(f'{operation} feedback: {progress}% - {feedback.current_step}')

    def _do_cancel(self, goal_handle):
        """Cancel the active goal."""
        self.logger.info('Cancelling active goal')
        cancel_future = goal_handle.cancel_goal_async()
        while not cancel_future.done():
            time.sleep(0.05)
        self._update_task(
            progress=0,
            message='Task cancelled',
            finished_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat()
        )

    def _run_stub_worker(self, task_id: str, operation: str):
        """Worker for unsupported operations (get_items/put_items)."""
        self._update_task(
            error_code='action_not_available',
            message=f'{operation} action is not available (ROS2 action type not implemented)',
            progress=0,
            finished_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat()
        )
        self.logger.warn(f'{operation} requested but action type does not exist yet')

    # --- Public API (same interface as MockService) ---

    def is_ready(self) -> IsReadyResponse:
        """Check if action servers are reachable."""
        self.logger.info('Checking action server readiness')

        get_ok = self._get_container_client.wait_for_server(timeout_sec=2.0)
        place_ok = self._place_container_client.wait_for_server(timeout_sec=2.0)

        if get_ok and place_ok:
            self.logger.info('All action servers ready')
            return IsReadyResponse(status="ok")
        else:
            missing = []
            if not get_ok:
                missing.append('/get_container')
            if not place_ok:
                missing.append('/place_container')
            self.logger.warn(f'Action servers not ready: {missing}')
            return IsReadyResponse(status="not ready")

    def get_container(self, request: GetContainerRequest) -> AcceptedResponse:
        """Send get_container goal to ROS2 action server."""
        self._assert_not_busy()

        task_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        task = TaskInfo(
            task_id=task_id,
            progress=0,
            current_operation='getcontainer',
            started_at=now,
            updated_at=now,
            message='Task accepted, sending goal to /get_container'
        )
        self._set_task(task)

        goal = GetContainer.Goal()
        worker = threading.Thread(
            target=self._send_goal,
            args=(self._get_container_client, goal, task_id, 'getcontainer'),
            daemon=True
        )
        worker.start()

        self.logger.info(f'get_container task accepted: {task_id} (unload={request.unload})')
        return AcceptedResponse(status="ok", accepted=True)

    def return_container(self, request: ReturnContainerRequest) -> AcceptedResponse:
        """Send place_container goal to ROS2 action server."""
        self._assert_not_busy()

        task_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        task = TaskInfo(
            task_id=task_id,
            progress=0,
            current_operation='retcontainer',
            started_at=now,
            updated_at=now,
            message='Task accepted, sending goal to /place_container'
        )
        self._set_task(task)

        goal = PlaceContainer.Goal()
        worker = threading.Thread(
            target=self._send_goal,
            args=(self._place_container_client, goal, task_id, 'retcontainer'),
            daemon=True
        )
        worker.start()

        self.logger.info(f'return_container task accepted: {task_id} (unload={request.unload})')
        return AcceptedResponse(status="ok", accepted=True)

    def get_items(self, request: GetItemsRequest) -> AcceptedResponse:
        """Accept get_items task — immediately fails (action type not implemented)."""
        self._assert_not_busy()

        task_id = request.task_id
        now = datetime.utcnow().isoformat()

        task = TaskInfo(
            task_id=task_id,
            progress=0,
            current_operation='get_items',
            started_at=now,
            updated_at=now,
            message='Task accepted'
        )
        self._set_task(task)

        worker = threading.Thread(
            target=self._run_stub_worker,
            args=(task_id, 'get_items'),
            daemon=True
        )
        worker.start()

        self.logger.info(f'get_items task accepted: {task_id} (stub — will fail)')
        return AcceptedResponse(status="ok", accepted=True)

    def put_items(self, request: PutItemsRequest) -> AcceptedResponse:
        """Accept put_items task — immediately fails (action type not implemented)."""
        self._assert_not_busy()

        task_id = request.task_id
        now = datetime.utcnow().isoformat()

        task = TaskInfo(
            task_id=task_id,
            progress=0,
            current_operation='put_items',
            started_at=now,
            updated_at=now,
            message='Task accepted'
        )
        self._set_task(task)

        worker = threading.Thread(
            target=self._run_stub_worker,
            args=(task_id, 'put_items'),
            daemon=True
        )
        worker.start()

        self.logger.info(f'put_items task accepted: {task_id} (stub — will fail)')
        return AcceptedResponse(status="ok", accepted=True)

    def get_task_status(self) -> TaskStatusResponse:
        """Get status of current/last task."""
        with self._task_lock:
            if self._current_task is None:
                task = TaskInfo(
                    task_id='no-task',
                    progress=0,
                    current_operation='none',
                    message='No task executed yet'
                )
            else:
                task = self._current_task

        return TaskStatusResponse(status="ok", task=task)

    def cancel_task(self) -> TaskCancelResponse:
        """Cancel current task."""
        self.logger.info('Cancel task requested')

        with self._task_lock:
            if self._current_task is None or self._current_task.finished_at is not None:
                return TaskCancelResponse(status="ok")
            self._cancel_requested = True
            goal_handle = self._goal_handle

        # If we have an active goal handle, cancel it
        if goal_handle is not None:
            try:
                cancel_future = goal_handle.cancel_goal_async()
                # Poll for completion
                for _ in range(100):  # 5 second timeout
                    if cancel_future.done():
                        break
                    time.sleep(0.05)
            except Exception as e:
                self.logger.warn(f'Error cancelling goal: {e}')

        # Ensure the task is marked as finished
        with self._task_lock:
            if self._current_task is not None and self._current_task.finished_at is None:
                self._current_task.message = 'Task cancelled'
                self._current_task.progress = 0
                self._current_task.finished_at = datetime.utcnow().isoformat()
                self._current_task.updated_at = datetime.utcnow().isoformat()

        return TaskCancelResponse(status="ok")
