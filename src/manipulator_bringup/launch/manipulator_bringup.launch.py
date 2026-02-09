#!/usr/bin/env python3
"""
Main launch file for manipulator ROS2 control system

This launch file:
- Processes the xacro file with ros2_control enabled
- Starts robot_state_publisher
- Starts ros2_control controller_manager
- Spawns all controllers (manipulator, gripper, optional SCARA)
- Starts unified control interface (move_joint_group_server)
- Automatically extracts controller->joints mapping from YAML files
- Optionally launches RViz2

Usage:
    ros2 launch manipulator_bringup manipulator_bringup.launch.py
    ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true
    ros2 launch manipulator_bringup manipulator_bringup.launch.py rviz:=false
"""

import yaml
import json
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler, OpaqueFunction
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue


def get_controller_joints(manip_controllers_file, scara_controllers_file, use_scara):
    """
    Extract controller->joints mapping from YAML files.
    
    Args:
        manip_controllers_file: Path to manipulator_controllers.yaml
        scara_controllers_file: Path to scara_controllers.yaml
        use_scara: Whether SCARA is enabled
    
    Returns:
        Dictionary mapping controller names to joint lists
    """
    controller_joints = {}
    
    try:
        # Parse manipulator controllers
        with open(manip_controllers_file, 'r') as f:
            manip_config = yaml.safe_load(f)
        
        # Extract manipulator_controller joints
        if 'manipulator_controller' in manip_config:
            if 'ros__parameters' in manip_config['manipulator_controller']:
                joints = manip_config['manipulator_controller']['ros__parameters'].get('joints', [])
                if joints:
                    controller_joints['manipulator_controller'] = joints
        
        # Extract gripper_controller joints
        if 'gripper_controller' in manip_config:
            if 'ros__parameters' in manip_config['gripper_controller']:
                joints = manip_config['gripper_controller']['ros__parameters'].get('joints', [])
                if joints:
                    controller_joints['gripper_controller'] = joints
        
        # Parse SCARA controllers if enabled
        if use_scara:
            with open(scara_controllers_file, 'r') as f:
                scara_config = yaml.safe_load(f)
            
            if 'scara_controller' in scara_config:
                if 'ros__parameters' in scara_config['scara_controller']:
                    joints = scara_config['scara_controller']['ros__parameters'].get('joints', [])
                    if joints:
                        controller_joints['scara_controller'] = joints
    
    except Exception as e:
        print(f"Warning: Failed to extract controller joints: {e}")
        # Return empty dict, move_joint_group_server will discover dynamically
        return {}
    
    return controller_joints


def generate_launch_description():
    # Package directories
    pkg_share = FindPackageShare('manipulator_description')
    scara_pkg_share = FindPackageShare('scara_description')
    ros_control_pkg_share = FindPackageShare('ros_control')
    
    # Paths
    urdf_file = PathJoinSubstitution([pkg_share, 'urdf', 'robot.urdf.xacro'])
    manip_controllers_file = PathJoinSubstitution([pkg_share, 'config', 'manipulator_controllers.yaml'])
    scara_controllers_file = PathJoinSubstitution([scara_pkg_share, 'config', 'scara_controllers.yaml'])
    rviz_config_file = PathJoinSubstitution([pkg_share, 'rviz', 'view_robot.rviz'])
    move_joint_group_config_file = PathJoinSubstitution([ros_control_pkg_share, 'config', 'move_joint_group_config.yaml'])
    gripper_config_file = PathJoinSubstitution([ros_control_pkg_share, 'config', 'gripper_config.yaml'])
    get_container_config_file = PathJoinSubstitution([ros_control_pkg_share, 'config', 'get_container_config.yaml'])
    place_container_config_file = PathJoinSubstitution([ros_control_pkg_share, 'config', 'place_container_config.yaml'])
    navigate_to_address_config_file = PathJoinSubstitution([ros_control_pkg_share, 'config', 'navigate_to_address_config.yaml'])
    
    # Launch arguments
    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz = LaunchConfiguration('rviz')
    use_scara = LaunchConfiguration('use_scara')
    
    # Declare arguments
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation clock if true'
    )
    
    declare_rviz = DeclareLaunchArgument(
        'rviz',
        default_value='true',
        description='Launch RViz2 if true'
    )
    
    declare_use_scara = DeclareLaunchArgument(
        'use_scara',
        default_value='false',
        description='Attach SCARA arm to picker_frame if true'
    )
    
    # Process xacro file with ros2_control enabled
    robot_description_content = ParameterValue(
        Command([
            'xacro ', urdf_file,
            ' use_scara:=', use_scara,
            ' use_ros2_control:=true'
        ]),
        value_type=str
    )
    
    # Robot state publisher node
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description_content,
            'use_sim_time': use_sim_time
        }]
    )
    
    # ros2_control controller manager
    # Pass controller YAML files so controller_manager knows controller types
    controller_manager_node = Node(
        package='controller_manager',
        executable='ros2_control_node',
        parameters=[
            {'robot_description': robot_description_content},
            manip_controllers_file,
            scara_controllers_file
        ],
        output='screen'
    )
    
    # Spawn joint_state_broadcaster
    spawn_joint_state_broadcaster = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['joint_state_broadcaster', '--controller-manager', '/controller_manager'],
        output='screen'
    )

    # Spawn manipulator_controller (after joint_state_broadcaster)
    spawn_manipulator_controller = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['manipulator_controller', '--controller-manager', '/controller_manager'],
        output='screen'
    )

    # Spawn gripper_controller (after joint_state_broadcaster)
    spawn_gripper_controller = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['gripper_controller', '--controller-manager', '/controller_manager'],
        output='screen'
    )
    
    # Event handler: spawn manipulator_controller after joint_state_broadcaster is active
    delayed_manipulator_controller = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=spawn_joint_state_broadcaster,
            on_exit=[spawn_manipulator_controller]
        )
    )
    
    # Event handler: spawn gripper_controller after joint_state_broadcaster is active
    delayed_gripper_controller = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=spawn_joint_state_broadcaster,
            on_exit=[spawn_gripper_controller]
        )
    )
    
    # Spawn scara_controller (only when SCARA is enabled, after joint_state_broadcaster)
    spawn_scara_controller = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['scara_controller', '--controller-manager', '/controller_manager'],
        output='screen',
        condition=IfCondition(use_scara)
    )
    
    # Event handler: spawn scara_controller after joint_state_broadcaster is active
    delayed_scara_controller = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=spawn_joint_state_broadcaster,
            on_exit=[spawn_scara_controller]
        )
    )
    
    # MoveJointGroup action server node
    # We'll use OpaqueFunction to extract controller_joints at launch time
    # The node is delayed until controllers are spawned to ensure discovery works
    def create_move_joint_group_server(context):
        """Create move_joint_group_server node with extracted controller_joints"""
        try:
            use_scara_val = context.launch_configurations.get('use_scara', 'false') == 'true'
            use_sim_time_val = context.launch_configurations.get('use_sim_time', 'false') == 'true'

            # Resolve file paths
            manip_file = str(manip_controllers_file.perform(context))
            scara_file = str(scara_controllers_file.perform(context))
            config_file = str(move_joint_group_config_file.perform(context))

            print(f"[manipulator_bringup] Creating move_joint_group_server node...")
            print(f"[manipulator_bringup]   manip_file: {manip_file}")
            print(f"[manipulator_bringup]   scara_file: {scara_file}")
            print(f"[manipulator_bringup]   config_file: {config_file}")
            print(f"[manipulator_bringup]   use_scara: {use_scara_val}")

            # Extract controller joints from YAML files
            controller_joints = get_controller_joints(manip_file, scara_file, use_scara_val)

            # Log extracted controller joints for debugging
            if controller_joints:
                print(f"[manipulator_bringup] Extracted controller joints: {list(controller_joints.keys())}")
                for controller, joints in controller_joints.items():
                    print(f"[manipulator_bringup]   {controller}: {joints}")
            else:
                print("[manipulator_bringup] Warning: No controller joints extracted, move_joint_group_server will use discovery")

            # Serialize controller_joints to JSON (ROS2 doesn't support nested dict params)
            controller_joints_json = json.dumps(controller_joints)

            node = Node(
                package='ros_control',
                executable='move_joint_group_server.py',
                name='move_joint_group_server',
                output='screen',
                parameters=[
                    {'use_sim_time': use_sim_time_val},
                    {'controller_joints_json': controller_joints_json},
                    config_file
                ]
            )
            print(f"[manipulator_bringup] move_joint_group_server node created successfully")
            return [node]
        except Exception as e:
            print(f"[manipulator_bringup] ERROR creating move_joint_group_server: {e}")
            import traceback
            traceback.print_exc()
            # Return empty list so launch doesn't fail completely
            return []

    move_joint_group_server_action = OpaqueFunction(function=create_move_joint_group_server)

    # Event handler: start move_joint_group_server after manipulator_controller is spawned
    # This ensures controllers are active before the server tries to discover them
    delayed_move_joint_group_server = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=spawn_manipulator_controller,
            on_exit=[move_joint_group_server_action]
        )
    )

    # Gripper service node (provides /gripper/open and /gripper/close services)
    def create_gripper_service(context):
        """Create gripper_service node with config file parameters"""
        try:
            use_sim_time_val = context.launch_configurations.get('use_sim_time', 'false') == 'true'
            config_file = str(gripper_config_file.perform(context))

            print(f"[manipulator_bringup] Creating gripper_service node...")
            print(f"[manipulator_bringup]   config_file: {config_file}")

            node = Node(
                package='ros_control',
                executable='gripper_service.py',
                name='gripper_service',
                output='screen',
                parameters=[
                    {'use_sim_time': use_sim_time_val},
                    config_file
                ]
            )
            print(f"[manipulator_bringup] gripper_service node created successfully")
            return [node]
        except Exception as e:
            print(f"[manipulator_bringup] ERROR creating gripper_service: {e}")
            import traceback
            traceback.print_exc()
            return []

    gripper_service_action = OpaqueFunction(function=create_gripper_service)

    # Event handler: start gripper_service after gripper_controller is spawned
    delayed_gripper_service = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=spawn_gripper_controller,
            on_exit=[gripper_service_action]
        )
    )

    # GetContainer action server node
    def create_get_container_server(context):
        """Create get_container_server node with config file parameters"""
        try:
            use_sim_time_val = context.launch_configurations.get('use_sim_time', 'false') == 'true'
            config_file = str(get_container_config_file.perform(context))

            print(f"[manipulator_bringup] Creating get_container_server node...")
            print(f"[manipulator_bringup]   config_file: {config_file}")

            node = Node(
                package='ros_control',
                executable='get_container_server.py',
                name='get_container_server',
                output='screen',
                parameters=[
                    {'use_sim_time': use_sim_time_val},
                    config_file
                ]
            )
            print(f"[manipulator_bringup] get_container_server node created successfully")
            return [node]
        except Exception as e:
            print(f"[manipulator_bringup] ERROR creating get_container_server: {e}")
            import traceback
            traceback.print_exc()
            return []

    get_container_server_action = OpaqueFunction(function=create_get_container_server)

    # Event handler: start get_container_server after gripper_service is started
    # This ensures both gripper services and move_joint_group are available
    delayed_get_container_server = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=spawn_gripper_controller,
            on_exit=[get_container_server_action]
        )
    )

    # PlaceContainer action server node
    def create_place_container_server(context):
        """Create place_container_server node with config file parameters"""
        try:
            use_sim_time_val = context.launch_configurations.get('use_sim_time', 'false') == 'true'
            config_file = str(place_container_config_file.perform(context))

            print(f"[manipulator_bringup] Creating place_container_server node...")
            print(f"[manipulator_bringup]   config_file: {config_file}")

            node = Node(
                package='ros_control',
                executable='place_container_server.py',
                name='place_container_server',
                output='screen',
                parameters=[
                    {'use_sim_time': use_sim_time_val},
                    config_file
                ]
            )
            print(f"[manipulator_bringup] place_container_server node created successfully")
            return [node]
        except Exception as e:
            print(f"[manipulator_bringup] ERROR creating place_container_server: {e}")
            import traceback
            traceback.print_exc()
            return []

    place_container_server_action = OpaqueFunction(function=create_place_container_server)

    # Event handler: start place_container_server after gripper_controller is spawned
    delayed_place_container_server = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=spawn_gripper_controller,
            on_exit=[place_container_server_action]
        )
    )

    # NavigateToAddress action server node
    def create_navigate_to_address_server(context):
        """Create navigate_to_address_server node with config file parameters"""
        try:
            use_sim_time_val = context.launch_configurations.get('use_sim_time', 'false') == 'true'
            config_file = str(navigate_to_address_config_file.perform(context))

            print(f"[manipulator_bringup] Creating navigate_to_address_server node...")
            print(f"[manipulator_bringup]   config_file: {config_file}")

            node = Node(
                package='ros_control',
                executable='navigate_to_address_server.py',
                name='navigate_to_address_server',
                output='screen',
                parameters=[
                    {'use_sim_time': use_sim_time_val},
                    config_file
                ]
            )
            print(f"[manipulator_bringup] navigate_to_address_server node created successfully")
            return [node]
        except Exception as e:
            print(f"[manipulator_bringup] ERROR creating navigate_to_address_server: {e}")
            import traceback
            traceback.print_exc()
            return []

    navigate_to_address_server_action = OpaqueFunction(function=create_navigate_to_address_server)

    # Event handler: start navigate_to_address_server after manipulator_controller is spawned
    delayed_navigate_to_address_server = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=spawn_manipulator_controller,
            on_exit=[navigate_to_address_server_action]
        )
    )

    # RViz2 node (optional)
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config_file],
        parameters=[{'use_sim_time': use_sim_time}],
        condition=IfCondition(use_rviz)
    )
    
    return LaunchDescription([
        # Arguments
        declare_use_sim_time,
        declare_rviz,
        declare_use_scara,
        # Nodes
        robot_state_publisher_node,
        controller_manager_node,
        spawn_joint_state_broadcaster,
        delayed_manipulator_controller,
        delayed_gripper_controller,
        delayed_scara_controller,
        delayed_move_joint_group_server,  # Starts after manipulator_controller is spawned
        delayed_gripper_service,  # Starts after gripper_controller is spawned
        delayed_get_container_server,  # Starts after gripper_controller is spawned
        delayed_place_container_server,  # Starts after gripper_controller is spawned
        delayed_navigate_to_address_server,  # Starts after manipulator_controller is spawned
        rviz_node
    ])

