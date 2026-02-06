# GetContainer Action Server

Orchestrates container pick operations by coordinating gripper control and manipulator movement.

## Overview

The GetContainer action server provides a high-level interface for picking containers. It coordinates multiple subsystems (gripper services and MoveJointGroup action) to execute a complete pick sequence automatically.

## Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    GetContainer Action                       │
├─────────────────────────────────────────────────────────────┤
│  1. Open Gripper        ──► /gripper/open service           │
│         ↓                                                    │
│  2. Move to Container   ──► /move_joint_group action        │
│         ↓                   (base_main_frame_joint,         │
│                              main_frame_selector_frame)     │
│         ↓                                                    │
│  3. Close Gripper       ──► /gripper/close service          │
│         ↓                   + wait gripper_settle_time      │
│                                                              │
│  4. Lift Container      ──► /move_joint_group action        │
│                             (main_frame_selector_frame)     │
└─────────────────────────────────────────────────────────────┘
```

## Action Definition

File: `ros_control/action/GetContainer.action`

```yaml
# Goal (empty - trigger only)
---
# Result
bool success
string message
float64 execution_time
---
# Feedback
string current_step
float32 progress_percentage
```

### Feedback Steps

| Step | Progress | Description |
|------|----------|-------------|
| Opening gripper | 0% | Sending open command to gripper |
| Moving to container | 25% | Moving manipulator to container position |
| Closing gripper | 50% | Closing gripper and waiting for settle |
| Lifting container | 75% | Lifting selector frame with container |
| Complete | 100% | Operation finished successfully |

## Configuration

Configuration file: `ros_control/config/get_container_config.yaml`

```yaml
get_container_server:
  ros__parameters:
    # Target position for container pickup
    container_position:
      base_main_frame_joint: 1.5              # X axis position (meters)
      main_frame_selector_frame_joint: 0.2    # Z axis position (meters)

    # Lift parameters
    lift_joint: main_frame_selector_frame_joint  # Joint for Z-axis lift
    lift_height: 0.20                            # Lift distance (meters)

    # Timing
    gripper_settle_time: 1.0    # Wait time after gripper close (seconds)

    # Timeouts
    timeouts:
      move_timeout: 30.0        # MoveJointGroup timeout (seconds)
      gripper_timeout: 5.0      # Gripper service timeout (seconds)

    position_tolerance: 0.01    # Position tolerance (meters)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `container_position` | dict | see above | Target joint positions for pickup |
| `lift_joint` | string | `main_frame_selector_frame_joint` | Joint used for lifting |
| `lift_height` | float | `0.20` | Vertical lift distance in meters |
| `gripper_settle_time` | float | `1.0` | Delay after gripper close |
| `timeouts.move_timeout` | float | `30.0` | Timeout for move operations |
| `timeouts.gripper_timeout` | float | `5.0` | Timeout for gripper services |

## Usage

### Command Line

```bash
# Send goal and wait for result
ros2 action send_goal /get_container ros_control/action/GetContainer "{}"

# Send goal with feedback
ros2 action send_goal /get_container ros_control/action/GetContainer "{}" --feedback
```

### Python Client

```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from ros_control.action import GetContainer


class GetContainerClient(Node):
    def __init__(self):
        super().__init__('get_container_client')
        self.client = ActionClient(self, GetContainer, '/get_container')

    def send_goal(self):
        self.client.wait_for_server()

        goal = GetContainer.Goal()
        future = self.client.send_goal_async(
            goal,
            feedback_callback=self.feedback_callback
        )
        future.add_done_callback(self.goal_response_callback)

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        self.get_logger().info(
            f'Step: {feedback.current_step}, Progress: {feedback.progress_percentage}%'
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
            self.get_logger().info(
                f'Success: {result.message} (took {result.execution_time:.2f}s)'
            )
        else:
            self.get_logger().error(f'Failed: {result.message}')


def main():
    rclpy.init()
    client = GetContainerClient()
    client.send_goal()
    rclpy.spin(client)


if __name__ == '__main__':
    main()
```

### C++ Client

```cpp
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include "ros_control/action/get_container.hpp"

using GetContainer = ros_control::action::GetContainer;
using GoalHandle = rclcpp_action::ClientGoalHandle<GetContainer>;

class GetContainerClient : public rclcpp::Node {
public:
    GetContainerClient() : Node("get_container_client") {
        client_ = rclcpp_action::create_client<GetContainer>(
            this, "/get_container"
        );
    }

    void send_goal() {
        if (!client_->wait_for_action_server(std::chrono::seconds(10))) {
            RCLCPP_ERROR(get_logger(), "Action server not available");
            return;
        }

        auto goal = GetContainer::Goal();

        auto options = rclcpp_action::Client<GetContainer>::SendGoalOptions();
        options.feedback_callback = [this](
            GoalHandle::SharedPtr,
            const std::shared_ptr<const GetContainer::Feedback> feedback
        ) {
            RCLCPP_INFO(get_logger(), "Step: %s, Progress: %.1f%%",
                feedback->current_step.c_str(),
                feedback->progress_percentage
            );
        };

        options.result_callback = [this](
            const GoalHandle::WrappedResult& result
        ) {
            if (result.result->success) {
                RCLCPP_INFO(get_logger(), "Success: %s",
                    result.result->message.c_str()
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
    rclcpp_action::Client<GetContainer>::SharedPtr client_;
};
```

### Run Standalone

```bash
# With default parameters
ros2 run ros_control get_container_server.py

# With custom config file
ros2 run ros_control get_container_server.py --ros-args \
  --params-file /path/to/custom_config.yaml
```

### Launch with Bringup

The server is automatically started by `manipulator_bringup.launch.py`:

```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py
```

Startup sequence:
1. `joint_state_broadcaster` spawns
2. `gripper_controller` spawns
3. `gripper_service` starts
4. `manipulator_controller` spawns
5. `move_joint_group_server` starts
6. `get_container_server` starts

## Implementation Details

### MultiThreadedExecutor

The server uses `MultiThreadedExecutor` to handle async operations:

```python
executor = MultiThreadedExecutor()
executor.add_node(node)
executor.spin()
```

This allows the action callback to await service calls and other action results without blocking.

### ReentrantCallbackGroup

All clients use a `ReentrantCallbackGroup` to allow concurrent callback execution:

```python
self.callback_group = ReentrantCallbackGroup()
self.gripper_open_client = self.create_client(
    Trigger, '/gripper/open', callback_group=self.callback_group
)
```

### Gripper Settle Time

After closing the gripper, the server waits `gripper_settle_time` seconds before lifting. This ensures the gripper has physically closed before attempting to lift the container:

```python
time.sleep(self.config.get('gripper_settle_time', 1.0))
```

## Dependencies

### Required Services

| Service | Type | Description |
|---------|------|-------------|
| `/gripper/open` | `std_srvs/srv/Trigger` | Opens the gripper |
| `/gripper/close` | `std_srvs/srv/Trigger` | Closes the gripper |

### Required Actions

| Action | Type | Description |
|--------|------|-------------|
| `/move_joint_group` | `ros_control/action/MoveJointGroup` | Moves manipulator joints |

### Package Dependencies

- `rclpy` - ROS2 Python client library
- `std_srvs` - For `Trigger` service type
- `ros_control` - For `MoveJointGroup` and `GetContainer` action types

## Files

| File | Description |
|------|-------------|
| `action/GetContainer.action` | Action definition |
| `src/get_container_server.py` | Main node implementation |
| `config/get_container_config.yaml` | Default configuration |

## Error Handling

The server implements fail-fast error handling. If any step fails, the action aborts immediately with an error message:

| Error | Cause |
|-------|-------|
| `Failed to open gripper: ...` | Gripper open service failed or unavailable |
| `Failed to move to container: ...` | MoveJointGroup action failed or timeout |
| `Failed to close gripper: ...` | Gripper close service failed |
| `Failed to lift container: ...` | Lift movement failed or timeout |

## See Also

- [gripper_service.md](gripper_service.md) - Gripper control services
- [move_joint_group_server.md](move_joint_group_server.md) - Joint movement action server
