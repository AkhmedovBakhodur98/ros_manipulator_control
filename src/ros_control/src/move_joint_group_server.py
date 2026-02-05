#!/usr/bin/env python3
"""
MoveJointGroup Action Server

Provides unified interface for moving multiple joints simultaneously
across different controllers (manipulator, SCARA, gripper, etc.)
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, ActionClient
from rclpy.qos import QoSProfile, ReliabilityPolicy
import yaml
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from ament_index_python.packages import get_package_share_directory

# Action messages
from ros_control.action import MoveJointGroup

# ROS2 messages
from sensor_msgs.msg import JointState
from control_msgs.action import FollowJointTrajectory
from std_msgs.msg import Float64MultiArray
from controller_manager_msgs.srv import ListControllers


class MoveJointGroupServer(Node):
    """Action server for moving multiple joints simultaneously"""

    def __init__(self):
        super().__init__('move_joint_group_server')
        
        # Load configuration
        self.config = self._load_config()
        self.get_logger().info('Configuration loaded')
        
        # Read controller joints from ROS2 parameters (passed by launch file)
        # ROS2 doesn't support nested dicts, so we pass as JSON string
        # Parameter: controller_joints_json = '{"controller_name": ["joint1", "joint2"], ...}'
        self.controller_joints_param = {}
        try:
            self.declare_parameter('controller_joints_json', '')
            json_str = self.get_parameter('controller_joints_json').value
            if json_str:
                self.controller_joints_param = json.loads(json_str)
                self.get_logger().info(f'Parsed controller_joints from JSON parameter')
        except json.JSONDecodeError as e:
            self.get_logger().error(f'Failed to parse controller_joints_json: {e}')
        except Exception as e:
            self.get_logger().debug(f'controller_joints_json parameter not set: {e}')
        
        if self.controller_joints_param:
            self.get_logger().info(
                f'Loaded controller joints from parameters: {list(self.controller_joints_param.keys())}'
            )
        else:
            self.get_logger().info('No controller_joints parameter provided, will use discovery/fallback')
        
        # State
        self.joint_to_controller_map: Dict[str, Tuple[str, str, str]] = {}
        # Format: joint_name -> (controller_name, controller_type, interface)
        self.controller_info: Dict[str, Dict] = {}
        self.last_discovery_time = 0.0
        self.current_joint_states: Dict[str, float] = {}
        
        # Active goal tracking (for fail-all strategy)
        self.active_goal_handles: Dict[str, object] = {}  # controller_name -> goal_handle
        self.active_initial_positions: Dict[str, float] = {}  # joint_name -> initial_position
        
        # ROS2 interfaces
        self.action_server = ActionServer(
            self,
            MoveJointGroup,
            'move_joint_group',
            self.execute_goal_callback
        )
        
        # Joint state subscriber
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            depth=10
        )
        self.joint_state_sub = self.create_subscription(
            JointState,
            '/joint_states',
            self.joint_state_callback,
            qos_profile
        )
        
        # Controller manager clients
        self.list_controllers_client = self.create_client(
            ListControllers,
            '/controller_manager/list_controllers'
        )
        
        # Action clients for trajectory controllers (created on demand)
        self.trajectory_action_clients: Dict[str, ActionClient] = {}
        
        # Publishers for topic-based controllers (created on demand)
        self.topic_publishers: Dict[str, rclpy.publisher.Publisher] = {}
        
        # Initialize joint map from parameters (fallback if discovery fails)
        self._init_from_parameters()

        # Initial discovery (may fail if controllers not yet active)
        self.discover_controllers()

        # Timer for periodic discovery refresh
        self.discovery_timer = self.create_timer(
            self.config['discovery']['refresh_interval'],
            self.discover_controllers
        )

        self.get_logger().info('MoveJointGroup action server started')

    def _init_from_parameters(self):
        """Initialize joint-to-controller map from controller_joints parameter.

        This provides a fallback when discovery fails (e.g., controllers not yet active).
        The controller type is inferred from naming convention or defaults to trajectory.
        """
        if not self.controller_joints_param:
            return

        for controller_name, joints in self.controller_joints_param.items():
            if not joints:
                continue

            # Infer controller type from name (fallback)
            if 'gripper' in controller_name.lower():
                controller_type = 'forward_command_controller/ForwardCommandController'
                interface_type = 'topic'
                interface_name = f'/{controller_name}/commands'
            else:
                controller_type = 'joint_trajectory_controller/JointTrajectoryController'
                interface_type = 'action'
                interface_name = f'/{controller_name}/follow_joint_trajectory'

            # Store controller info
            self.controller_info[controller_name] = {
                'type': controller_type,
                'interface_type': interface_type,
                'interface_name': interface_name,
                'joints': joints
            }

            # Map joints to controller
            for joint in joints:
                self.joint_to_controller_map[joint] = (
                    controller_name,
                    controller_type,
                    interface_name
                )

        if self.joint_to_controller_map:
            self.get_logger().info(
                f'Initialized from parameters: {len(self.controller_info)} controllers, '
                f'{len(self.joint_to_controller_map)} joints'
            )

    def _load_config(self) -> Dict:
        """Load configuration from YAML file

        Handles multiple YAML formats:
        1. Direct config: {position_tolerance: 0.01, ...}
        2. ROS2 format: {ros__parameters: {position_tolerance: 0.01, ...}}
        3. Node-prefixed: {move_joint_group_server: {ros__parameters: {...}}}
        """
        # Use ament_index to find package share directory (works when installed)
        try:
            pkg_share = get_package_share_directory('ros_control')
            config_path = Path(pkg_share) / 'config' / 'move_joint_group_config.yaml'
        except Exception:
            # Fallback for development (running from source)
            config_path = Path(__file__).parent.parent / 'config' / 'move_joint_group_config.yaml'

        if not config_path.exists():
            self.get_logger().warn(f'Config file not found at {config_path}, using defaults')
            return self._default_config()

        with open(config_path, 'r') as f:
            yaml_data = yaml.safe_load(f)

        if not yaml_data:
            return self._default_config()

        # Extract config from various YAML structures
        config = None

        # Check for node-prefixed format: {move_joint_group_server: {ros__parameters: {...}}}
        if 'move_joint_group_server' in yaml_data:
            node_config = yaml_data['move_joint_group_server']
            if isinstance(node_config, dict) and 'ros__parameters' in node_config:
                config = node_config['ros__parameters']
            elif isinstance(node_config, dict):
                config = node_config
        # Check for direct ros__parameters format: {ros__parameters: {...}}
        elif 'ros__parameters' in yaml_data:
            config = yaml_data['ros__parameters']
        # Direct config format: {position_tolerance: 0.01, ...}
        else:
            config = yaml_data

        if not config:
            config = {}

        # Deep merge with defaults
        default = self._default_config()
        merged = self._deep_merge(default, config)
        return merged

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries, with override taking precedence"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _default_config(self) -> Dict:
        """Return default configuration"""
        return {
            'position_tolerance': 0.01,
            'execution': {
                'strategy': 'simultaneous',
                'max_coordination_time': 10.0,
                'timeout': 30.0
            },
            'discovery': {
                'refresh_interval': 5.0,
                'query_timeout': 2.0
            },
            'feedback': {
                'publish_rate': 10.0
            }
        }

    def joint_state_callback(self, msg: JointState):
        """Update current joint states"""
        for i, joint_name in enumerate(msg.name):
            if i < len(msg.position):
                self.current_joint_states[joint_name] = msg.position[i]

    def discover_controllers(self):
        """Discover available controllers and their joints"""
        try:
            # Wait for service
            if not self.list_controllers_client.wait_for_service(timeout_sec=1.0):
                self.get_logger().warn('Controller manager service not available')
                return
            
            # List all controllers
            request = ListControllers.Request()
            future = self.list_controllers_client.call_async(request)
            rclpy.spin_until_future_complete(self, future, timeout_sec=self.config['discovery']['query_timeout'])
            
            if not future.done():
                self.get_logger().warn('Timeout querying controllers')
                return
            
            response = future.result()
            if not response:
                self.get_logger().warn('Failed to get controller list')
                return
            
            # Clear old mapping
            self.joint_to_controller_map.clear()
            self.controller_info.clear()
            
            # Query each controller
            for controller in response.controller:
                if controller.state != 'active':
                    continue  # Skip inactive controllers
                
                controller_name = controller.name
                controller_type = controller.type
                
                # Skip joint_state_broadcaster
                if 'joint_state_broadcaster' in controller_name:
                    continue
                
                # Debug: log controller info
                self.get_logger().info(
                    f'Processing controller: {controller_name}, '
                    f'claimed_interfaces: {getattr(controller, "claimed_interfaces", "N/A")}'
                )
                
                # Get controller parameters to find joints
                joints = self._get_controller_joints(controller_name)
                
                # Fallback: extract joints from claimed_interfaces if parameter not available
                if not joints:
                    # Extract joint names from claimed interfaces (format: "joint_name/position")
                    joints = []
                    try:
                        # Access claimed_interfaces directly from controller state
                        claimed_interfaces = getattr(controller, 'claimed_interfaces', [])
                        if claimed_interfaces:
                            for interface in claimed_interfaces:
                                if '/position' in interface:
                                    joint_name = interface.split('/')[0]
                                    if joint_name not in joints:
                                        joints.append(joint_name)
                            if joints:
                                self.get_logger().info(
                                    f'Extracted joints from interfaces for {controller_name}: {joints}'
                                )
                            else:
                                self.get_logger().warn(
                                    f'No position interfaces found in claimed_interfaces for {controller_name}: {claimed_interfaces}'
                                )
                        else:
                            self.get_logger().warn(
                                f'Controller {controller_name} has empty claimed_interfaces. '
                                f'Controller type: {controller_type}, '
                                f'State: {controller.state}'
                            )
                    except Exception as e:
                        self.get_logger().error(
                            f'Error extracting joints from interfaces for {controller_name}: {e}'
                        )
                        import traceback
                        self.get_logger().error(traceback.format_exc())
                
                if not joints:
                    self.get_logger().warn(
                        f'No joints found for controller {controller_name}. '
                        f'Type: {type(controller)}, '
                        f'Has claimed_interfaces: {hasattr(controller, "claimed_interfaces")}'
                    )
                    continue
                
                # Determine interface type
                if 'JointTrajectoryController' in controller_type:
                    interface_type = 'action'
                    interface_name = f'/{controller_name}/follow_joint_trajectory'
                elif 'ForwardCommandController' in controller_type:
                    interface_type = 'topic'
                    interface_name = f'/{controller_name}/commands'
                else:
                    self.get_logger().warn(f'Unsupported controller type: {controller_type}')
                    continue
                
                # Store controller info
                self.controller_info[controller_name] = {
                    'type': controller_type,
                    'interface_type': interface_type,
                    'interface_name': interface_name,
                    'joints': joints
                }
                
                # Map joints to controller
                for joint in joints:
                    self.joint_to_controller_map[joint] = (
                        controller_name,
                        controller_type,
                        interface_name
                    )
                
                self.get_logger().info(
                    f'Discovered controller: {controller_name} ({controller_type}) '
                    f'with joints: {joints}'
                )
            
            self.last_discovery_time = time.time()
            self.get_logger().info(
                f'Controller discovery complete. Found {len(self.controller_info)} controllers, '
                f'{len(self.joint_to_controller_map)} joints'
            )
            
        except Exception as e:
            self.get_logger().error(f'Error during controller discovery: {e}')

    def _get_controller_joints(self, controller_name: str) -> List[str]:
        """Get joint list for a controller from ROS2 parameters (passed by launch file)
        
        The launch file should pass controller_joints parameter with structure:
        {
            'controller_name': ['joint1', 'joint2', ...],
            ...
        }
        """
        # Check ROS2 parameters (passed by launch file)
        if not self.controller_joints_param:
            self.get_logger().error(
                f'No controller_joints parameter provided. '
                f'Please start this node via launch file that passes controller configuration.'
            )
            return []
        
        if controller_name not in self.controller_joints_param:
            self.get_logger().warn(
                f'Controller {controller_name} not found in controller_joints parameter. '
                f'Available controllers: {list(self.controller_joints_param.keys())}'
            )
            return []
        
        joints = self.controller_joints_param[controller_name]
        
        # Ensure it's a list
        if isinstance(joints, list):
            self.get_logger().debug(
                f'Found joints for {controller_name} from parameters: {joints}'
            )
            return list(joints)
        elif isinstance(joints, str):
            # Single joint as string
            return [joints]
        else:
            self.get_logger().error(
                f'Invalid joints format for {controller_name}: expected list or string, got {type(joints)}'
            )
            return []

    def validate_goal(self, goal: MoveJointGroup.Goal) -> Optional[str]:
        """Validate goal request. Returns error message if invalid, None if valid"""
        # Check array lengths match
        if len(goal.joint_names) != len(goal.target_positions):
            return f"joint_names ({len(goal.joint_names)}) and target_positions ({len(goal.target_positions)}) length mismatch"
        
        if len(goal.joint_names) != len(goal.max_velocity):
            return f"joint_names ({len(goal.joint_names)}) and max_velocity ({len(goal.max_velocity)}) length mismatch"
        
        # Check joints exist
        missing_joints = []
        for joint in goal.joint_names:
            if joint not in self.joint_to_controller_map:
                missing_joints.append(joint)
        
        if missing_joints:
            return f"Joints not found: {missing_joints}"
        
        return None

    def group_joints_by_controller(self, joint_names: List[str], target_positions: List[float], 
                                   max_velocities: List[float]) -> Dict[str, Dict]:
        """Group joints by their controllers"""
        controller_groups = {}
        
        for i, joint in enumerate(joint_names):
            controller_name, controller_type, interface_name = self.joint_to_controller_map[joint]
            controller_info = self.controller_info[controller_name]
            
            if controller_name not in controller_groups:
                controller_groups[controller_name] = {
                    'type': controller_info['interface_type'],
                    'interface_name': interface_name,
                    'joints': [],
                    'targets': [],
                    'velocities': []
                }
            
            controller_groups[controller_name]['joints'].append(joint)
            controller_groups[controller_name]['targets'].append(target_positions[i])
            controller_groups[controller_name]['velocities'].append(max_velocities[i])
        
        return controller_groups

    def execute_goal_callback(self, goal_handle):
        """Execute action goal"""
        goal = goal_handle.request
        start_time = time.time()
        
        self.get_logger().info(
            f'Received goal: {len(goal.joint_names)} joints, '
            f'positions: {goal.target_positions}'
        )
        
        # Validate goal
        error_msg = self.validate_goal(goal)
        if error_msg:
            self.get_logger().error(f'Goal validation failed: {error_msg}')
            result = MoveJointGroup.Result()
            result.success = False
            result.message = f"Validation error: {error_msg}"
            result.final_position = []
            result.position_error = float('inf')
            result.execution_time = time.time() - start_time
            goal_handle.abort()
            return result
        
        # Refresh discovery if needed
        if time.time() - self.last_discovery_time > self.config['discovery']['refresh_interval']:
            self.discover_controllers()
        
        # Track initial positions for progress calculation
        for joint in goal.joint_names:
            self.active_initial_positions[joint] = self.current_joint_states.get(joint, 0.0)
        
        # Group joints by controller
        controller_groups = self.group_joints_by_controller(
            list(goal.joint_names),
            list(goal.target_positions),
            list(goal.max_velocity)
        )
        
        # Clear active goal handles for this execution
        self.active_goal_handles.clear()
        
        # Execute commands
        try:
            # Execute all controllers in parallel
            futures = []
            publishers = []
            
            # Calculate timing for coordinated execution if needed
            execution_strategy = self.config['execution']['strategy']
            if execution_strategy == 'coordinated':
                # Calculate required time for all joints to arrive simultaneously
                max_time = self._calculate_coordinated_time(
                    goal.joint_names, goal.target_positions, goal.max_velocity
                )
                self.get_logger().info(f'Coordinated execution: all joints will arrive in {max_time:.2f}s')
            else:
                max_time = None  # Will be calculated per-joint for simultaneous
            
            for controller_name, group_info in controller_groups.items():
                if group_info['type'] == 'action':
                    # Action-based controller
                    future, goal_handle_wrapper = self._execute_trajectory_action(
                        controller_name, group_info, goal_handle, max_time
                    )
                    if future:
                        futures.append((controller_name, future))
                        if goal_handle_wrapper:
                            self.active_goal_handles[controller_name] = goal_handle_wrapper
                elif group_info['type'] == 'topic':
                    # Topic-based controller
                    publisher = self._publish_topic_command(controller_name, group_info)
                    if publisher:
                        publishers.append((controller_name, publisher))
            
            # Note: For action-based controllers, we send goals asynchronously
            # and monitor joint states to determine completion
            # Goal handles are already stored in self.active_goal_handles
            action_goals_sent = {}
            for controller_name, future in futures:
                try:
                    # Wait briefly to ensure goal was sent
                    rclpy.spin_until_future_complete(
                        self, future, timeout_sec=2.0
                    )
                    if future.done():
                        goal_handle_result = future.result()
                        if goal_handle_result:
                            action_goals_sent[controller_name] = True
                            self.get_logger().info(f'Goal sent to {controller_name}')
                        else:
                            self.get_logger().warn(f'Failed to send goal to {controller_name}')
                            # Remove from active handles if failed
                            if controller_name in self.active_goal_handles:
                                del self.active_goal_handles[controller_name]
                    else:
                        self.get_logger().warn(f'Timeout sending goal to {controller_name}')
                except Exception as e:
                    self.get_logger().error(f'Error sending goal to {controller_name}: {e}')
                    # Remove from active handles on error
                    if controller_name in self.active_goal_handles:
                        del self.active_goal_handles[controller_name]
            
            # Monitor progress until all joints reach target
            feedback_timer = None
            if self.config['feedback']['publish_rate'] > 0:
                feedback_timer = self.create_timer(
                    1.0 / self.config['feedback']['publish_rate'],
                    lambda: self._publish_feedback(goal_handle, goal)
                )
            
            # Wait for joints to reach target
            timeout = self.config['execution']['timeout']
            check_interval = 0.1  # seconds
            start_wait = time.time()

            while (time.time() - start_wait) < timeout:
                # Process callbacks to update joint states
                rclpy.spin_once(self, timeout_sec=check_interval)

                if goal_handle.is_cancel_requested:
                    # Fail-all: cancel all active goals
                    self._cancel_all_active_goals()
                    if feedback_timer:
                        feedback_timer.cancel()
                    result = self._create_result(goal, start_time, False, "Cancelled by user")
                    goal_handle.canceled()
                    return result

                # Check if all joints are within tolerance
                all_reached, max_error, failed_joints = self._check_joints_reached(
                    goal.joint_names, goal.target_positions
                )

                if all_reached:
                    if feedback_timer:
                        feedback_timer.cancel()
                    result = self._create_result(goal, start_time, True, "Success")
                    goal_handle.succeed()
                    # Clear active handles
                    self.active_goal_handles.clear()
                    self.active_initial_positions.clear()
                    return result
            
            # Timeout - Fail-all: cancel all active goals
            self._cancel_all_active_goals()
            if feedback_timer:
                feedback_timer.cancel()
            
            # Get which joints failed
            _, max_error, failed_joints = self._check_joints_reached(
                goal.joint_names, goal.target_positions
            )
            error_msg = f"Timeout after {timeout}s"
            if failed_joints:
                error_msg += f". Failed joints: {failed_joints}"
            
            result = self._create_result(goal, start_time, False, error_msg)
            goal_handle.abort()
            # Clear active handles
            self.active_goal_handles.clear()
            self.active_initial_positions.clear()
            return result
            
        except Exception as e:
            self.get_logger().error(f'Error during execution: {e}', exc_info=True)
            # Fail-all: cancel all active goals on error
            self._cancel_all_active_goals()
            result = self._create_result(goal, start_time, False, f"Execution error: {e}")
            goal_handle.abort()
            # Clear active handles
            self.active_goal_handles.clear()
            self.active_initial_positions.clear()
            return result

    def _calculate_coordinated_time(self, joint_names: List[str], target_positions: List[float],
                                   max_velocities: List[float]) -> float:
        """Calculate time needed for all joints to arrive simultaneously (coordinated strategy)"""
        max_time = 0.0
        
        for joint, target, max_vel in zip(joint_names, target_positions, max_velocities):
            initial = self.active_initial_positions.get(joint, self.current_joint_states.get(joint, 0.0))
            distance = abs(target - initial)
            
            if max_vel > 0.0:
                # Use specified velocity
                time_needed = distance / max_vel
            else:
                # Use default velocity (estimate based on joint type)
                # For now, use a conservative estimate
                # In practice, could query joint limits
                default_vel = 0.5  # m/s or rad/s default
                time_needed = distance / default_vel if distance > 0 else 0.0
            
            max_time = max(max_time, time_needed)
        
        # Add small buffer
        calculated_time = max_time + 0.5
        
        # Apply maximum coordination time limit from config
        max_coordination_time = self.config['execution']['max_coordination_time']
        return min(calculated_time, max_coordination_time)

    def _cancel_all_active_goals(self):
        """Cancel all active action goals (fail-all strategy)"""
        for controller_name, goal_handle_wrapper in self.active_goal_handles.items():
            try:
                # goal_handle_wrapper is a ClientGoalHandle from send_goal_async
                if goal_handle_wrapper is not None:
                    # Request cancellation
                    cancel_future = goal_handle_wrapper.cancel_goal_async()
                    # Don't wait for completion, just send cancellation
                    self.get_logger().info(f'Cancelled goal for {controller_name}')
            except Exception as e:
                self.get_logger().warn(f'Error cancelling goal for {controller_name}: {e}')

    def _execute_trajectory_action(self, controller_name: str, group_info: Dict, 
                                   goal_handle, coordinated_time: Optional[float] = None) -> Tuple[Optional[rclpy.executors.Future], Optional[object]]:
        """Execute trajectory action for a controller"""
        try:
            # Get or create action client
            if controller_name not in self.trajectory_action_clients:
                self.trajectory_action_clients[controller_name] = ActionClient(
                    self,
                    FollowJointTrajectory,
                    group_info['interface_name']
                )
            
            client = self.trajectory_action_clients[controller_name]
            
            # Wait for action server
            if not client.wait_for_server(timeout_sec=2.0):
                self.get_logger().error(f'Action server {group_info["interface_name"]} not available')
                return None, None
            
            # Create goal - must include ALL controller joints, not just requested ones
            # JointTrajectoryController requires all joints in every trajectory
            action_goal = FollowJointTrajectory.Goal()

            # Get all joints for this controller
            all_controller_joints = self.controller_info[controller_name]['joints']

            # Build joint name to target/velocity mapping from user request
            requested_joints = {j: (t, v) for j, t, v in zip(
                group_info['joints'], group_info['targets'], group_info['velocities']
            )}

            # Build complete trajectory with all controller joints
            # JointTrajectoryController requires ALL joints in every trajectory,
            # even if only some are moving. Use current position for unspecified joints.
            full_joints = []
            full_targets = []
            full_velocities = []
            for joint in all_controller_joints:
                full_joints.append(joint)
                if joint in requested_joints:
                    target, vel = requested_joints[joint]
                    full_targets.append(target)
                    full_velocities.append(vel)
                else:
                    # Use current position for unspecified joints (no movement)
                    current = self.current_joint_states.get(joint, 0.0)
                    full_targets.append(current)
                    full_velocities.append(0.0)

            action_goal.trajectory.joint_names = full_joints

            # Create trajectory point
            from trajectory_msgs.msg import JointTrajectoryPoint
            point = JointTrajectoryPoint()
            point.positions = full_targets

            # Use max_velocity for time calculation only
            # Do NOT set point.velocities - for single-point trajectory,
            # the last point velocity must be zero (robot must stop)
            velocities = full_velocities

            # Calculate time from start
            if coordinated_time is not None:
                # Use coordinated time for all joints
                max_time = coordinated_time
            else:
                # Calculate time based on max velocity per joint (simultaneous strategy)
                max_time = 5.0  # Default 5 seconds
                if any(v > 0.0 for v in velocities):
                    # Calculate time based on distance and velocity
                    current_positions = [self.current_joint_states.get(j, 0.0) for j in full_joints]
                    times = []
                    for i, (current, target, vel) in enumerate(zip(current_positions, full_targets, velocities)):
                        if vel > 0.0:
                            distance = abs(target - current)
                            t = distance / vel
                            times.append(t)
                    if times:
                        max_time = max(times) + 0.5  # Add small buffer
            
            from builtin_interfaces.msg import Duration
            point.time_from_start = Duration(sec=int(max_time), nanosec=int((max_time % 1) * 1e9))
            
            action_goal.trajectory.points = [point]
            
            # Send goal
            send_goal_future = client.send_goal_async(action_goal)
            self.get_logger().info(f'Sending trajectory goal to {controller_name} (time: {max_time:.2f}s)')
            
            # Wait for goal to be accepted and get goal handle
            goal_handle_wrapper = None
            try:
                rclpy.spin_until_future_complete(self, send_goal_future, timeout_sec=2.0)
                if send_goal_future.done():
                    goal_handle_wrapper = send_goal_future.result()
            except Exception as e:
                self.get_logger().warn(f'Error getting goal handle for {controller_name}: {e}')
            
            # Return future and goal handle for cancellation
            return send_goal_future, goal_handle_wrapper
            
        except Exception as e:
            self.get_logger().error(f'Error executing trajectory action: {e}')
            return None, None

    def _publish_topic_command(self, controller_name: str, group_info: Dict) -> Optional[rclpy.publisher.Publisher]:
        """Publish command to topic-based controller"""
        try:
            # Get or create publisher
            if controller_name not in self.topic_publishers:
                self.topic_publishers[controller_name] = self.create_publisher(
                    Float64MultiArray,
                    group_info['interface_name'],
                    10
                )
            
            publisher = self.topic_publishers[controller_name]
            
            # Create message
            msg = Float64MultiArray()
            # Note: For ForwardCommandController, we need to send in controller's joint order
            # For now, assume order matches our group_info order
            msg.data = group_info['targets']
            
            # Publish
            publisher.publish(msg)
            self.get_logger().info(f'Published command to {controller_name}')
            return publisher
            
        except Exception as e:
            self.get_logger().error(f'Error publishing topic command: {e}')
            return None

    def _check_joints_reached(self, joint_names: List[str], target_positions: List[float]) -> Tuple[bool, float, List[str]]:
        """Check if all joints are within tolerance of target
        
        Returns:
            (all_reached, max_error, failed_joints)
        """
        max_error = 0.0
        all_reached = True
        failed_joints = []
        
        for joint, target in zip(joint_names, target_positions):
            current = self.current_joint_states.get(joint, None)
            if current is None:
                all_reached = False
                failed_joints.append(joint)
                continue
            
            error = abs(current - target)
            max_error = max(max_error, error)
            
            if error > self.config['position_tolerance']:
                all_reached = False
                failed_joints.append(joint)
        
        return all_reached, max_error, failed_joints

    def _publish_feedback(self, goal_handle, goal: MoveJointGroup.Goal):
        """Publish feedback"""
        feedback = MoveJointGroup.Feedback()
        feedback.joint_names = list(goal.joint_names)
        feedback.target_positions = list(goal.target_positions)
        
        # Get current positions
        current_positions = []
        for joint in goal.joint_names:
            current_positions.append(self.current_joint_states.get(joint, 0.0))
        feedback.current_positions = current_positions
        
        # Calculate progress using tracked initial positions
        initial_errors = []
        current_errors = []
        
        for i, joint in enumerate(goal.joint_names):
            # Use tracked initial position, fallback to current if not tracked
            initial = self.active_initial_positions.get(
                joint, 
                self.current_joint_states.get(joint, goal.target_positions[i])
            )
            current = self.current_joint_states.get(joint, goal.target_positions[i])
            target = goal.target_positions[i]
            
            initial_error = abs(initial - target)
            current_error = abs(current - target)
            
            initial_errors.append(initial_error)
            current_errors.append(current_error)
        
        if sum(initial_errors) > 0:
            progress = max(0.0, min(100.0, (1.0 - sum(current_errors) / sum(initial_errors)) * 100.0))
        else:
            progress = 100.0
        
        feedback.progress_percentage = float(progress)
        
        goal_handle.publish_feedback(feedback)

    def _create_result(self, goal: MoveJointGroup.Goal, start_time: float, 
                      success: bool, message: str) -> MoveJointGroup.Result:
        """Create result message"""
        result = MoveJointGroup.Result()
        result.success = success
        result.message = message
        result.execution_time = time.time() - start_time
        
        # Get final positions
        final_positions = []
        max_error = 0.0
        
        for i, joint in enumerate(goal.joint_names):
            final = self.current_joint_states.get(joint, goal.target_positions[i])
            final_positions.append(final)
            error = abs(final - goal.target_positions[i])
            max_error = max(max_error, error)
        
        result.final_position = final_positions
        result.position_error = max_error
        
        return result


def main(args=None):
    rclpy.init(args=args)
    
    node = MoveJointGroupServer()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
