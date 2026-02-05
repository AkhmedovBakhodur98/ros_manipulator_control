# move_joint_group_server.py Documentation

## Overview

The `move_joint_group_server.py` file implements the `MoveJointGroupServer` class, which provides a unified ROS2 action server for coordinating movement of multiple joints across different controllers. This server abstracts the complexity of managing multiple controller types (action-based and topic-based) and provides a single interface for coordinated robot movement.

## File Location

```
src/ros_control/src/move_joint_group_server.py
```

## Purpose

This implementation:
- Provides a high-level action server (`/move_joint_group`) for coordinated joint movement
- Automatically discovers available controllers and their joints
- Supports both action-based (`JointTrajectoryController`) and topic-based (`ForwardCommandController`) controllers
- Coordinates movement across multiple controllers simultaneously
- Monitors joint states and provides progress feedback
- Implements fail-all strategy (cancels all goals on failure)

---

## Class: MoveJointGroupServer

### Inheritance

```python
class MoveJointGroupServer(Node)
```

Inherits from `rclpy.node.Node`, providing ROS2 node functionality.

---

## Initialization

### `__init__(self)`

Initializes the action server node and sets up all ROS2 interfaces.

**Process:**
1. Calls `super().__init__('move_joint_group_server')` to initialize ROS2 node
2. Loads configuration from YAML file (using `ament_index_python` to find package share directory)
3. Reads `controller_joints_json` parameter (JSON string passed by launch file) and parses it
4. Initializes state variables
5. Creates ROS2 interfaces (action server, subscribers, service clients)
6. Initializes joint map from parameters via `_init_from_parameters()` (fallback for early goals)
7. Performs initial controller discovery
8. Sets up periodic discovery refresh timer

**State Variables Initialized:**

| Variable | Type | Description |
|----------|------|-------------|
| `config` | `Dict` | Configuration loaded from YAML file |
| `controller_joints_param` | `Dict[str, List[str]]` | Controller-to-joints mapping parsed from `controller_joints_json` parameter |
| `joint_to_controller_map` | `Dict[str, Tuple[str, str, str]]` | Maps joint name to (controller_name, controller_type, interface_name) |
| `controller_info` | `Dict[str, Dict]` | Controller information (type, interface_type, interface_name, joints) |
| `last_discovery_time` | `float` | Timestamp of last controller discovery |
| `current_joint_states` | `Dict[str, float]` | Current joint positions from `/joint_states` |
| `active_goal_handles` | `Dict[str, object]` | Active goal handles for cancellation (fail-all strategy) |
| `active_initial_positions` | `Dict[str, float]` | Initial positions when goal started (for progress calculation) |
| `trajectory_action_clients` | `Dict[str, ActionClient]` | Action clients for trajectory controllers (created on demand) |
| `topic_publishers` | `Dict[str, Publisher]` | Publishers for topic-based controllers (created on demand) |

**ROS2 Interfaces Created:**

| Interface | Type | Name | Purpose |
|-----------|------|------|---------|
| Action Server | `ActionServer` | `/move_joint_group` | Receives action goals |
| Subscription | `Subscription` | `/joint_states` | Monitors current joint positions |
| Service Client | `ServiceClient` | `/controller_manager/list_controllers` | Discovers controllers |
| Timer | `Timer` | - | Periodic controller discovery refresh |

**Dynamic Interfaces (Created On-Demand):**

- Action clients for trajectory controllers: `/{controller_name}/follow_joint_trajectory`
- Publishers for topic-based controllers: `/{controller_name}/commands`

---

## Configuration Methods

### `_load_config(self) -> Dict`

Loads configuration from YAML file and merges with defaults.

**Process:**
1. Constructs path: `{package_dir}/config/move_joint_group_config.yaml`
2. Checks if file exists
3. If exists: loads YAML and extracts config from various formats
4. Deep merges with defaults (nested dictionaries are merged recursively)
5. If not exists: returns default configuration with warning

**Supported YAML Formats:**

1. **Node-prefixed format** (recommended for ROS2):
```yaml
move_joint_group_server:
  ros__parameters:
    position_tolerance: 0.01
    execution:
      timeout: 30.0
```

2. **Direct ros__parameters format:**
```yaml
ros__parameters:
  position_tolerance: 0.01
  execution:
    timeout: 30.0
```

3. **Direct config format:**
```yaml
position_tolerance: 0.01
execution:
  timeout: 30.0
```

**Returns:** `Dict` - Merged configuration dictionary

**Default Configuration:**
```python
{
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
```

### `_default_config(self) -> Dict`

Returns default configuration dictionary.

**Returns:** `Dict` - Default configuration values

### `_init_from_parameters(self)`

Initializes joint-to-controller map from `controller_joints_json` parameter as a fallback when controller discovery fails (e.g., controllers not yet active).

**Process:**
1. Checks if `controller_joints_param` is populated
2. For each controller in the parameter:
   - Infers controller type from name (e.g., 'gripper' → ForwardCommandController)
   - Defaults to JointTrajectoryController for other controllers
   - Stores controller info and maps joints to controller
3. Logs initialization results

**Controller Type Inference:**
- Controller name contains 'gripper' → `ForwardCommandController` (topic-based)
- All other controllers → `JointTrajectoryController` (action-based)

This method ensures the server can accept goals even before discovery completes.

### `_deep_merge(self, base: Dict, override: Dict) -> Dict`

Deep merges two dictionaries, with override values taking precedence.

**Parameters:**
- `base` (`Dict`): Base dictionary with default values
- `override` (`Dict`): Dictionary with values to override

**Returns:** `Dict` - Merged dictionary

**Process:**
1. Creates copy of base dictionary
2. For each key in override:
   - If both values are dicts: recursively merge
   - Otherwise: override value replaces base value
3. Returns merged result

---

## Joint State Management

### `joint_state_callback(self, msg: JointState)`

Callback for `/joint_states` topic subscription.

**Parameters:**
- `msg` (`sensor_msgs.msg.JointState`): Joint state message

**Process:**
1. Iterates through joint names in message
2. Updates `self.current_joint_states[joint_name] = position[i]`
3. Only updates if position data exists for joint

**QoS Profile:**
- Reliability: `BEST_EFFORT` (allows missing messages)
- Depth: 10 (queue size)

---

## Controller Discovery

### `discover_controllers(self)`

Discovers available controllers and maps joints to controllers.

**Process:**
1. Waits for `list_controllers` service (1 second timeout)
2. Calls service to get list of all controllers
3. Filters controllers:
   - Only active controllers
   - Skips `joint_state_broadcaster`
4. For each controller:
   - Gets joint list from ROS2 `controller_joints` parameter (passed by launch file)
   - Determines interface type (action or topic) based on controller type
   - Stores controller information
   - Maps joints to controller
5. Updates `last_discovery_time`
6. Logs discovery results

**Note:** Joint information is obtained from the `controller_joints` ROS2 parameter that must be passed by the launch file. This parameter contains a dictionary mapping controller names to their joint lists.

**Controller Interface Types:**

| Controller Type | Interface Type | Interface Name |
|----------------|----------------|---------------|
| `JointTrajectoryController` | `action` | `/{controller_name}/follow_joint_trajectory` |
| `ForwardCommandController` | `topic` | `/{controller_name}/commands` |

**Updates:**
- `self.joint_to_controller_map`: Joint → Controller mapping
- `self.controller_info`: Controller information dictionary

**Error Handling:**
- Service unavailable: Logs warning, returns early
- Timeout: Logs warning, returns early
- Exception: Logs error with exception details

### `_get_controller_joints(self, controller_name: str) -> List[str]`

Gets joint list for a controller from ROS2 parameters.

**Parameters:**
- `controller_name` (`str`): Name of the controller

**Returns:** `List[str]` - List of joint names, or empty list if not found

**Process:**
1. Checks if `controller_joints_param` is provided
2. Checks if controller exists in parameter dictionary
3. Extracts joints list
4. Validates format (list or single string)
5. Returns joint list

**Parameter Structure Expected:**
```python
{
    'controller_name': ['joint1', 'joint2', ...],
    ...
}
```

**Error Handling:**
- No parameter provided: Logs error, returns empty list
- Controller not found: Logs warning, returns empty list
- Invalid format: Logs error, returns empty list

---

## Goal Validation

### `validate_goal(self, goal: MoveJointGroup.Goal) -> Optional[str]`

Validates goal request before execution.

**Parameters:**
- `goal` (`MoveJointGroup.Goal`): Goal request to validate

**Returns:** 
- `None` if valid
- `str` error message if invalid

**Validation Checks:**
1. Array length matching:
   - `joint_names` length == `target_positions` length
   - `joint_names` length == `max_velocity` length
2. Joint existence:
   - All joints in `joint_names` must exist in `joint_to_controller_map`

**Error Messages:**
- `"joint_names ({len}) and target_positions ({len}) length mismatch"`
- `"joint_names ({len}) and max_velocity ({len}) length mismatch"`
- `"Joints not found: {missing_joints}"`

---

## Joint Grouping

### `group_joints_by_controller(self, joint_names: List[str], target_positions: List[float], max_velocities: List[float]) -> Dict[str, Dict]`

Groups joints by their controllers for coordinated execution.

**Parameters:**
- `joint_names` (`List[str]`): List of joint names
- `target_positions` (`List[float]`): Target positions for each joint
- `max_velocities` (`List[float]`): Max velocities for each joint

**Returns:** `Dict[str, Dict]` - Controller groups dictionary

**Return Structure:**
```python
{
    'controller_name': {
        'type': 'action' | 'topic',
        'interface_name': '/controller_name/...',
        'joints': ['joint1', 'joint2', ...],
        'targets': [pos1, pos2, ...],
        'velocities': [vel1, vel2, ...]
    },
    ...
}
```

**Process:**
1. Iterates through joints
2. Looks up controller for each joint
3. Groups joints by controller
4. Collects targets and velocities for each controller

---

## Goal Execution

### `execute_goal_callback(self, goal_handle)`

Main callback for executing action goals.

**Parameters:**
- `goal_handle`: Action goal handle from ROS2

**Process Flow:**

```
1. Extract goal from goal_handle
2. Validate goal → abort if invalid
3. Refresh discovery if needed
4. Track initial positions
5. Group joints by controller
6. Clear active goal handles
7. Execute commands:
   - Action controllers: Send trajectory goals
   - Topic controllers: Publish commands
8. Monitor progress:
   - Check joint positions periodically
   - Publish feedback
   - Check for cancellation
9. Complete:
   - Success: All joints within tolerance
   - Timeout: Maximum time exceeded
   - Cancellation: User cancelled
   - Error: Exception occurred
10. Cleanup: Cancel all active goals (fail-all strategy)
```

**Execution Strategies:**

1. **Simultaneous** (default):
   - All joints start moving at once
   - Each joint finishes independently
   - Time calculated per-joint based on velocity

2. **Coordinated**:
   - All joints start moving at once
   - All joints arrive at same time
   - Time calculated to synchronize arrival

**Monitoring:**
- Check interval: 0.1 seconds
- Checks if all joints within tolerance
- Publishes feedback at configured rate
- Handles cancellation requests

**Result States:**
- `SUCCEEDED`: All joints reached target within tolerance
- `ABORTED`: Timeout or error occurred
- `CANCELED`: User requested cancellation

**Fail-All Strategy:**
On any failure (timeout, error, cancellation), all active goals are cancelled to prevent partial movements.

---

## Execution Helpers

### `_calculate_coordinated_time(self, joint_names: List[str], target_positions: List[float], max_velocities: List[float]) -> float`

Calculates time needed for all joints to arrive simultaneously (coordinated strategy).

**Parameters:**
- `joint_names`: List of joint names
- `target_positions`: Target positions
- `max_velocities`: Max velocities

**Returns:** `float` - Time in seconds

**Process:**
1. For each joint:
   - Gets initial position
   - Calculates distance to target
   - Calculates time needed: `distance / velocity`
   - Uses default velocity (0.5) if max_velocity is 0.0
2. Finds maximum time needed
3. Adds 0.5 second buffer
4. Applies maximum coordination time limit from config

**Default Velocity:** 0.5 m/s or rad/s (if max_velocity is 0.0)

### `_cancel_all_active_goals(self)`

Cancels all active action goals (fail-all strategy).

**Process:**
1. Iterates through `active_goal_handles`
2. For each goal handle:
   - Calls `cancel_goal_async()`
   - Logs cancellation
3. Does not wait for completion (fire-and-forget)

**Error Handling:**
- Logs warning if cancellation fails for any controller

---

## Controller Execution

### `_execute_trajectory_action(self, controller_name: str, group_info: Dict, goal_handle, coordinated_time: Optional[float] = None) -> Tuple[Optional[rclpy.executors.Future], Optional[object]]`

Executes trajectory action for action-based controllers.

**Parameters:**
- `controller_name` (`str`): Name of the controller
- `group_info` (`Dict`): Controller group information (joints, targets, velocities)
- `goal_handle`: Action goal handle (not used, kept for compatibility)
- `coordinated_time` (`Optional[float]`): Coordinated time if using coordinated strategy

**Returns:** 
- `Tuple[Optional[Future], Optional[object]]` - (send_goal_future, goal_handle_wrapper)
- Returns `None` on error

**Process:**
1. Gets or creates action client for controller
2. Waits for action server (2 second timeout)
3. Creates `FollowJointTrajectory.Goal`:
   - **IMPORTANT:** Includes ALL joints for the controller, not just requested ones
   - For requested joints: uses target position and velocity from goal
   - For unspecified joints: uses current position (no movement), velocity 0.0
   - Does NOT set `point.velocities` (last trajectory point must have zero velocity)
   - Calculates time from start:
     - Coordinated: Uses `coordinated_time`
     - Simultaneous: Calculates per-joint based on distance/velocity, uses maximum
4. Sends goal asynchronously
5. Waits for goal acceptance (2 second timeout)
6. Returns future and goal handle

**Important:** `JointTrajectoryController` requires ALL controller joints in every trajectory. If you only send a subset of joints, the controller will reject the goal with "Joints on incoming trajectory don't match the controller joints" error.

**Time Calculation:**
- **Coordinated**: Uses provided `coordinated_time`
- **Simultaneous**: 
  - Default: 5.0 seconds
  - If velocities specified: `max(distance/velocity) + 0.5` buffer

**Error Handling:**
- Action server unavailable: Returns `None`
- Goal send error: Returns `None`
- Exception: Logs error, returns `None`

### `_publish_topic_command(self, controller_name: str, group_info: Dict) -> Optional[rclpy.publisher.Publisher]`

Publishes command to topic-based controllers.

**Parameters:**
- `controller_name` (`str`): Name of the controller
- `group_info` (`Dict`): Controller group information (joints, targets, velocities)

**Returns:** 
- `Optional[Publisher]` - Publisher object, or `None` on error

**Process:**
1. Gets or creates publisher for controller
2. Creates `Float64MultiArray` message
3. Sets `msg.data = group_info['targets']` (position commands)
4. Publishes message
5. Returns publisher

**Note:** Assumes joint order in `group_info['targets']` matches controller's joint order.

**Error Handling:**
- Exception: Logs error, returns `None`

---

## Progress Monitoring

### `_check_joints_reached(self, joint_names: List[str], target_positions: List[float]) -> Tuple[bool, float, List[str]]`

Checks if all joints are within tolerance of target.

**Parameters:**
- `joint_names`: List of joint names to check
- `target_positions`: Target positions for each joint

**Returns:** 
- `Tuple[bool, float, List[str]]` - (all_reached, max_error, failed_joints)

**Process:**
1. For each joint:
   - Gets current position from `current_joint_states`
   - Calculates error: `abs(current - target)`
   - Updates `max_error`
   - Checks if error > `position_tolerance`
2. Returns:
   - `all_reached`: True if all joints within tolerance
   - `max_error`: Maximum error across all joints
   - `failed_joints`: List of joints not within tolerance

**Error Handling:**
- Missing joint state: Treats as failed joint

### `_publish_feedback(self, goal_handle, goal: MoveJointGroup.Goal)`

Publishes progress feedback to action client.

**Parameters:**
- `goal_handle`: Action goal handle
- `goal`: Goal request

**Process:**
1. Creates `MoveJointGroup.Feedback` message
2. Sets joint names and target positions
3. Gets current positions from `current_joint_states`
4. Calculates progress percentage:
   - Uses tracked initial positions
   - Calculates: `(1.0 - sum(current_errors) / sum(initial_errors)) * 100.0`
   - Clamps to 0-100%
5. Publishes feedback via `goal_handle.publish_feedback()`

**Progress Calculation:**
- Initial error: `abs(initial_position - target_position)`
- Current error: `abs(current_position - target_position)`
- Progress: `(1.0 - sum(current_errors) / sum(initial_errors)) * 100.0`

### `_create_result(self, goal: MoveJointGroup.Goal, start_time: float, success: bool, message: str) -> MoveJointGroup.Result`

Creates result message for action goal.

**Parameters:**
- `goal`: Goal request
- `start_time`: Start time (for calculating execution time)
- `success`: Whether goal succeeded
- `message`: Result message

**Returns:** `MoveJointGroup.Result` - Result message

**Process:**
1. Creates `MoveJointGroup.Result` message
2. Sets `success` and `message`
3. Calculates `execution_time`: `time.time() - start_time`
4. Gets final positions from `current_joint_states`
5. Calculates `position_error`: Maximum error across all joints
6. Returns result

---

## Main Function

### `main(args=None)`

Main entry point for the node.

**Process:**
1. Initializes ROS2: `rclpy.init(args=args)`
2. Creates `MoveJointGroupServer` node
3. Spins node: `rclpy.spin(node)`
4. Handles `KeyboardInterrupt` gracefully
5. Cleans up: `node.destroy_node()`, `rclpy.shutdown()`

**Execution:**
```bash
ros2 run ros_control move_joint_group_server.py
```

---

## Execution Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Action Goal Received                      │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Validate Goal │
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │ Valid?        │
                    └───┬───────┬───┘
                        │       │
                   Yes  │       │  No
                        │       │
                        │       └───> Abort & Return Error
                        │
                        ▼
            ┌───────────────────────┐
            │ Refresh Discovery     │
            │ (if needed)           │
            └───────────┬───────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Track Initial Positions│
            └───────────┬───────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Group Joints by       │
            │ Controller            │
            └───────────┬───────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │ Calculate Execution Strategy  │
        │ (Simultaneous/Coordinated)   │
        └───────────────┬────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
┌───────────────┐              ┌───────────────┐
│ Action        │              │ Topic         │
│ Controllers   │              │ Controllers   │
│               │              │               │
│ Send Trajectory│              │ Publish       │
│ Goals         │              │ Commands      │
└───────┬───────┘              └───────┬───────┘
        │                               │
        └───────────────┬───────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Monitor Progress      │
            │ (Check Joint States)  │
            └───────────┬───────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
┌───────────────┐              ┌───────────────┐
│ All Reached?  │              │ Timeout/      │
│               │              │ Cancel/Error? │
└───┬───────┬───┘              └───┬───────┬───┘
    │       │                      │       │
 Yes│       │No                    │       │
    │       │                  Yes │       │No
    │       │                      │       │
    │       │                      │       │
    ▼       │                      ▼       │
┌───────────┘              ┌───────────────┘
│                           │
│ Success                   │ Cancel All Goals
│                           │ (Fail-All Strategy)
│                           │
└───────────┬───────────────┘
            │
            ▼
    ┌───────────────┐
    │ Return Result │
    └───────────────┘
```

---

## Error Handling

### Validation Errors

| Error | Cause | Action |
|-------|-------|--------|
| Array length mismatch | `joint_names`, `target_positions`, `max_velocity` lengths don't match | Abort goal, return error |
| Unknown joints | Joints not found in `joint_to_controller_map` | Abort goal, return error |

### Execution Errors

| Error | Cause | Action |
|-------|-------|--------|
| Controller unavailable | Action server not available | Log error, skip controller |
| Goal send failure | Failed to send goal to controller | Log warning, remove from active handles |
| Timeout | Joints don't reach target within timeout | Cancel all goals, abort goal |
| Cancellation | User requested cancellation | Cancel all goals, cancel goal |
| Exception | Unexpected error during execution | Cancel all goals, abort goal, log exception |

### Fail-All Strategy

On any failure:
1. Cancel all active action goals
2. Clear active goal handles
3. Clear initial position tracking
4. Return appropriate result (aborted/canceled)

---

## Configuration Parameters

### ROS2 Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `controller_joints_json` | `str` (JSON) | `''` | Controller-to-joints mapping as JSON string (ROS2 doesn't support nested dict params) |

**Note:** ROS2 doesn't support nested dictionary parameters, so `controller_joints` is serialized as a JSON string by the launch file.

**Example JSON value:**
```json
{"manipulator_controller": ["base_main_frame_joint", "main_frame_selector_frame_joint", "selector_frame_picker_frame_joint"], "scara_controller": ["scara_shoulder_joint", "scara_elbow_joint", "scara_wrist_joint"]}
```

**Parsed structure:**
```python
{
    'manipulator_controller': [
        'base_main_frame_joint',
        'main_frame_selector_frame_joint',
        'selector_frame_picker_frame_joint'
    ],
    'scara_controller': [
        'scara_shoulder_joint',
        'scara_elbow_joint',
        'scara_wrist_joint'
    ]
}
```

### YAML Configuration

Loaded from `config/move_joint_group_config.yaml`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `position_tolerance` | `float` | `0.01` | Position tolerance for success (meters/radians) |
| `execution.strategy` | `str` | `"simultaneous"` | Execution strategy |
| `execution.max_coordination_time` | `float` | `10.0` | Max coordination time (seconds) |
| `execution.timeout` | `float` | `30.0` | Execution timeout (seconds) |
| `discovery.refresh_interval` | `float` | `5.0` | Discovery refresh interval (seconds) |
| `discovery.query_timeout` | `float` | `2.0` | Controller query timeout (seconds) |
| `feedback.publish_rate` | `float` | `10.0` | Feedback publishing rate (Hz) |

---

## Dependencies

### Python Imports

| Module | Purpose |
|--------|---------|
| `rclpy` | ROS2 Python client library |
| `rclpy.node.Node` | Base node class |
| `rclpy.action.ActionServer` | Action server |
| `rclpy.action.ActionClient` | Action client |
| `rclpy.qos.QoSProfile` | QoS configuration |
| `yaml` | YAML file parsing |
| `json` | JSON parsing for `controller_joints_json` parameter |
| `time` | Time operations |
| `pathlib.Path` | Path operations |
| `typing` | Type hints |
| `ament_index_python.packages` | Finding installed package paths (for config file) |

### ROS2 Message Types

| Type | Purpose |
|------|---------|
| `ros_control.action.MoveJointGroup` | Action definition |
| `sensor_msgs.msg.JointState` | Joint state messages |
| `control_msgs.action.FollowJointTrajectory` | Trajectory action |
| `std_msgs.msg.Float64MultiArray` | Topic command messages |
| `controller_manager_msgs.srv.ListControllers` | Controller discovery service |
| `trajectory_msgs.msg.JointTrajectoryPoint` | Trajectory point |
| `builtin_interfaces.msg.Duration` | Time duration |

---

## Usage Examples

### Basic Usage (Recommended)

The server should be launched via the main bringup launch file, which handles proper startup sequencing:

```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py
```

This launch file:
1. Starts the controller manager
2. Spawns all controllers (manipulator, gripper, optionally SCARA)
3. **Waits for controllers to be active** before starting move_joint_group_server
4. Automatically extracts `controller_joints` mapping from controller YAML files

### Standalone Launch (for testing)

```bash
ros2 launch ros_control move_joint_group_server.launch.py
```

**Note:** When using standalone launch, ensure controllers are already running, otherwise the server will need to wait for periodic discovery (default 5 seconds).

### Direct Execution (not recommended)

```bash
ros2 run ros_control move_joint_group_server.py
```

**Warning:** Direct execution requires manual parameter passing and may fail if controllers are not already active.

### Python Client Example

```python
import rclpy
from rclpy.action import ActionClient
from ros_control.action import MoveJointGroup

rclpy.init()
node = rclpy.create_node('client')
client = ActionClient(node, MoveJointGroup, '/move_joint_group')
client.wait_for_server()

goal = MoveJointGroup.Goal()
goal.joint_names = ['base_main_frame_joint', 'scara_shoulder_joint']
goal.target_positions = [1.5, 0.5]
goal.max_velocity = [0.5, 1.0]

send_goal_future = client.send_goal_async(goal)
rclpy.spin_until_future_complete(node, send_goal_future)
goal_handle = send_goal_future.result()

result_future = goal_handle.get_result_async()
rclpy.spin_until_future_complete(node, result_future)
result = result_future.result().result

print(f"Success: {result.success}")
print(f"Message: {result.message}")
```

---

## Troubleshooting

### No Controllers Discovered

**Problem**: Server doesn't discover any controllers

**Check:**
1. Controller manager is running: `ros2 node list | grep controller_manager`
2. Controllers are active: `ros2 control list_controllers`
3. `controller_joints` parameter is passed correctly

**Solution:**
- Ensure robot launch file has started controller_manager
- Verify controllers are loaded and active
- Check launch file passes `controller_joints` parameter

### Joints Not Found

**Problem**: Error "Joints not found: ['joint_name']"

**Check:**
1. Joint names match exactly (case-sensitive)
2. Controllers are discovered
3. `controller_joints` parameter includes the controller

**Solution:**
- Verify joint names in goal match exactly
- Check controller discovery logs
- Ensure launch file passes correct `controller_joints` parameter

### Goal Timeout

**Problem**: Goals timeout before joints reach target

**Check:**
1. Joint limits and velocities
2. Hardware responsiveness
3. Obstacles or mechanical issues

**Solution:**
- Increase `execution.timeout` in config
- Check joint limits
- Verify hardware is responding
- Check for obstacles

---

## Related Documentation

- **Package Structure**: `docs/ros_control/package_structure.md`
- **Action Definition**: `src/ros_control/action/MoveJointGroup.action`
- **Configuration**: `src/ros_control/config/move_joint_group_config.yaml`
- **Launch File**: `src/ros_control/launch/move_joint_group_server.launch.py`

