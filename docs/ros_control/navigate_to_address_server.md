# NavigateToAddress Action Server

Translates a logical cabinet address (side, cabinet, row, column) into physical joint positions and moves the manipulator platform.

## Overview

The NavigateToAddress action server provides a high-level interface for navigating the manipulator platform to a specific cabinet cell. It converts a logical address into physical (X, Z) coordinates using configurable cabinet geometry and delegates movement to the MoveJointGroup action server.

Controls only platform joints:
- `base_main_frame_joint` (X axis, rail) — determined by `cabinet_num` + `column`
- `main_frame_selector_frame_joint` (Z axis, vertical lift) — determined by `row`

**Not controlled by this node**: gripper joints, picker joints, SCARA joints.

## Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                 NavigateToAddress Action                      │
├─────────────────────────────────────────────────────────────┤
│  1. Validate Address   ──► Check side, cabinet, row, column │
│         ↓                  against configured bounds         │
│                                                              │
│  2. Compute Position   ──► Apply geometry formulas           │
│         ↓                  X = f(cabinet_num, column)        │
│                            Z = f(row)                        │
│                                                              │
│  3. Validate Limits    ──► Check (X, Z) within URDF limits  │
│         ↓                                                    │
│                                                              │
│  4. Move Platform      ──► /move_joint_group action          │
│         ↓                  (base_main_frame_joint,           │
│                             main_frame_selector_frame_joint) │
│                                                              │
│  5. Relay Result       ──► Map MoveJointGroup result         │
│                            to NavigateToAddress result        │
└─────────────────────────────────────────────────────────────┘
```

### Position Formulas

```
X = first_cabinet_x + cabinet_num * cabinet_spacing + column * column_width + offsets.x
Z = first_row_z + row * row_height + offsets.z
```

## Action Definition

File: `ros_control/action/NavigateToAddress.action`

```yaml
# Goal
string side           # Cabinet side: "left" or "right"
uint8 cabinet_num     # Cabinet number (0-4)
uint8 row             # Row within cabinet (0-N)
uint8 column          # Column within cabinet (0-1)
---
# Result
bool success                        # true if platform reached position within tolerance
geometry_msgs/Point final_position  # End-effector position [x, y, z] in world frame
float64 position_error              # Maximum position error across joints
string message                      # Result message
---
# Feedback
float64 progress       # Completion percentage (0.0 - 1.0)
string current_phase   # Current phase: "validating", "computing", "moving", "done"
```

### Feedback Phases

| Phase | Progress | Description |
|-------|----------|-------------|
| validating | 0.0 | Checking address bounds against config |
| computing | 0.05 | Computing target (X, Z) from address |
| moving | 0.1 - 0.95 | Platform moving (relayed from MoveJointGroup) |
| done | 1.0 | Movement completed |

## Configuration

Configuration file: `ros_control/config/navigate_to_address_config.yaml`

```yaml
navigate_to_address_server:
  ros__parameters:
    cabinets:
      num_cabinets: 5           # Number of cabinets per side (0-4)
      rows_per_cabinet: 4       # Number of rows per cabinet (0-3)
      columns_per_row: 2        # Number of columns per row (0-1)

    rail:
      first_cabinet_x: 0.2     # [TEST] X position of cabinet_0, column_0 center [m]
      cabinet_spacing: 0.75    # [TEST] X distance between adjacent cabinet centers [m]
      column_width: 0.35       # [TEST] X distance between column_0 and column_1 [m]

    lift:
      first_row_z: 0.1         # [TEST] Z position of row_0 center [m]
      row_height: 0.30         # [TEST] Z distance between adjacent rows [m]

    offsets:
      x: 0.0                   # Global X correction [m]
      z: 0.0                   # Global Z correction [m]

    movement:
      max_velocity_x: 1.0      # Max rail velocity [m/s]
      max_velocity_z: 0.8      # Max lift velocity [m/s]

    joint_limits:
      x_min: 0.0
      x_max: 4.0
      z_min: -0.01
      z_max: 1.5

    position_tolerance: 0.005  # Acceptable position error [m]
    timeouts:
      move_timeout: 30.0       # Timeout for move_joint_group action [s]
```

**Note**: Values marked `[TEST]` are placeholder dimensions. Replace with real cabinet measurements.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cabinets.num_cabinets` | int | `5` | Number of cabinets per side |
| `cabinets.rows_per_cabinet` | int | `4` | Rows per cabinet |
| `cabinets.columns_per_row` | int | `2` | Columns per row |
| `rail.first_cabinet_x` | float | `0.2` | X position of cabinet 0, column 0 [m] |
| `rail.cabinet_spacing` | float | `0.75` | X distance between cabinet centers [m] |
| `rail.column_width` | float | `0.35` | X distance between columns [m] |
| `lift.first_row_z` | float | `0.1` | Z position of row 0 [m] |
| `lift.row_height` | float | `0.30` | Z distance between rows [m] |
| `offsets.x` | float | `0.0` | Global X correction [m] |
| `offsets.z` | float | `0.0` | Global Z correction [m] |
| `movement.max_velocity_x` | float | `1.0` | Max rail velocity [m/s] |
| `movement.max_velocity_z` | float | `0.8` | Max lift velocity [m/s] |
| `joint_limits.x_min` | float | `0.0` | Min X joint limit [m] |
| `joint_limits.x_max` | float | `4.0` | Max X joint limit [m] |
| `joint_limits.z_min` | float | `-0.01` | Min Z joint limit [m] |
| `joint_limits.z_max` | float | `1.5` | Max Z joint limit [m] |
| `position_tolerance` | float | `0.005` | Acceptable position error [m] |
| `timeouts.move_timeout` | float | `30.0` | MoveJointGroup timeout [s] |

## Controlled Joints

| Joint | Axis | Range | Determined by |
|-------|------|-------|---------------|
| `base_main_frame_joint` | X (prismatic) | 0.0 - 4.0 m | `cabinet_num` + `column` |
| `main_frame_selector_frame_joint` | Z (prismatic) | -0.01 - 1.5 m | `row` |

## Usage

### Command Line

```bash
# Navigate to left side, cabinet 2, row 1, column 0
ros2 action send_goal /navigate_to_address ros_control/action/NavigateToAddress \
  "{side: 'left', cabinet_num: 2, row: 1, column: 0}"

# With feedback monitoring
ros2 action send_goal /navigate_to_address ros_control/action/NavigateToAddress \
  "{side: 'left', cabinet_num: 2, row: 1, column: 0}" --feedback

# Navigate to right side, cabinet 4, row 3, column 1
ros2 action send_goal /navigate_to_address ros_control/action/NavigateToAddress \
  "{side: 'right', cabinet_num: 4, row: 3, column: 1}" --feedback
```

### Python Client

```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from ros_control.action import NavigateToAddress


class NavigateToAddressClient(Node):
    def __init__(self):
        super().__init__('navigate_to_address_client')
        self.client = ActionClient(self, NavigateToAddress, '/navigate_to_address')

    def send_goal(self, side, cabinet_num, row, column):
        self.client.wait_for_server()

        goal = NavigateToAddress.Goal()
        goal.side = side
        goal.cabinet_num = cabinet_num
        goal.row = row
        goal.column = column

        future = self.client.send_goal_async(
            goal,
            feedback_callback=self.feedback_callback
        )
        future.add_done_callback(self.goal_response_callback)

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        self.get_logger().info(
            f'Phase: {feedback.current_phase}, Progress: {feedback.progress:.1%}'
        )

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Goal rejected')
            return

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.result_callback)

    def result_callback(self, future):
        result = future.result().result
        if result.success:
            pos = result.final_position
            self.get_logger().info(
                f'Success: X={pos.x:.4f}, Z={pos.z:.4f}, '
                f'error={result.position_error:.4f}'
            )
        else:
            self.get_logger().error(f'Failed: {result.message}')


def main():
    rclpy.init()
    client = NavigateToAddressClient()
    client.send_goal('left', 2, 1, 0)
    rclpy.spin(client)


if __name__ == '__main__':
    main()
```

### C++ Client

```cpp
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include "ros_control/action/navigate_to_address.hpp"

using NavigateToAddress = ros_control::action::NavigateToAddress;
using GoalHandle = rclcpp_action::ClientGoalHandle<NavigateToAddress>;

class NavigateToAddressClient : public rclcpp::Node {
public:
    NavigateToAddressClient() : Node("navigate_to_address_client") {
        client_ = rclcpp_action::create_client<NavigateToAddress>(
            this, "/navigate_to_address"
        );
    }

    void send_goal(const std::string& side, uint8_t cabinet, uint8_t row, uint8_t col) {
        if (!client_->wait_for_action_server(std::chrono::seconds(10))) {
            RCLCPP_ERROR(get_logger(), "Action server not available");
            return;
        }

        auto goal = NavigateToAddress::Goal();
        goal.side = side;
        goal.cabinet_num = cabinet;
        goal.row = row;
        goal.column = col;

        auto options = rclcpp_action::Client<NavigateToAddress>::SendGoalOptions();
        options.feedback_callback = [this](
            GoalHandle::SharedPtr,
            const std::shared_ptr<const NavigateToAddress::Feedback> feedback
        ) {
            RCLCPP_INFO(get_logger(), "Phase: %s, Progress: %.1f%%",
                feedback->current_phase.c_str(),
                feedback->progress * 100.0
            );
        };

        options.result_callback = [this](
            const GoalHandle::WrappedResult& result
        ) {
            if (result.result->success) {
                auto pos = result.result->final_position;
                RCLCPP_INFO(get_logger(), "Success: X=%.4f, Z=%.4f, error=%.4f",
                    pos.x, pos.z, result.result->position_error
                );
            } else {
                RCLCPP_ERROR(get_logger(), "Failed: %s",
                    result.result->message.c_str()
                );
            }
        };

        client_->async_send_goal(goal, options);
    }

private:
    rclcpp_action::Client<NavigateToAddress>::SharedPtr client_;
};
```

### Run Standalone

```bash
# With default parameters
ros2 run ros_control navigate_to_address_server.py

# With custom config file
ros2 run ros_control navigate_to_address_server.py --ros-args \
  --params-file /path/to/custom_config.yaml
```

### Launch with Bringup

The server is automatically started by `manipulator_bringup.launch.py`:

```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py
```

Startup sequence:
1. `joint_state_broadcaster` spawns
2. `manipulator_controller` spawns
3. `move_joint_group_server` starts
4. `navigate_to_address_server` starts

## Implementation Details

### MultiThreadedExecutor

The server uses `MultiThreadedExecutor` to handle async operations:

```python
executor = MultiThreadedExecutor()
executor.add_node(node)
executor.spin()
```

This allows the action callback to await the MoveJointGroup action result without blocking.

### ReentrantCallbackGroup

All clients use a `ReentrantCallbackGroup` to allow concurrent callback execution:

```python
self.callback_group = ReentrantCallbackGroup()
self.move_joint_group_client = ActionClient(
    self, MoveJointGroup, '/move_joint_group',
    callback_group=self.callback_group
)
```

### Feedback Relay

MoveJointGroup progress (0-100%) is mapped to NavigateToAddress progress (0.1-0.95):

```python
normalized = move_fb.progress_percentage / 100.0
feedback.progress = 0.1 + normalized * 0.85
```

### Side Parameter

The `side` field is validated but does **not** affect platform position currently. It is reserved for future use (e.g., arm reaching direction, per-side geometry offsets).

## Dependencies

### Required Actions

| Action | Type | Description |
|--------|------|-------------|
| `/move_joint_group` | `ros_control/action/MoveJointGroup` | Moves platform joints |

### Package Dependencies

- `rclpy` - ROS2 Python client library
- `ros_control` - For `MoveJointGroup` and `NavigateToAddress` action types
- `geometry_msgs` - For `Point` message in result

## Files

| File | Description |
|------|-------------|
| `action/NavigateToAddress.action` | Action definition |
| `src/navigate_to_address_server.py` | Main node implementation |
| `config/navigate_to_address_config.yaml` | Default configuration |

## Error Handling

The server implements fail-fast error handling. If any step fails, the action aborts immediately with an error message:

| Error | Cause |
|-------|-------|
| `Invalid side: '{side}'. Expected 'left' or 'right'` | Invalid side value |
| `cabinet_num {n} out of range [0, {max})` | Cabinet number exceeds configured count |
| `row {n} out of range [0, {max})` | Row exceeds configured rows per cabinet |
| `column {n} out of range [0, {max})` | Column exceeds configured columns per row |
| `Computed X={x} outside joint limits [0.0, 4.0]` | Computed position exceeds URDF joint limit |
| `Computed Z={z} outside joint limits [-0.01, 1.5]` | Computed position exceeds URDF joint limit |
| `MoveJointGroup action server not available` | MoveJointGroup server not running |
| `Goal rejected by MoveJointGroup server` | MoveJointGroup rejected the goal |

## Address Examples

| Address | X | Z |
|---------|---|---|
| cabinet=0, row=0, col=0 | 0.20 | 0.10 |
| cabinet=0, row=0, col=1 | 0.55 | 0.10 |
| cabinet=2, row=1, col=0 | 1.70 | 0.40 |
| cabinet=4, row=3, col=1 | 3.55 | 1.00 |

## See Also

- [navigate_to_address_action.md](navigate_to_address_action.md) - Architectural design document
- [move_joint_group_server.md](move_joint_group_server.md) - Joint movement action server
- [get_container_server.md](get_container_server.md) - Container pick action server
- [place_container_server.md](place_container_server.md) - Container place action server
