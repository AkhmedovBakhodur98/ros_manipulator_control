#include "ar4_hardware_interface/ar4_system.hpp"

#include <cmath>
#include <chrono>
#include <thread>

#include "hardware_interface/types/hardware_interface_type_values.hpp"
#include "pluginlib/class_list_macros.hpp"

namespace ar4_hardware_interface {

hardware_interface::CallbackReturn Ar4System::on_init(
    const hardware_interface::HardwareComponentInterfaceParams& params) {

    if (hardware_interface::SystemInterface::on_init(params) !=
        hardware_interface::CallbackReturn::SUCCESS) {
        return hardware_interface::CallbackReturn::ERROR;
    }

    // Parse hardware-level parameters
    const auto& hw_params = info_.hardware_parameters;
    auto it = hw_params.find("serial_port");
    serial_device_ = (it != hw_params.end()) ? it->second : "/dev/ttyACM0";

    it = hw_params.find("baud_rate");
    baud_rate_ = (it != hw_params.end()) ? std::stoi(it->second) : 115200;

    // Parse per-joint configuration
    for (const auto& joint : info_.joints) {
        JointConfig cfg;
        cfg.name = joint.name;

        const auto& jp = joint.parameters;

        auto jit = jp.find("motor_id");
        if (jit != jp.end()) cfg.motor_id = std::stoi(jit->second);

        jit = jp.find("steps_per_rev");
        if (jit != jp.end()) cfg.steps_per_rev = std::stoi(jit->second);

        jit = jp.find("gear_ratio");
        if (jit != jp.end()) cfg.gear_ratio = std::stod(jit->second);

        jit = jp.find("microsteps");
        if (jit != jp.end()) cfg.microsteps = std::stoi(jit->second);

        jit = jp.find("home_offset_rad");
        if (jit != jp.end()) cfg.home_offset_rad = std::stod(jit->second);

        joint_configs_.push_back(cfg);

        RCLCPP_INFO(get_logger(),
            "Joint '%s': motor_id=%d, steps/output_rev=%d, home_offset=%.3f rad",
            cfg.name.c_str(), cfg.motor_id, cfg.stepsPerOutputRev(),
            cfg.home_offset_rad);
    }

    prev_cmd_steps_.resize(joint_configs_.size(), 0);

    return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn Ar4System::on_configure(
    const rclcpp_lifecycle::State& /*previous_state*/) {

    RCLCPP_INFO(get_logger(), "Opening serial port: %s @ %d",
                serial_device_.c_str(), baud_rate_);

    if (!serial_port_.open(serial_device_, baud_rate_)) {
        RCLCPP_ERROR(get_logger(), "Failed to open serial port: %s",
                     serial_device_.c_str());
        return hardware_interface::CallbackReturn::ERROR;
    }

    protocol_ = std::make_unique<TeensyProtocol>(serial_port_);

    // Wait for Teensy to boot after USB connection
    std::this_thread::sleep_for(std::chrono::seconds(2));

    // Verify connection
    if (!protocol_->ping()) {
        RCLCPP_ERROR(get_logger(), "Teensy did not respond to PING");
        serial_port_.close();
        return hardware_interface::CallbackReturn::ERROR;
    }

    RCLCPP_INFO(get_logger(), "Teensy connected (PONG received)");

    // Create calibration service
    auto node = get_node();
    calibrate_service_ = node->create_service<std_srvs::srv::Trigger>(
        "/ar4_hardware/calibrate",
        std::bind(&Ar4System::calibrateCallback, this,
                  std::placeholders::_1, std::placeholders::_2));

    RCLCPP_INFO(get_logger(), "Calibration service available at /ar4_hardware/calibrate");

    return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn Ar4System::on_activate(
    const rclcpp_lifecycle::State& /*previous_state*/) {

    RCLCPP_INFO(get_logger(), "Activating: enabling motors");

    if (!protocol_->enable()) {
        RCLCPP_ERROR(get_logger(), "Failed to enable motors");
        return hardware_interface::CallbackReturn::ERROR;
    }

    // Initialize commands to current state (no jump on activation)
    for (size_t i = 0; i < joint_configs_.size(); i++) {
        const auto& cfg = joint_configs_[i];
        double pos = get_state(cfg.name + "/position");
        set_command(cfg.name + "/position", pos);
        prev_cmd_steps_[i] = cfg.radToSteps(pos);
    }

    RCLCPP_INFO(get_logger(), "Activated (homed=%s)",
                is_homed_.load() ? "true" : "false");

    return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn Ar4System::on_deactivate(
    const rclcpp_lifecycle::State& /*previous_state*/) {

    RCLCPP_INFO(get_logger(), "Deactivating: disabling motors");
    protocol_->disable();

    return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn Ar4System::on_cleanup(
    const rclcpp_lifecycle::State& /*previous_state*/) {

    RCLCPP_INFO(get_logger(), "Cleaning up: closing serial port");

    calibrate_service_.reset();
    protocol_.reset();
    serial_port_.close();
    is_homed_ = false;

    return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::return_type Ar4System::read(
    const rclcpp::Time& /*time*/, const rclcpp::Duration& period) {

    if (!is_homed_.load()) {
        // Before homing: report zero positions
        for (const auto& cfg : joint_configs_) {
            set_state(cfg.name + "/position", 0.0);
            set_state(cfg.name + "/velocity", 0.0);
        }
        return hardware_interface::return_type::OK;
    }

    auto positions = protocol_->getPositions();
    if (positions.empty()) {
        RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 1000,
                             "Failed to read positions from Teensy");
        return hardware_interface::return_type::OK;
    }

    for (size_t i = 0; i < joint_configs_.size(); i++) {
        const auto& cfg = joint_configs_[i];
        if (cfg.motor_id < static_cast<int>(positions.size())) {
            double new_pos = cfg.stepsToRad(positions[cfg.motor_id]);
            double old_pos = get_state(cfg.name + "/position");
            double dt = period.seconds();
            double velocity = (dt > 0.0) ? (new_pos - old_pos) / dt : 0.0;

            set_state(cfg.name + "/position", new_pos);
            set_state(cfg.name + "/velocity", velocity);
        }
    }

    return hardware_interface::return_type::OK;
}

hardware_interface::return_type Ar4System::write(
    const rclcpp::Time& /*time*/, const rclcpp::Duration& /*period*/) {

    if (!is_homed_.load()) {
        // Not homed — do not send movement commands
        return hardware_interface::return_type::OK;
    }

    for (size_t i = 0; i < joint_configs_.size(); i++) {
        const auto& cfg = joint_configs_[i];
        double cmd_rad = get_command(cfg.name + "/position");
        long cmd_steps = cfg.radToSteps(cmd_rad);

        // Only send if command changed
        if (cmd_steps != prev_cmd_steps_[i]) {
            protocol_->moveTo(cfg.motor_id, cmd_steps);
            prev_cmd_steps_[i] = cmd_steps;
        }
    }

    return hardware_interface::return_type::OK;
}

void Ar4System::calibrateCallback(
    const std::shared_ptr<std_srvs::srv::Trigger::Request> /*request*/,
    std::shared_ptr<std_srvs::srv::Trigger::Response> response) {

    RCLCPP_INFO(get_logger(), "Calibration requested — homing all joints");

    bool all_ok = true;
    for (const auto& cfg : joint_configs_) {
        RCLCPP_INFO(get_logger(), "Homing motor %d (%s)...",
                    cfg.motor_id, cfg.name.c_str());

        if (!protocol_->home(cfg.motor_id, 30000)) {
            RCLCPP_ERROR(get_logger(), "Homing failed for motor %d (%s)",
                         cfg.motor_id, cfg.name.c_str());
            all_ok = false;
            break;
        }

        RCLCPP_INFO(get_logger(), "Motor %d (%s) homed successfully",
                    cfg.motor_id, cfg.name.c_str());
    }

    if (all_ok) {
        is_homed_ = true;
        response->success = true;
        response->message = "All joints homed successfully";
        RCLCPP_INFO(get_logger(), "Calibration complete");
    } else {
        response->success = false;
        response->message = "Homing failed for one or more joints";
        RCLCPP_ERROR(get_logger(), "Calibration failed");
    }
}

}  // namespace ar4_hardware_interface

PLUGINLIB_EXPORT_CLASS(
    ar4_hardware_interface::Ar4System,
    hardware_interface::SystemInterface)
