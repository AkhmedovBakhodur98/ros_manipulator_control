# Stage 6.6b onwards — full 6-slave EtherCAT chain under ros2_control.
#
# Renders manipulator_description/urdf/robot.urdf.xacro with
# hardware:=ethercat_full + use_scara:=true. Spawns:
#   - joint_state_broadcaster
#   - manipulator_trajectory_controller (active — primary motion)
#   - control_word_controller, mode_of_operation_controller (inactive;
#     activated on demand by the homing action server)
#   - homing action server (manipulator_homing.homing_action_server)
#   - safety / limit monitor (manipulator_homing.safety_monitor)
#
# Launch arguments mirror ethercat_bench.launch.py plus a `use_scara`
# toggle so the base-only build (3 of 6 drives) can still come up
# without the SCARA arm on the bench.
#
# Wrap with `chrt -f 80` for steady-state RT priority — see Stage 6
# exit-criterion recipe in bringup.md.

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_description = FindPackageShare("manipulator_description")
    pkg_hw = FindPackageShare("manipulator_hardware_interface")

    use_scara = LaunchConfiguration("use_scara")

    slave_config_dir = PathJoinSubstitution([pkg_hw, "config", "ethercat"])
    controllers_yaml = PathJoinSubstitution(
        [pkg_hw, "config", "ethercat_full_controllers.yaml"]
    )
    urdf_xacro = PathJoinSubstitution([pkg_description, "urdf", "robot.urdf.xacro"])

    robot_description_content = ParameterValue(
        Command([
            FindExecutable(name="xacro"), " ",
            urdf_xacro,
            " hardware:=ethercat_full",
            " use_scara:=", use_scara,
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

    jtc_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["manipulator_trajectory_controller",
                   "--controller-manager", "/controller_manager"],
    )

    # Loaded inactive — the homing action server activates them when a
    # goal arrives and deactivates them after the run.
    cw_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["control_word_controller",
                   "--controller-manager", "/controller_manager",
                   "--inactive"],
    )

    mode_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["mode_of_operation_controller",
                   "--controller-manager", "/controller_manager",
                   "--inactive"],
    )

    homing_node = Node(
        package="manipulator_homing",
        executable="homing_action_server",
        output="both",
    )

    safety_node = Node(
        package="manipulator_homing",
        executable="safety_monitor",
        output="both",
    )

    # Spawn controllers only after joint_state_broadcaster is up — gives
    # the hardware interface time to enumerate slaves before any other
    # controller tries to claim interfaces.
    after_jsb = RegisterEventHandler(
        OnProcessExit(
            target_action=jsb_spawner,
            on_exit=[jtc_spawner, cw_spawner, mode_spawner,
                     homing_node, safety_node],
        )
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "use_scara",
            default_value="true",
            description="Include the 3 SCARA joints (aliases 4..6) in the bring-up. "
                        "Set false when bringing up the base axes only.",
        ),
        control_node,
        rsp_node,
        jsb_spawner,
        after_jsb,
    ])
