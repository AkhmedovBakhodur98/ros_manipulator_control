#include "homing.h"
#include "config.h"
#include "motor.h"
#include <Arduino.h>

HomingSequence homing;

HomingSequence::HomingSequence()
    : state_(HomingState::IDLE),
      motor_id_(0),
      limit_pin_(0),
      backoff_target_(0) {}

bool HomingSequence::start(uint8_t motor_id) {
    if (state_ != HomingState::IDLE) return false;
    if (motor_id >= NUM_JOINTS) return false;

    motor_id_ = motor_id;
    limit_pin_ = JOINTS[motor_id_].pins.limit_pin;

    motors[motor_id_].setHoming(true);
    motors[motor_id_].setHomed(false);

    const auto& h = JOINTS[motor_id_].homing;

    Serial.print("DBG HOME start motor=");
    Serial.print(motor_id_);
    Serial.print(" limit_pin=");
    Serial.print(limit_pin_);
    Serial.print(" pin_state=");
    Serial.println(digitalRead(limit_pin_));

    // If switch is already triggered, start by backing off
    if (limitTriggered()) {
        Serial.println("DBG HOME switch already triggered, backing off");
        state_ = HomingState::BACKOFF;
        long cur = motors[motor_id_].currentPosition();
        backoff_target_ = cur - h.home_dir * h.backoff_steps;
        motors[motor_id_].setCurrentPosition(cur);
        motors[motor_id_].forceMoveTo(backoff_target_);
    } else {
        Serial.println("DBG HOME approaching fast...");
        state_ = HomingState::APPROACH_FAST;
        // Move a large distance toward the limit switch
        long target = motors[motor_id_].currentPosition()
                      + h.home_dir * JOINTS[motor_id_].steps_per_output_rev;
        motors[motor_id_].forceMoveTo(target);
    }

    return true;
}

bool HomingSequence::update() {
    if (state_ == HomingState::IDLE || state_ == HomingState::DONE) return false;

    const auto& h = JOINTS[motor_id_].homing;

    switch (state_) {
        case HomingState::APPROACH_FAST:
            if (limitTriggered()) {
                Serial.println("DBG HOME fast approach triggered, backing off");
                // Switch hit — instant stop (no deceleration overshoot)
                long cur_fast;
                cur_fast = motors[motor_id_].currentPosition();
                motors[motor_id_].setCurrentPosition(cur_fast);
                state_ = HomingState::BACKOFF;
                backoff_target_ = cur_fast - h.home_dir * h.backoff_steps;
                motors[motor_id_].forceMoveTo(backoff_target_);
            }
            break;

        case HomingState::BACKOFF:
            if (!motors[motor_id_].isRunning()) {
                Serial.println("DBG HOME backoff done, approaching slow...");
                // Backoff complete, approach slowly
                state_ = HomingState::APPROACH_SLOW;
                long target_slow;
                target_slow = motors[motor_id_].currentPosition()
                              + h.home_dir * h.backoff_steps * 2;
                motors[motor_id_].forceMoveTo(target_slow);
            }
            break;

        case HomingState::APPROACH_SLOW:
            if (limitTriggered()) {
                Serial.println("DBG HOME slow approach triggered, setting reference");
                // Precise home position found — instant stop
                motors[motor_id_].setCurrentPosition(motors[motor_id_].currentPosition());
                state_ = HomingState::SET_REFERENCE;
            }
            break;

        case HomingState::SET_REFERENCE: {
            if (!motors[motor_id_].isRunning()) {
                Serial.print("DBG HOME done, position set to ");
                Serial.println(h.home_offset_steps);
                // Set this position as the home offset
                motors[motor_id_].setCurrentPosition(h.home_offset_steps);
                motors[motor_id_].setHoming(false);
                motors[motor_id_].setHomed(true);
                state_ = HomingState::DONE;
                return true;  // Signal completion
            }
            break;
        }

        default:
            break;
    }

    return false;
}

bool HomingSequence::isActive() const {
    return state_ != HomingState::IDLE && state_ != HomingState::DONE;
}

uint8_t HomingSequence::motorId() const {
    return motor_id_;
}

bool HomingSequence::limitTriggered() const {
    return digitalRead(limit_pin_) == LIMIT_TRIGGERED;
}
