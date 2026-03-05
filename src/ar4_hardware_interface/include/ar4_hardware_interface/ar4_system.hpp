#pragma once

#include <memory>
#include <string>
#include <vector>
#include <atomic>

#include "hardware_interface/system_interface.hpp"
#include "hardware_interface/types/hardware_component_interface_params.hpp"
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/float64_multi_array.hpp"
#include "std_srvs/srv/trigger.hpp"

#include "ar4_hardware_interface/serial_port.hpp"
#include "ar4_hardware_interface/teensy_protocol.hpp"

namespace ar4_hardware_interface {

/// Per-joint configuration parsed from URDF <param> tags.
struct JointConfig {
    std::string name;
    int motor_id = 0;
    int steps_per_rev = 200;
    double gear_ratio = 10.0;
    int microsteps = 16;
    double home_offset_rad = 0.0;

    /// Total steps per output revolution.
    int stepsPerOutputRev() const {
        return steps_per_rev * microsteps * static_cast<int>(gear_ratio);
    }

    /// Convert radians to motor steps.
    long radToSteps(double rad) const {
        return static_cast<long>(rad / (2.0 * M_PI) * stepsPerOutputRev());
    }

    /// Convert motor steps to radians.
    double stepsToRad(long steps) const {
        return static_cast<double>(steps) / stepsPerOutputRev() * 2.0 * M_PI;
    }
};

/// ros2_control SystemInterface for AR4 arm via Teensy 4.1.
///
/// Controls real motors through serial communication.
/// Homing is NOT automatic — requires explicit /ar4_hardware/calibrate service call.
class Ar4System : public hardware_interface::SystemInterface {
public:
    RCLCPP_SHARED_PTR_DEFINITIONS(Ar4System)

    // Lifecycle callbacks
    hardware_interface::CallbackReturn on_init(
        const hardware_interface::HardwareComponentInterfaceParams& params) override;

    hardware_interface::CallbackReturn on_configure(
        const rclcpp_lifecycle::State& previous_state) override;

    hardware_interface::CallbackReturn on_activate(
        const rclcpp_lifecycle::State& previous_state) override;

    hardware_interface::CallbackReturn on_deactivate(
        const rclcpp_lifecycle::State& previous_state) override;

    hardware_interface::CallbackReturn on_cleanup(
        const rclcpp_lifecycle::State& previous_state) override;

    // Real-time read/write
    hardware_interface::return_type read(
        const rclcpp::Time& time, const rclcpp::Duration& period) override;

    hardware_interface::return_type write(
        const rclcpp::Time& time, const rclcpp::Duration& period) override;

private:
    // Serial communication
    std::string serial_device_;
    int baud_rate_ = 115200;
    SerialPort serial_port_;
    std::unique_ptr<TeensyProtocol> protocol_;

    // Joint configuration
    std::vector<JointConfig> joint_configs_;

    // Homing state
    std::atomic<bool> is_homed_{false};

    // Calibration service
    rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr calibrate_service_;

    void calibrateCallback(
        const std::shared_ptr<std_srvs::srv::Trigger::Request> request,
        std::shared_ptr<std_srvs::srv::Trigger::Response> response);

    // Start service (skip homing, mark at start positions)
    rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr start_service_;

    void startCallback(
        const std::shared_ptr<std_srvs::srv::Trigger::Request> request,
        std::shared_ptr<std_srvs::srv::Trigger::Response> response);

    // Jog control
    rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr jog_subscription_;
    std::atomic<bool> is_jogging_{false};
    rclcpp::Time last_jog_time_;

    void jogCallback(const std_msgs::msg::Float64MultiArray::SharedPtr msg);

    // Previous commanded positions (for skip-if-unchanged optimization)
    std::vector<long> prev_cmd_steps_;
};

}  // namespace ar4_hardware_interface
