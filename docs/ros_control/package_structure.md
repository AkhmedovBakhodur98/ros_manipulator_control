# ros_control Package Documentation

## Overview

The `ros_control` package provides a unified ROS2 control interface for moving multiple joints simultaneously across different controllers (manipulator, SCARA, gripper, and future equipment). It implements a high-level action server that coordinates movement across multiple low-level controllers, abstracting away the complexity of managing different controller types and interfaces.

## Package Structure

```
src/ros_control/
├── CMakeLists.txt                    # Build configuration
├── package.xml                       # Package metadata and dependencies
├── README.md                         # Quick start guide
├── action/
│   └── MoveJointGroup.action         # Action definition (Goal, Result, Feedback)
├── config/
│   └── move_joint_group_config.yaml  # Server configuration (tolerances, timeouts, strategies)
├── launch/
│   └── move_joint_group_server.launch.py  # Launch file for the action server
└── src/
    └── move_joint_group_server.py    # Action server implementation
```

---

## File Descriptions

### Build Files

#### `CMakeLists.txt`
CMake build configuration for the ROS2 package.

**Key sections:**
- **Action generation**: Generates ROS2 action interfaces from `MoveJointGroup.action`
- **Python script installation**: Installs `move_joint_group_server.py` as executable
- **Resource installation**: Installs `config/` and `launch/` directories

**Dependencies:**
- `ament_cmake` - ROS2 build system
- `rosidl_default_generators` - For generating action interfaces

#### `package.xml`
ROS2 package manifest defining package metadata and dependencies.

**Package information:**
- Name: `ros_control`
- Version: `0.1.0`
- Description: Unified ROS2 control interface for manipulator, SCARA, and other equipment
- License: Apache-2.0

**Dependencies:**

| Category | Package | Purpose |
|----------|---------|---------|
| **Build** | `ament_cmake` | ROS2 build system |
| **Action** | `rosidl_default_generators` | Generate action interfaces |
| **Action** | `rosidl_default_runtime` | Runtime support for generated interfaces |
| **ROS2 Core** | `rclpy` | ROS2 Python client library |
| **Messages** | `sensor_msgs` | JointState messages |
| **Messages** | `control_msgs` | FollowJointTrajectory action |
| **Messages** | `std_msgs` | Standard message types |
| **Messages** | `trajectory_msgs` | JointTrajectory messages |
| **Messages** | `controller_manager_msgs` | Controller discovery services |
| **Messages** | `builtin_interfaces` | Time and duration types |
| **Control** | `controller_manager` | Controller lifecycle management |
| **Control** | `ros2_control` | Hardware abstraction framework |
| **Python** | `pyyaml` | YAML configuration parsing |

---

### Action Definition

#### `action/MoveJointGroup.action`
Defines the action interface for coordinated joint movement.

**Goal (Request):**
```yaml
string[] joint_names          # Individual joint names (not groups)
float64[] target_positions    # Target positions (meters for prismatic, radians for revolute)
float64[] max_velocity        # Max velocity per joint (0.0 = use default)
```

**Result (Response):**
```yaml
bool success                  # True if joints reached target within tolerance
float64[] final_position     # Actually achieved positions
float64 position_error       # Maximum position error across all joints
float64 execution_time        # Total execution time (seconds)
string message               # Result message (success/error description)
```

**Feedback (Progress Updates):**
```yaml
string[] joint_names         # Joint names being moved
float64[] current_positions  # Current joint positions
float64[] target_positions   # Target joint positions
float32 progress_percentage  # Progress (0-100%)
```

**Usage Example:**
```bash
ros2 action send_goal /move_joint_group \
  ros_control/action/MoveJointGroup "{
    joint_names: ['base_main_frame_joint', 'scara_shoulder_joint'],
    target_positions: [1.5, 0.5],
    max_velocity: [0.5, 1.0]
  }"
```

---

### Configuration Files

#### `config/move_joint_group_config.yaml`
Configuration file for the MoveJointGroup action server.

**Configuration Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `position_tolerance` | float | 0.01 | Position tolerance for success (meters/radians) |
| `execution.strategy` | string | "simultaneous" | Execution strategy: "simultaneous" or "coordinated" |
| `execution.max_coordination_time` | float | 10.0 | Max time for coordinated execution (seconds) |
| `execution.timeout` | float | 30.0 | Maximum time to wait for completion (seconds) |
| `discovery.refresh_interval` | float | 5.0 | Controller discovery refresh interval (seconds) |
| `discovery.query_timeout` | float | 2.0 | Timeout for controller queries (seconds) |
| `feedback.publish_rate` | float | 10.0 | Feedback publishing rate (Hz) |

**Execution Strategies:**

1. **`simultaneous`** (default):
   - All joints start moving at once
   - Each joint finishes independently when it reaches its target
   - Faster overall execution
   - Joints may arrive at different times

2. **`coordinated`**:
   - All joints start moving at once
   - All joints arrive at their targets at the same time
   - Calculates timing to synchronize arrival
   - Useful for coordinated motions (e.g., maintaining orientation)

**Example Configuration:**
```yaml
position_tolerance: 0.01

execution:
  strategy: "simultaneous"
  max_coordination_time: 10.0
  timeout: 30.0

discovery:
  refresh_interval: 5.0
  query_timeout: 2.0

feedback:
  publish_rate: 10.0
```

---

### Source Code

#### `src/move_joint_group_server.py`
Main implementation of the MoveJointGroup action server.

**Class: `MoveJointGroupServer`**

**Key Responsibilities:**
1. **Controller Discovery**: Automatically discovers available controllers and their joints
2. **Joint Mapping**: Maps joints to their controllers and interface types
3. **Goal Execution**: Coordinates movement across multiple controllers
4. **Progress Monitoring**: Monitors joint states and publishes feedback
5. **Error Handling**: Implements fail-all strategy (cancels all goals on failure)

**Main Components:**

| Component | Type | Purpose |
|-----------|------|---------|
| `action_server` | `ActionServer` | Receives MoveJointGroup action goals |
| `joint_state_sub` | `Subscription` | Subscribes to `/joint_states` for current positions |
| `list_controllers_client` | `ServiceClient` | Queries controller manager for active controllers |
| `trajectory_action_clients` | `Dict[ActionClient]` | Action clients for trajectory controllers (created on demand) |
| `topic_publishers` | `Dict[Publisher]` | Publishers for topic-based controllers (created on demand) |

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `discover_controllers()` | Discovers active controllers and maps joints |
| `_get_controller_joints()` | Retrieves joint list for a controller from ROS2 parameters |
| `validate_goal()` | Validates goal request (array lengths, joint existence) |
| `group_joints_by_controller()` | Groups joints by their controllers |
| `execute_goal_callback()` | Main execution handler for action goals |
| `_execute_trajectory_action()` | Sends trajectory goals to action-based controllers |
| `_publish_topic_command()` | Publishes commands to topic-based controllers |
| `_check_joints_reached()` | Checks if joints are within tolerance |
| `_publish_feedback()` | Publishes progress feedback |
| `_cancel_all_active_goals()` | Cancels all active goals (fail-all strategy) |

**Controller Interface Types:**

1. **Action-based** (`JointTrajectoryController`):
   - Uses `FollowJointTrajectory` action
   - Interface: `/{controller_name}/follow_joint_trajectory`
   - Supports velocity constraints and timing

2. **Topic-based** (`ForwardCommandController`):
   - Uses `Float64MultiArray` topic
   - Interface: `/{controller_name}/commands`
   - Direct position commands

**Controller Discovery Process:**

1. Query `controller_manager/list_controllers` service
2. Filter active controllers (skip `joint_state_broadcaster`)
3. For each controller:
   - Get controller type
   - Get joint list from ROS2 `controller_joints` parameter (passed by launch file)
   - Determine interface type (action or topic) based on controller type
   - Map joints to controller
4. Store mapping: `joint_name -> (controller_name, controller_type, interface_name)`

**Note:** The `controller_joints` parameter is a dictionary passed by the launch file with structure:
```python
{
    'controller_name': ['joint1', 'joint2', ...],
    ...
}
```

**Execution Flow:**

1. **Goal Received**: Validate goal request
2. **Discovery Refresh**: Refresh controller discovery if needed
3. **Group Joints**: Group joints by their controllers
4. **Send Commands**:
   - Action controllers: Send trajectory goals asynchronously
   - Topic controllers: Publish position commands
5. **Monitor Progress**:
   - Subscribe to `/joint_states`
   - Check if all joints are within tolerance
   - Publish feedback periodically
6. **Completion**:
   - Success: All joints within tolerance
   - Timeout: Maximum time exceeded
   - Cancellation: User requested cancellation
7. **Fail-All Strategy**: On any failure, cancel all active goals

**Error Handling:**

- **Validation Errors**: Invalid goal (array length mismatch, unknown joints)
- **Controller Errors**: Controller not available, goal rejected
- **Timeout**: Joints don't reach target within timeout
- **Cancellation**: User cancels goal (cancels all active goals)

---

### Launch Files

#### `launch/move_joint_group_server.launch.py`
Launch file for starting the MoveJointGroup action server.

**See detailed documentation in:** `docs/ros_control/move_joint_group_server_launch.md`

**Quick Summary:**
- Launches `move_joint_group_server.py` node
- Loads configuration from `config/move_joint_group_config.yaml`
- Supports `use_sim_time` parameter for simulation

---

## Architecture

### System Integration

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Application                          │
│  (sends MoveJointGroup goals, receives feedback/results)    │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│          MoveJointGroup Action Server                        │
│  (ros_control package)                                      │
│  - Discovers controllers                                     │
│  - Coordinates movement across controllers                  │
│  - Monitors progress                                         │
└───────┬───────────────────────┬─────────────────────────────┘
        │                       │
        ▼                       ▼
┌──────────────────┐   ┌──────────────────┐
│  Controller 1    │   │  Controller 2    │
│  (Manipulator)   │   │  (SCARA)         │
│                  │   │                  │
│  Joints:         │   │  Joints:         │
│  - base_main_... │   │  - scara_shoulder│
│  - main_frame_...│   │  - scara_elbow   │
│  - selector_...  │   │  - scara_wrist   │
└────────┬─────────┘   └────────┬─────────┘
         │                      │
         ▼                      ▼
┌─────────────────────────────────────────────┐
│         Controller Manager                   │
│  (ros2_control framework)                   │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│         Hardware Interface                  │
│  (robot hardware abstraction)               │
└─────────────────────────────────────────────┘
```

### Data Flow

1. **Goal Request**:
   ```
   Application → MoveJointGroup Action Server
   ```

2. **Controller Discovery**:
   ```
   Action Server → Controller Manager (list_controllers service)
   Controller Manager → Action Server (controller list)
   ```

3. **Command Execution**:
   ```
   Action Server → Controllers (trajectory actions or topic commands)
   ```

4. **State Monitoring**:
   ```
   Hardware → Joint State Broadcaster → /joint_states topic
   /joint_states → Action Server (monitoring)
   ```

5. **Feedback/Result**:
   ```
   Action Server → Application (feedback during execution, result on completion)
   ```

---

## Dependencies

### ROS2 Packages

| Package | Purpose |
|---------|---------|
| `rclpy` | ROS2 Python client library |
| `sensor_msgs` | JointState messages |
| `control_msgs` | FollowJointTrajectory action interface |
| `std_msgs` | Standard message types |
| `trajectory_msgs` | JointTrajectory message types |
| `controller_manager_msgs` | Controller discovery services |
| `builtin_interfaces` | Time and duration types |
| `controller_manager` | Controller lifecycle management |
| `ros2_control` | Hardware abstraction framework |

### Python Packages

| Package | Purpose |
|---------|---------|
| `pyyaml` | YAML configuration file parsing |

---

## ROS2 Topics

### Subscribed Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/joint_states` | `sensor_msgs/JointState` | Current joint positions, velocities, efforts |

### Published Topics

None (uses action interface for communication)

---

## ROS2 Services

### Service Clients

| Service | Type | Description |
|---------|------|-------------|
| `/controller_manager/list_controllers` | `controller_manager_msgs/ListControllers` | Query active controllers |

---

## ROS2 Actions

### Action Server

| Action | Type | Description |
|--------|------|-------------|
| `/move_joint_group` | `ros_control/action/MoveJointGroup` | Main action interface for coordinated joint movement |

### Action Clients (Created Dynamically)

| Action | Type | Description |
|--------|------|-------------|
| `/{controller_name}/follow_joint_trajectory` | `control_msgs/action/FollowJointTrajectory` | Trajectory control for action-based controllers |

---

## ROS2 Parameters

### Node Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `use_sim_time` | bool | Use simulation clock if true |
| `controller_joints` | dict | Controller-to-joints mapping (passed by launch file) |

**`controller_joints` Parameter Structure:**
```yaml
controller_joints:
  manipulator_controller:
    - base_main_frame_joint
    - main_frame_selector_frame_joint
    - selector_frame_picker_frame_joint
  scara_controller:
    - scara_shoulder_joint
    - scara_elbow_joint
    - scara_wrist_joint
```

---

## Usage Examples

### Basic Usage

**Launch the server:**
```bash
ros2 launch ros_control move_joint_group_server.launch.py
```

**Move manipulator joints:**
```bash
ros2 action send_goal /move_joint_group \
  ros_control/action/MoveJointGroup "{
    joint_names: [
      'base_main_frame_joint',
      'main_frame_selector_frame_joint',
      'selector_frame_picker_frame_joint'
    ],
    target_positions: [1.5, 0.5, 0.1],
    max_velocity: [0.5, 0.3, 0.2]
  }"
```

**Move SCARA arm:**
```bash
ros2 action send_goal /move_joint_group \
  ros_control/action/MoveJointGroup "{
    joint_names: [
      'scara_shoulder_joint',
      'scara_elbow_joint',
      'scara_wrist_joint'
    ],
    target_positions: [0.5, 0.3, 1.0],
    max_velocity: [1.0, 1.0, 2.0]
  }"
```

**Mixed movement (manipulator + SCARA):**
```bash
ros2 action send_goal /move_joint_group \
  ros_control/action/MoveJointGroup "{
    joint_names: [
      'base_main_frame_joint',
      'scara_shoulder_joint'
    ],
    target_positions: [1.0, 0.5],
    max_velocity: [0.5, 1.0]
  }"
```

**Use default velocities:**
```bash
ros2 action send_goal /move_joint_group \
  ros_control/action/MoveJointGroup "{
    joint_names: ['base_main_frame_joint'],
    target_positions: [2.0],
    max_velocity: [0.0]  # 0.0 = use default velocity
  }"
```

### Python Client Example

```python
import rclpy
from rclpy.action import ActionClient
from ros_control.action import MoveJointGroup

def main():
    rclpy.init()
    node = rclpy.create_node('move_joint_group_client')
    
    action_client = ActionClient(node, MoveJointGroup, '/move_joint_group')
    
    # Wait for server
    action_client.wait_for_server()
    
    # Create goal
    goal = MoveJointGroup.Goal()
    goal.joint_names = ['base_main_frame_joint', 'scara_shoulder_joint']
    goal.target_positions = [1.5, 0.5]
    goal.max_velocity = [0.5, 1.0]
    
    # Send goal
    send_goal_future = action_client.send_goal_async(goal)
    rclpy.spin_until_future_complete(node, send_goal_future)
    goal_handle = send_goal_future.result()
    
    # Wait for result
    result_future = goal_handle.get_result_async()
    rclpy.spin_until_future_complete(node, result_future)
    result = result_future.result().result
    
    print(f"Success: {result.success}")
    print(f"Message: {result.message}")
    print(f"Execution time: {result.execution_time:.2f}s")
    
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

---

## Building

```bash
cd /path/to/manipulator_ros_control
colcon build --packages-select ros_control
source install/setup.bash
```

---

## Configuration

### Adjusting Position Tolerance

Edit `config/move_joint_group_config.yaml`:
```yaml
position_tolerance: 0.005  # 5mm or ~0.29 degrees
```

### Changing Execution Strategy

```yaml
execution:
  strategy: "coordinated"  # or "simultaneous"
```

### Adjusting Timeouts

```yaml
execution:
  timeout: 60.0  # Increase timeout for slow movements
```

### Changing Discovery Refresh Rate

```yaml
discovery:
  refresh_interval: 10.0  # Refresh every 10 seconds
```

---

## Troubleshooting

### Controller Not Found

**Problem**: Error "Joints not found: ['joint_name']"

**Solutions**:
1. Ensure controller is active: `ros2 control list_controllers`
2. Check controller_joints parameter is passed correctly by launch file
3. Verify joint names match exactly (case-sensitive)

### Goal Timeout

**Problem**: Goal times out before joints reach target

**Solutions**:
1. Increase `execution.timeout` in config
2. Check joint limits and velocities
3. Verify hardware is responding
4. Check for obstacles or mechanical issues

### Controller Discovery Fails

**Problem**: No controllers discovered

**Solutions**:
1. Ensure controller_manager is running
2. Check controller_manager service: `ros2 service list | grep controller_manager`
3. Verify controllers are active: `ros2 control list_controllers`
4. Check launch file passes controller_joints parameter correctly

---

## Extending the Package

### Adding Support for New Controllers

1. **Add controller to launch file**: Update launch file to pass controller_joints parameter
2. **Verify interface type**: Ensure controller uses either:
   - `JointTrajectoryController` (action-based)
   - `ForwardCommandController` (topic-based)
3. **Test discovery**: Launch server and verify controller is discovered

### Adding New Execution Strategies

1. Edit `src/move_joint_group_server.py`
2. Add new strategy to `_default_config()` in `execution.strategy`
3. Implement strategy logic in `execute_goal_callback()`
4. Update config file documentation

---

## Related Documentation

- **Launch File**: `docs/ros_control/move_joint_group_server_launch.md`
- **Package README**: `src/ros_control/README.md`
- **Manipulator Description**: `docs/manipulator_description/package_structure.md`
- **SCARA Description**: `docs/scara_description/package_structure.md`

