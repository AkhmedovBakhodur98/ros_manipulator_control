"""
ScaraClient — composable SCARA arm control library.

Attaches to any ROS2 node and provides high-level control via
FollowJointTrajectory action clients. Supports optional Z-axis
through a separate controller.
"""

import math
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Tuple

import yaml

from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.callback_groups import ReentrantCallbackGroup

from sensor_msgs.msg import JointState
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint
from builtin_interfaces.msg import Duration
from std_srvs.srv import Trigger

from ament_index_python.packages import get_package_share_directory


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ScaraResult:
    success: bool
    message: str
    joint_positions: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    z_position: float = 0.0
    tcp_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    execution_time: float = 0.0


class ElbowConfig(Enum):
    ELBOW_UP = "elbow_up"
    ELBOW_DOWN = "elbow_down"


@dataclass
class CartesianPose:
    x: float
    y: float
    phi: float


@dataclass
class IKSolution:
    shoulder: float
    elbow: float
    wrist: float
    valid: bool
    elbow_config: ElbowConfig


@dataclass
class IKDiagnostic:
    reason: str  # 'too_far' | 'too_close' | 'joint_limit' | 'reachable'
    suggested_x_offset: float
    suggested_z_offset: float
    distance: float
    workspace_min: float
    workspace_max: float


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ScaraNotReady(RuntimeError):
    """SCARA controller action server is not available."""


class ZAxisNotConfigured(RuntimeError):
    """Z-axis method called but Z-axis is not configured."""


class ZAxisNotReady(RuntimeError):
    """Z-axis controller action server is not available."""


# ---------------------------------------------------------------------------
# ScaraClient
# ---------------------------------------------------------------------------

class ScaraClient:
    """Composable SCARA arm control — attach to any ROS2 node."""

    # Joint names (fixed by URDF)
    SHOULDER_JOINT = 'scara_shoulder_joint'
    ELBOW_JOINT = 'scara_elbow_joint'
    WRIST_JOINT = 'scara_wrist_joint'
    JOINT_NAMES = [SHOULDER_JOINT, ELBOW_JOINT, WRIST_JOINT]

    def __init__(self, node: Node, config_path: str = None):
        self._node = node
        self._logger = node.get_logger()
        self._lock = threading.Lock()
        self._joint_states: dict[str, float] = {}

        # Callback group for async action/service calls
        self._cb_group = ReentrantCallbackGroup()

        # Load config
        self._config = self._load_config(config_path)
        self._client_cfg = self._config.get('scara_client', {})

        # Kinematic parameters
        kin = self._config['kinematics']
        self._L1: float = kin['L1']
        self._L2: float = kin['L2']

        # Joint limits from config
        joints_cfg = self._config['joints']
        self._joint_limits: dict[str, dict] = {}
        for jname in self.JOINT_NAMES:
            self._joint_limits[jname] = joints_cfg[jname]['limits']

        # Defaults
        defaults = self._client_cfg.get('defaults', {})
        self._default_velocity = defaults.get('velocity_scaling', 0.5)
        self._default_linear_velocity = defaults.get('linear_velocity', 0.1)
        self._default_step_size = defaults.get('linear_step_size', 0.005)
        self._default_elbow_up = defaults.get('elbow_up', True)
        self._timeout = self._client_cfg.get('timeout', 30.0)

        # ---- Joint state subscriber (BEST_EFFORT, matches existing pattern) ----
        qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, depth=10)
        topic = self._client_cfg.get('joint_states_topic', '/joint_states')
        self._joint_state_sub = node.create_subscription(
            JointState, topic, self._joint_state_cb, qos,
            callback_group=self._cb_group,
        )

        # ---- SCARA controller action client (always required) ----
        scara_action = self._client_cfg.get(
            'controller_action',
            '/scara_controller/follow_joint_trajectory',
        )
        self._scara_client = ActionClient(
            node, FollowJointTrajectory, scara_action,
            callback_group=self._cb_group,
        )

        # ---- Z-axis controller (optional) ----
        z_cfg = self._client_cfg.get('z_axis', {})
        self._z_enabled = z_cfg.get('enabled', False)
        self._z_client: Optional[ActionClient] = None
        self._z_joint_name: Optional[str] = None
        self._z_limits: Optional[dict] = None

        if self._z_enabled:
            self._z_joint_name = z_cfg['joint_name']
            self._z_limits = z_cfg.get('limits', {})
            z_action = z_cfg.get(
                'controller_action',
                '/picker_z_controller/follow_joint_trajectory',
            )
            self._z_client = ActionClient(
                node, FollowJointTrajectory, z_action,
                callback_group=self._cb_group,
            )

        # ---- Tool config ----
        self._tool_cfg = self._client_cfg.get('tool', {'type': 'none'})
        self._tool_activate_client: Optional[object] = None
        self._tool_deactivate_client: Optional[object] = None

        if self._tool_cfg.get('type') == 'service':
            self._tool_activate_client = node.create_client(
                Trigger, self._tool_cfg['activate'],
                callback_group=self._cb_group,
            )
            self._tool_deactivate_client = node.create_client(
                Trigger, self._tool_cfg['deactivate'],
                callback_group=self._cb_group,
            )

        # ---- Elbow flip config ----
        flip_cfg = self._client_cfg.get('elbow_flip', {})
        self._flip_enabled = flip_cfg.get('enabled', False)
        self._flip_margin = flip_cfg.get('joint_limit_margin', 0.15)
        self._flip_duration = flip_cfg.get('flip_duration', 1.5)
        self._flip_z_offset = flip_cfg.get('z_unhook_offset', 0.03)

        # ---- Linear motion config ----
        lin_cfg = self._client_cfg.get('linear_motion', {})
        self._max_deviation = lin_cfg.get('max_deviation', 0.005)

        # ---- Home config ----
        self._home = self._client_cfg.get('home', {
            'shoulder': 0.0, 'elbow': 0.0, 'wrist': 0.0, 'z': 0.0,
        })

        self._logger.info('ScaraClient initialised '
                          f'(L1={self._L1}, L2={self._L2}, '
                          f'z_axis={self._z_enabled})')

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_config(self, config_path: Optional[str]) -> dict:
        if config_path is not None:
            p = Path(config_path)
        else:
            # Auto-discover from scara_description
            try:
                pkg_share = get_package_share_directory('scara_description')
                p = Path(pkg_share) / 'config' / 'scara_params.yaml'
            except Exception:
                # Source fallback
                p = (Path(__file__).resolve().parents[3]
                     / 'scara_description' / 'config' / 'scara_params.yaml')

        if not p.exists():
            raise FileNotFoundError(
                f'scara_params.yaml not found at {p}')

        with open(p, 'r') as f:
            data = yaml.safe_load(f)

        self._logger.info(f'Loaded SCARA config from {p}')
        return data

    # ------------------------------------------------------------------
    # Joint state callback
    # ------------------------------------------------------------------

    def _joint_state_cb(self, msg: JointState):
        with self._lock:
            for i, name in enumerate(msg.name):
                if i < len(msg.position):
                    self._joint_states[name] = msg.position[i]

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def get_joint_positions(self) -> Tuple[float, float, float]:
        """Return current (shoulder, elbow, wrist) angles [rad]."""
        with self._lock:
            return (
                self._joint_states.get(self.SHOULDER_JOINT, 0.0),
                self._joint_states.get(self.ELBOW_JOINT, 0.0),
                self._joint_states.get(self.WRIST_JOINT, 0.0),
            )

    def get_z_position(self) -> float:
        """Return current Z position [m]. Raises if Z not configured."""
        if not self._z_enabled:
            raise ZAxisNotConfigured('Z-axis is not configured')
        with self._lock:
            return self._joint_states.get(self._z_joint_name, 0.0)

    def get_tcp_position(self) -> Tuple[float, float, float]:
        """Return current TCP (x, y, phi) via FK."""
        s, e, w = self.get_joint_positions()
        return self.compute_fk(s, e, w)

    def get_tcp_position_3d(self) -> Tuple[float, float, float, float]:
        """Return (x, y, z, phi). Raises if Z not configured."""
        x, y, phi = self.get_tcp_position()
        z = self.get_z_position()
        return (x, y, z, phi)

    def has_z_axis(self) -> bool:
        return self._z_enabled

    def get_elbow_config(self) -> ElbowConfig:
        """Current elbow config from joint angle."""
        _, theta2, _ = self.get_joint_positions()
        return ElbowConfig.ELBOW_UP if theta2 >= 0 else ElbowConfig.ELBOW_DOWN

    # ------------------------------------------------------------------
    # Kinematics (pure computation)
    # ------------------------------------------------------------------

    def compute_fk(
        self, shoulder: float, elbow: float, wrist: float,
    ) -> Tuple[float, float, float]:
        """FK: (theta1, theta2, theta3) -> (x, y, phi)."""
        x = self._L1 * math.cos(shoulder) + self._L2 * math.cos(shoulder + elbow)
        y = self._L1 * math.sin(shoulder) + self._L2 * math.sin(shoulder + elbow)
        phi = shoulder + elbow + wrist
        return (x, y, phi)

    def compute_ik(
        self,
        x: float,
        y: float,
        orientation: float = 0.0,
        elbow_up: bool = True,
    ) -> Tuple[float, float, float]:
        """IK: (x, y, phi) -> (theta1, theta2, theta3). Raises ValueError."""
        d_sq = x * x + y * y
        d = math.sqrt(d_sq)

        if d < 1e-9:
            raise ValueError('Target is at the origin')

        cos_t2 = (d_sq - self._L1**2 - self._L2**2) / (2.0 * self._L1 * self._L2)
        if abs(cos_t2) > 1.0:
            raise ValueError(
                f'Target ({x:.4f}, {y:.4f}) unreachable: '
                f'distance={d:.4f}, workspace=[{self._L1 - self._L2:.4f}, {self._L1 + self._L2:.4f}]'
            )

        sin_t2 = math.sqrt(1.0 - cos_t2 * cos_t2)
        if not elbow_up:
            sin_t2 = -sin_t2

        theta2 = math.atan2(sin_t2, cos_t2)
        theta1 = math.atan2(y, x) - math.atan2(
            self._L2 * sin_t2, self._L1 + self._L2 * cos_t2,
        )
        theta3 = orientation - theta1 - theta2

        return (theta1, theta2, theta3)

    def is_reachable(self, x: float, y: float) -> bool:
        d = math.sqrt(x * x + y * y)
        return (self._L1 - self._L2) <= d <= (self._L1 + self._L2)

    def diagnose_ik_failure(
        self, x: float, y: float, orientation: float = 0.0,
    ) -> IKDiagnostic:
        d = math.sqrt(x * x + y * y)
        ws_min = self._L1 - self._L2
        ws_max = self._L1 + self._L2

        if d > ws_max:
            return IKDiagnostic(
                reason='too_far',
                suggested_x_offset=d - ws_max,
                suggested_z_offset=0.0,
                distance=d,
                workspace_min=ws_min,
                workspace_max=ws_max,
            )

        if d < ws_min:
            return IKDiagnostic(
                reason='too_close',
                suggested_x_offset=ws_min - d,
                suggested_z_offset=0.0,
                distance=d,
                workspace_min=ws_min,
                workspace_max=ws_max,
            )

        # Reachable in workspace — check joint limits
        for elbow_up in (True, False):
            try:
                t1, t2, t3 = self.compute_ik(x, y, orientation, elbow_up)
                if self._joints_within_limits(t1, t2, t3):
                    return IKDiagnostic(
                        reason='reachable',
                        suggested_x_offset=0.0,
                        suggested_z_offset=0.0,
                        distance=d,
                        workspace_min=ws_min,
                        workspace_max=ws_max,
                    )
            except ValueError:
                pass

        return IKDiagnostic(
            reason='joint_limit',
            suggested_x_offset=0.0,
            suggested_z_offset=0.0,
            distance=d,
            workspace_min=ws_min,
            workspace_max=ws_max,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _joints_within_limits(self, t1: float, t2: float, t3: float) -> bool:
        limits = self._joint_limits
        if not (limits[self.SHOULDER_JOINT]['lower'] <= t1 <= limits[self.SHOULDER_JOINT]['upper']):
            return False
        if not (limits[self.ELBOW_JOINT]['lower'] <= t2 <= limits[self.ELBOW_JOINT]['upper']):
            return False
        if not (limits[self.WRIST_JOINT]['lower'] <= t3 <= limits[self.WRIST_JOINT]['upper']):
            return False
        return True

    def _make_duration(self, seconds: float) -> Duration:
        sec = int(seconds)
        nanosec = int((seconds - sec) * 1e9)
        return Duration(sec=sec, nanosec=nanosec)

    def _calc_scara_time(
        self, targets: list[float], velocity: float,
    ) -> float:
        """Bottleneck time: max(distance / scaled_velocity) across joints."""
        current = self.get_joint_positions()
        max_t = 0.0
        for i, jname in enumerate(self.JOINT_NAMES):
            dist = abs(targets[i] - current[i])
            max_vel = self._joint_limits[jname]['velocity'] * velocity
            if max_vel > 0:
                max_t = max(max_t, dist / max_vel)
        return max(max_t, 0.1)  # minimum 100ms

    def _build_result(
        self, success: bool, message: str, start_time: float,
    ) -> ScaraResult:
        s, e, w = self.get_joint_positions()
        x, y, phi = self.compute_fk(s, e, w)
        z = 0.0
        if self._z_enabled:
            with self._lock:
                z = self._joint_states.get(self._z_joint_name, 0.0)
        return ScaraResult(
            success=success,
            message=message,
            joint_positions=(s, e, w),
            z_position=z,
            tcp_position=(x, y, phi),
            execution_time=time.time() - start_time,
        )

    # ------------------------------------------------------------------
    # Low-level trajectory execution
    # ------------------------------------------------------------------

    async def _send_scara_trajectory(
        self, points: list[JointTrajectoryPoint],
    ) -> Tuple[bool, str]:
        """Send multi-point trajectory to SCARA controller."""
        if not self._scara_client.wait_for_server(timeout_sec=5.0):
            raise ScaraNotReady('SCARA controller action server not available')

        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = list(self.JOINT_NAMES)
        goal.trajectory.points = points

        handle = await self._scara_client.send_goal_async(goal)
        if not handle.accepted:
            return False, 'SCARA trajectory goal rejected'

        result = await handle.get_result_async()
        rc = result.result.error_code
        if rc == FollowJointTrajectory.Result.SUCCESSFUL:
            return True, 'OK'
        return False, f'Trajectory failed (error_code={rc})'

    async def _send_z_trajectory(
        self, z_target: float, velocity: float,
    ) -> Tuple[bool, str]:
        """Send single-point trajectory to Z controller."""
        if not self._z_enabled:
            raise ZAxisNotConfigured('Z-axis is not configured')
        if self._z_client is None:
            raise ZAxisNotReady('Z-axis action client not created')
        if not self._z_client.wait_for_server(timeout_sec=5.0):
            raise ZAxisNotReady('Z controller action server not available')

        # Validate limits
        if self._z_limits:
            lo = self._z_limits.get('lower', float('-inf'))
            hi = self._z_limits.get('upper', float('inf'))
            if not (lo <= z_target <= hi):
                return False, (
                    f'Z target {z_target:.4f} outside limits [{lo}, {hi}]')

        # Time calculation
        current_z = self.get_z_position()
        dist = abs(z_target - current_z)
        max_vel = self._z_limits.get('velocity', 1.0) * velocity
        move_time = max(dist / max_vel if max_vel > 0 else 1.0, 0.1)

        point = JointTrajectoryPoint()
        point.positions = [z_target]
        point.time_from_start = self._make_duration(move_time)

        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = [self._z_joint_name]
        goal.trajectory.points = [point]

        handle = await self._z_client.send_goal_async(goal)
        if not handle.accepted:
            return False, 'Z trajectory goal rejected'

        result = await handle.get_result_async()
        rc = result.result.error_code
        if rc == FollowJointTrajectory.Result.SUCCESSFUL:
            return True, 'OK'
        return False, f'Z trajectory failed (error_code={rc})'

    # ------------------------------------------------------------------
    # Motion: joints
    # ------------------------------------------------------------------

    async def move_joints(
        self,
        shoulder: float = None,
        elbow: float = None,
        wrist: float = None,
        velocity: float = 1.0,
    ) -> ScaraResult:
        """Move SCARA joints. None = keep current position."""
        t0 = time.time()
        cur_s, cur_e, cur_w = self.get_joint_positions()
        targets = [
            shoulder if shoulder is not None else cur_s,
            elbow if elbow is not None else cur_e,
            wrist if wrist is not None else cur_w,
        ]

        # Validate limits
        for i, jname in enumerate(self.JOINT_NAMES):
            lo = self._joint_limits[jname]['lower']
            hi = self._joint_limits[jname]['upper']
            if not (lo <= targets[i] <= hi):
                return self._build_result(
                    False,
                    f'{jname} target {targets[i]:.4f} outside limits [{lo}, {hi}]',
                    t0,
                )

        move_time = self._calc_scara_time(targets, velocity)
        point = JointTrajectoryPoint()
        point.positions = targets
        point.time_from_start = self._make_duration(move_time)

        ok, msg = await self._send_scara_trajectory([point])
        return self._build_result(ok, msg, t0)

    # ------------------------------------------------------------------
    # Motion: Z-axis
    # ------------------------------------------------------------------

    async def move_z(
        self, z: float, velocity: float = 1.0,
    ) -> ScaraResult:
        """Move Z-axis. Raises ZAxisNotConfigured if unavailable."""
        t0 = time.time()
        ok, msg = await self._send_z_trajectory(z, velocity)
        return self._build_result(ok, msg, t0)

    # ------------------------------------------------------------------
    # Motion: IK point-to-point
    # ------------------------------------------------------------------

    async def move_to_point(
        self,
        x: float,
        y: float,
        z: float = None,
        orientation: float = None,
        elbow_up: bool = True,
        velocity: float = 1.0,
    ) -> ScaraResult:
        """Move TCP to Cartesian point via IK. Z first, then XY."""
        t0 = time.time()

        # Z first
        if z is not None:
            ok, msg = await self._send_z_trajectory(z, velocity)
            if not ok:
                return self._build_result(False, f'Z move failed: {msg}', t0)

        # Orientation: None = keep current wrist angle
        if orientation is None:
            _, _, cur_w = self.get_joint_positions()
            cur_s, cur_e, _ = self.get_joint_positions()
            orientation = cur_s + cur_e + cur_w  # current phi

        # IK
        try:
            t1, t2, t3 = self.compute_ik(x, y, orientation, elbow_up)
        except ValueError as exc:
            return self._build_result(False, str(exc), t0)

        if not self._joints_within_limits(t1, t2, t3):
            # Try alternate elbow
            try:
                t1, t2, t3 = self.compute_ik(x, y, orientation, not elbow_up)
                if not self._joints_within_limits(t1, t2, t3):
                    return self._build_result(
                        False, 'Both IK solutions exceed joint limits', t0)
            except ValueError as exc:
                return self._build_result(False, str(exc), t0)

        targets = [t1, t2, t3]
        move_time = self._calc_scara_time(targets, velocity)
        point = JointTrajectoryPoint()
        point.positions = targets
        point.time_from_start = self._make_duration(move_time)

        ok, msg = await self._send_scara_trajectory([point])
        return self._build_result(ok, msg, t0)

    # ------------------------------------------------------------------
    # Motion: linear (Cartesian interpolation)
    # ------------------------------------------------------------------

    async def move_linear(
        self,
        x: float,
        y: float,
        z: float = None,
        orientation: float = None,
        velocity: float = 0.1,
        step_size: float = 0.005,
        allow_elbow_flip: bool = False,
        on_before_flip: Callable = None,
        on_after_flip: Callable = None,
    ) -> ScaraResult:
        """Straight-line TCP motion. Z first, then linear XY."""
        t0 = time.time()

        # Z first
        if z is not None:
            ok, msg = await self._send_z_trajectory(z, self._default_velocity)
            if not ok:
                return self._build_result(False, f'Z move failed: {msg}', t0)

        # Current TCP
        cur_s, cur_e, cur_w = self.get_joint_positions()
        x0, y0, phi0 = self.compute_fk(cur_s, cur_e, cur_w)
        target_phi = orientation if orientation is not None else phi0

        dx = x - x0
        dy = y - y0
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1e-6:
            return self._build_result(True, 'Already at target', t0)

        n_steps = max(int(math.ceil(dist / step_size)), 1)
        current_elbow_up = (cur_e >= 0)

        # Plan waypoints
        waypoints: list[list[float]] = []
        for i in range(1, n_steps + 1):
            frac = i / n_steps
            wx = x0 + dx * frac
            wy = y0 + dy * frac
            wphi = phi0 + (target_phi - phi0) * frac

            try:
                t1, t2, t3 = self.compute_ik(wx, wy, wphi, current_elbow_up)
            except ValueError as exc:
                if allow_elbow_flip:
                    return await self.move_linear_with_flip(
                        x, y, z=None, orientation=orientation,
                        velocity=velocity, step_size=step_size,
                        on_before_flip=on_before_flip,
                        on_after_flip=on_after_flip,
                    )
                return self._build_result(
                    False, f'Waypoint {i}/{n_steps} unreachable: {exc}', t0)

            if not self._joints_within_limits(t1, t2, t3):
                if allow_elbow_flip:
                    return await self.move_linear_with_flip(
                        x, y, z=None, orientation=orientation,
                        velocity=velocity, step_size=step_size,
                        on_before_flip=on_before_flip,
                        on_after_flip=on_after_flip,
                    )
                return self._build_result(
                    False,
                    f'Waypoint {i}/{n_steps} exceeds joint limits',
                    t0,
                )

            waypoints.append([t1, t2, t3])

        # Verify linearity (FK deviation check)
        for i, wp in enumerate(waypoints):
            frac = (i + 1) / n_steps
            ideal_x = x0 + dx * frac
            ideal_y = y0 + dy * frac
            fk_x, fk_y, _ = self.compute_fk(wp[0], wp[1], wp[2])
            dev = math.sqrt((fk_x - ideal_x)**2 + (fk_y - ideal_y)**2)
            if dev > self._max_deviation:
                return self._build_result(
                    False,
                    f'Linear deviation {dev:.4f}m exceeds max {self._max_deviation}m '
                    f'at waypoint {i + 1}/{n_steps}',
                    t0,
                )

        # Build multi-point trajectory
        time_per_step = step_size / velocity if velocity > 0 else 0.1
        points: list[JointTrajectoryPoint] = []
        for i, wp in enumerate(waypoints):
            pt = JointTrajectoryPoint()
            pt.positions = wp
            pt.time_from_start = self._make_duration(time_per_step * (i + 1))
            points.append(pt)

        ok, msg = await self._send_scara_trajectory(points)
        return self._build_result(ok, msg, t0)

    # ------------------------------------------------------------------
    # Motion: linear with elbow flip
    # ------------------------------------------------------------------

    async def move_linear_with_flip(
        self,
        x: float,
        y: float,
        z: float = None,
        orientation: float = None,
        velocity: float = 0.1,
        step_size: float = 0.005,
        on_before_flip: Callable = None,
        on_after_flip: Callable = None,
    ) -> ScaraResult:
        """Linear motion with automatic elbow reconfiguration at limit."""
        t0 = time.time()

        # Z first
        if z is not None:
            ok, msg = await self._send_z_trajectory(z, self._default_velocity)
            if not ok:
                return self._build_result(False, f'Z move failed: {msg}', t0)

        cur_s, cur_e, cur_w = self.get_joint_positions()
        x0, y0, phi0 = self.compute_fk(cur_s, cur_e, cur_w)
        target_phi = orientation if orientation is not None else phi0
        current_elbow_up = (cur_e >= 0)

        dx = x - x0
        dy = y - y0
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1e-6:
            return self._build_result(True, 'Already at target', t0)

        n_steps = max(int(math.ceil(dist / step_size)), 1)
        elbow_limit_lo = self._joint_limits[self.ELBOW_JOINT]['lower']
        elbow_limit_hi = self._joint_limits[self.ELBOW_JOINT]['upper']

        # Plan segment 1 with current elbow config, find flip point
        seg1: list[list[float]] = []
        flip_idx: Optional[int] = None

        for i in range(1, n_steps + 1):
            frac = i / n_steps
            wx = x0 + dx * frac
            wy = y0 + dy * frac
            wphi = phi0 + (target_phi - phi0) * frac

            try:
                t1, t2, t3 = self.compute_ik(wx, wy, wphi, current_elbow_up)
            except ValueError:
                flip_idx = i - 1
                break

            # Check margin
            if (t2 > elbow_limit_hi - self._flip_margin or
                    t2 < elbow_limit_lo + self._flip_margin):
                flip_idx = i
                seg1.append([t1, t2, t3])
                break

            if not self._joints_within_limits(t1, t2, t3):
                flip_idx = i - 1
                break

            seg1.append([t1, t2, t3])

        # No flip needed — execute straight
        if flip_idx is None:
            time_per_step = step_size / velocity if velocity > 0 else 0.1
            points = []
            for i, wp in enumerate(seg1):
                pt = JointTrajectoryPoint()
                pt.positions = wp
                pt.time_from_start = self._make_duration(time_per_step * (i + 1))
                points.append(pt)
            ok, msg = await self._send_scara_trajectory(points)
            return self._build_result(ok, msg, t0)

        if not seg1:
            return self._build_result(
                False, 'Cannot plan first segment — flip at start', t0)

        # Plan segment 2 with alternate elbow config
        alt_elbow_up = not current_elbow_up
        seg2: list[list[float]] = []
        for i in range(flip_idx + 1, n_steps + 1):
            frac = i / n_steps
            wx = x0 + dx * frac
            wy = y0 + dy * frac
            wphi = phi0 + (target_phi - phi0) * frac

            try:
                t1, t2, t3 = self.compute_ik(wx, wy, wphi, alt_elbow_up)
            except ValueError as exc:
                return self._build_result(
                    False, f'Segment 2 waypoint unreachable: {exc}', t0)

            if not self._joints_within_limits(t1, t2, t3):
                return self._build_result(
                    False, 'Segment 2 exceeds joint limits', t0)

            seg2.append([t1, t2, t3])

        if not seg2:
            return self._build_result(
                False, 'No waypoints in segment 2 after flip', t0)

        # Execute segment 1
        time_per_step = step_size / velocity if velocity > 0 else 0.1
        pts1 = []
        for i, wp in enumerate(seg1):
            pt = JointTrajectoryPoint()
            pt.positions = wp
            pt.time_from_start = self._make_duration(time_per_step * (i + 1))
            pts1.append(pt)

        ok, msg = await self._send_scara_trajectory(pts1)
        if not ok:
            return self._build_result(False, f'Segment 1 failed: {msg}', t0)

        # Before flip callback
        if on_before_flip is not None:
            await on_before_flip()

        # Elbow flip motion: move to seg2[0] from current config
        flip_target = seg2[0]
        flip_point = JointTrajectoryPoint()
        flip_point.positions = flip_target
        flip_point.time_from_start = self._make_duration(self._flip_duration)
        ok, msg = await self._send_scara_trajectory([flip_point])
        if not ok:
            return self._build_result(False, f'Elbow flip failed: {msg}', t0)

        # After flip callback
        if on_after_flip is not None:
            await on_after_flip()

        # Execute segment 2
        pts2 = []
        for i, wp in enumerate(seg2):
            pt = JointTrajectoryPoint()
            pt.positions = wp
            pt.time_from_start = self._make_duration(time_per_step * (i + 1))
            pts2.append(pt)

        ok, msg = await self._send_scara_trajectory(pts2)
        return self._build_result(ok, msg, t0)

    # ------------------------------------------------------------------
    # Motion: home
    # ------------------------------------------------------------------

    async def move_home(self, velocity: float = 0.5) -> ScaraResult:
        """Move to configured home position. Z first if configured."""
        t0 = time.time()

        if self._z_enabled:
            home_z = self._home.get('z', 0.0)
            ok, msg = await self._send_z_trajectory(home_z, velocity)
            if not ok:
                return self._build_result(False, f'Z home failed: {msg}', t0)

        return await self.move_joints(
            shoulder=self._home.get('shoulder', 0.0),
            elbow=self._home.get('elbow', 0.0),
            wrist=self._home.get('wrist', 0.0),
            velocity=velocity,
        )

    # ------------------------------------------------------------------
    # Tool control
    # ------------------------------------------------------------------

    async def trigger_tool(self, activate: bool = True) -> ScaraResult:
        """Activate / deactivate end-effector tool."""
        t0 = time.time()

        if self._tool_cfg.get('type', 'none') == 'none':
            return self._build_result(False, 'Tool not configured', t0)

        if self._tool_cfg['type'] == 'service':
            client = (self._tool_activate_client if activate
                      else self._tool_deactivate_client)
            if client is None:
                return self._build_result(False, 'Tool service client not created', t0)

            timeout = self._tool_cfg.get('settle_time', 5.0)
            if not client.wait_for_service(timeout_sec=timeout):
                return self._build_result(False, 'Tool service not available', t0)

            resp = await client.call_async(Trigger.Request())
            if not resp.success:
                return self._build_result(False, f'Tool trigger failed: {resp.message}', t0)

            settle = self._tool_cfg.get('settle_time', 0.5)
            if settle > 0:
                await self._async_sleep(settle)

            return self._build_result(True, 'Tool triggered', t0)

        return self._build_result(False, f'Unknown tool type: {self._tool_cfg["type"]}', t0)

    async def pick_at(
        self, x: float, y: float, z: float = None, velocity: float = 0.5,
    ) -> ScaraResult:
        """Move to point, activate tool."""
        result = await self.move_to_point(x=x, y=y, z=z, velocity=velocity)
        if not result.success:
            return result
        return await self.trigger_tool(activate=True)

    async def place_at(
        self, x: float, y: float, z: float = None, velocity: float = 0.5,
    ) -> ScaraResult:
        """Move to point, deactivate tool."""
        result = await self.move_to_point(x=x, y=y, z=z, velocity=velocity)
        if not result.success:
            return result
        return await self.trigger_tool(activate=False)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    async def _async_sleep(self, seconds: float):
        """Non-blocking sleep using the node's clock."""
        import asyncio
        await asyncio.sleep(seconds)
