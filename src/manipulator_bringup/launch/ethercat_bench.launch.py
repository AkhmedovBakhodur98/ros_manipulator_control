# Stage 6 single-slave bench bring-up: A6-200EC (alias 6) under ros2_control.
#
# Renders manipulator_description/urdf/robot.urdf.xacro with hardware:=ethercat_bench,
# starts ros2_control_node + robot_state_publisher, spawns joint_state_broadcaster
# and forward_position_controller (active) plus bench_trajectory_controller (inactive).
#
# For long-running tests (Stage 6 exit criterion = 10 min without SafeOP drops) wrap
# the launch in `chrt -f 80` so the controller_manager update loop holds RT priority.

from launch import LaunchDescription
from launch.actions import RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, FindExecutable, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_description = FindPackageShare("manipulator_description")
    pkg_hw = FindPackageShare("manipulator_hardware_interface")

    slave_config_dir = PathJoinSubstitution([pkg_hw, "config", "ethercat"])
    controllers_yaml = PathJoinSubstitution(
        [pkg_hw, "config", "ethercat_bench_controllers.yaml"]
    )
    urdf_xacro = PathJoinSubstitution(
        [pkg_description, "urdf", "robot.urdf.xacro"]
    )

    robot_description_content = ParameterValue(
        Command([
            FindExecutable(name="xacro"), " ",
            urdf_xacro,
            " hardware:=ethercat_bench",
            " slave_config_dir:=", slave_config_dir,
        ]),
        value_type=str,
    )
    robot_description = {"robot_description": robot_description_content}

    control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[robot_description, controllers_yaml],
        output="both",
    )

    rsp_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[robot_description],
        output="both",
    )

    jsb_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster",
                   "--controller-manager", "/controller_manager"],
    )

    fpc_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["forward_position_controller",
                   "--controller-manager", "/controller_manager"],
    )

    # JTC loaded but kept inactive — switch with `ros2 control switch_controllers`.
    jtc_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["bench_trajectory_controller",
                   "--controller-manager", "/controller_manager",
                   "--inactive"],
    )

    delayed_position_controllers = RegisterEventHandler(
        OnProcessExit(target_action=jsb_spawner, on_exit=[fpc_spawner, jtc_spawner])
    )

    return LaunchDescription([
        control_node,
        rsp_node,
        jsb_spawner,
        delayed_position_controllers,
    ])
