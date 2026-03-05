#include <Arduino.h>
#include "config.h"
#include "protocol.h"
#include "motor.h"
#include "homing.h"

void setup() {
    Serial.begin(SERIAL_BAUD);
    while (!Serial) {
        // Wait for USB serial connection (Teensy 4.1)
    }

    motors_init();
    Protocol::init();

    Serial.println("AR4 Teensy 4.1 ready");
}

void loop() {
    // Process incoming serial commands
    Protocol::poll();

    // Update homing state machine
    if (homing.isActive()) {
        if (homing.update()) {
            // Homing just completed — send response
            char buf[16];
            snprintf(buf, sizeof(buf), "HOMED %d", homing.motorId());
            Protocol::respond(buf);
        }
    }

    // Hard limit protection — instant stop if switch triggered outside homing,
    // but allow movement AWAY from the switch
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        if (!motors[i].isHoming()
            && digitalRead(JOINTS[i].pins.limit_pin) == LIMIT_TRIGGERED) {
            if (motors[i].isRunning()) {
                long dist = motors[i].distanceToGo();
                bool moving_toward_switch = (dist * JOINTS[i].homing.home_dir) > 0;
                if (moving_toward_switch) {
                    motors[i].setCurrentPosition(motors[i].currentPosition());
                    Serial.print("DBG LIMIT HIT motor=");
                    Serial.println(i);
                }
            }
        }
    }

    // Software position limits (after homing only)
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        if (JOINTS[i].limits.enabled && motors[i].isHomed() && !motors[i].isHoming()) {
            long pos = motors[i].currentPosition();
            if (pos <= JOINTS[i].limits.min_steps || pos >= JOINTS[i].limits.max_steps) {
                long dist = motors[i].distanceToGo();
                bool moving_toward_min = (dist < 0) && (pos <= JOINTS[i].limits.min_steps);
                bool moving_toward_max = (dist > 0) && (pos >= JOINTS[i].limits.max_steps);
                if (moving_toward_min || moving_toward_max) {
                    motors[i].setCurrentPosition(motors[i].currentPosition());
                    Serial.print("DBG SOFT_LIMIT motor=");
                    Serial.println(i);
                }
            }
        }
    }

    // Print position every 2 seconds while moving, and once when reached
    static unsigned long last_pos_print = 0;
    static bool was_running[NUM_JOINTS] = {false};
    if (millis() - last_pos_print >= 2000) {
        for (uint8_t i = 0; i < NUM_JOINTS; i++) {
            if (motors[i].isRunning()) {
                Serial.print("DBG motor=");
                Serial.print(i);
                Serial.print(" pos=");
                Serial.println(motors[i].currentPosition());
            }
        }
        last_pos_print = millis();
    }
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        if (was_running[i] && !motors[i].isRunning()) {
            Serial.print("DBG motor=");
            Serial.print(i);
            Serial.print(" REACHED pos=");
            Serial.println(motors[i].currentPosition());
        }
        was_running[i] = motors[i].isRunning();
    }

    // Generate step pulses for all motors
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        motors[i].run();
    }
}
