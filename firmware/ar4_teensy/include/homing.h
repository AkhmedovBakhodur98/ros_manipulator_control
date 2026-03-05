#pragma once

#include <Arduino.h>

/// Non-blocking homing state machine for a single motor.
///
/// Homing sequence:
///   1. APPROACH_FAST: Move toward limit switch at high speed
///   2. BACKOFF:       Move away from switch by a fixed number of steps
///   3. APPROACH_SLOW: Move toward switch again at low speed for precision
///   4. SET_REFERENCE:  Set position to home offset
///   5. DONE:          Homing complete
///
/// If the switch is already triggered at start, begins with BACKOFF.

enum class HomingState {
    IDLE,
    APPROACH_FAST,
    BACKOFF,
    APPROACH_SLOW,
    SET_REFERENCE,
    DONE
};

class HomingSequence {
public:
    HomingSequence();

    /// Start homing for the given motor id.
    /// Returns false if already homing or invalid id.
    bool start(uint8_t motor_id);

    /// Update the state machine. Call every loop().
    /// Returns true when homing has completed (DONE state entered this tick).
    bool update();

    /// Is a homing operation in progress?
    bool isActive() const;

    /// Get the motor id being homed.
    uint8_t motorId() const;

private:
    HomingState state_;
    uint8_t motor_id_;
    uint8_t limit_pin_;
    long backoff_target_;

    bool limitTriggered() const;
};

/// Global homing sequence instance
extern HomingSequence homing;
