cmake_minimum_required(VERSION 3.8)
project(ros_control)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find dependencies
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(control_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)

# Action definition
rosidl_generate_interfaces(${PROJECT_NAME}
  "action/MoveJointGroup.action"
  DEPENDENCIES
    sensor_msgs
    control_msgs
    std_msgs
    trajectory_msgs
    builtin_interfaces
)

# Install Python scripts
install(PROGRAMS
  src/move_joint_group_server.py
  DESTINATION lib/${PROJECT_NAME}
)

# Install config files
install(DIRECTORY
  config
  DESTINATION share/${PROJECT_NAME}
)

# Install launch files
install(DIRECTORY
  launch
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
