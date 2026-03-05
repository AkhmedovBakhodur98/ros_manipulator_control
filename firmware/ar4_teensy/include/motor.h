#pragma once

#include <AccelStepper.h>
#include "config.h"

/// Motor controller wrapping AccelStepper with position tracking.
/// One instance per joint.
class Motor {
public:
    Motor();

    /// Configure pins and motion parameters.
    /// Call once in setup().
    void init(uint8_t step_pin, uint8_t dir_pin, bool dir_invert,
              float max_speed, float accel);

    /// Command an absolute move to target_steps.
    /// Returns false if motor is busy with homing.
    bool moveTo(long target_steps);

    /// Internal move — bypasses homing guard (for use by homing code).
    void forceMoveTo(long target_steps);

    /// Get current position in steps.
    long currentPosition() const;

    /// Set current position (used after homing to establish reference).
    void setCurrentPosition(long pos);

    /// Returns true if motor is still moving toward target.
    bool isRunning() const;

    /// Remaining distance to target (sign indicates direction).
    long distanceToGo() const;

    /// Must be called every loop iteration to generate step pulses.
    void run();

    /// Emergency stop — decelerate to zero speed.
    void stop();

    /// Start jogging at given speed (steps/s). Sign = direction.
    /// Sets a far-away target and adjusts maxSpeed.
    void jogAt(float speed_steps_per_sec);

    /// Stop jogging — decelerate and restore original maxSpeed.
    void stopJog();

    /// Returns true if currently in jog mode.
    bool isJogging() const;

    /// Mark motor as homed / not homed.
    void setHomed(bool h);
    bool isHomed() const;

    /// Mark motor as currently homing (blocks MT commands).
    void setHoming(bool h);
    bool isHoming() const;

private:
    AccelStepper stepper_;
    bool homed_;
    bool homing_;
    bool jogging_;
    float saved_max_speed_;
};

/// Global motor array (indexed by motor_id)
extern Motor motors[NUM_JOINTS];

/// Initialize all motors. Call in setup().
void motors_init();
