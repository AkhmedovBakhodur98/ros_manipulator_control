#include <math.h>
#include "motor.h"

Motor motors[NUM_JOINTS];

Motor::Motor()
    : stepper_(AccelStepper::DRIVER, 0, 0),
      homed_(false),
      homing_(false),
      jogging_(false),
      saved_max_speed_(0.0f) {}

void Motor::init(uint8_t step_pin, uint8_t dir_pin, bool dir_invert,
                 float max_speed, float accel) {
    stepper_ = AccelStepper(AccelStepper::DRIVER, step_pin, dir_pin);
    stepper_.setPinsInverted(dir_invert, false, false);
    stepper_.setMinPulseWidth(50);   // 50us min pulse for MKS SERVO42C
    stepper_.enableOutputs();
    stepper_.setMaxSpeed(max_speed);
    stepper_.setAcceleration(accel);
    stepper_.setCurrentPosition(0);
    stepper_.moveTo(0);

    Serial.print("DBG motor init step=");
    Serial.print(step_pin);
    Serial.print(" dir=");
    Serial.print(dir_pin);
    Serial.print(" maxspd=");
    Serial.print(max_speed);
    Serial.print(" accel=");
    Serial.println(accel);
}

bool Motor::moveTo(long target_steps) {
    if (homing_ || jogging_) return false;
    stepper_.moveTo(target_steps);
    return true;
}

void Motor::forceMoveTo(long target_steps) {
    stepper_.moveTo(target_steps);
}

long Motor::currentPosition() const {
    return stepper_.currentPosition();
}

void Motor::setCurrentPosition(long pos) {
    stepper_.setCurrentPosition(pos);
}

bool Motor::isRunning() const {
    return stepper_.distanceToGo() != 0;
}

long Motor::distanceToGo() const {
    return stepper_.distanceToGo();
}

void Motor::run() {
    long before = stepper_.currentPosition();
    stepper_.run();
    long after = stepper_.currentPosition();

    // Auto-clear jogging state when deceleration completes
    if (jogging_ && stepper_.distanceToGo() == 0) {
        stepper_.setMaxSpeed(saved_max_speed_);
        jogging_ = false;
    }

    if (before != after) {
        static unsigned long last_step_dbg = 0;
        if (millis() - last_step_dbg >= 2000) {
            Serial.print("DBG stepping pos=");
            Serial.println(after);
            last_step_dbg = millis();
        }
    }
}

void Motor::stop() {
    stepper_.stop();
}

void Motor::jogAt(float speed_steps_per_sec) {
    if (!jogging_) {
        saved_max_speed_ = stepper_.maxSpeed();
    }
    jogging_ = true;

    float abs_speed = fabs(speed_steps_per_sec);
    if (abs_speed < 1.0f) {
        // Treat near-zero as stop
        stopJog();
        return;
    }

    stepper_.setMaxSpeed(abs_speed);
    long target = (speed_steps_per_sec > 0) ? 2000000000L : -2000000000L;
    stepper_.moveTo(target);
}

void Motor::stopJog() {
    if (!jogging_) return;
    stepper_.stop();  // Decelerate to zero
    // Restore maxSpeed after decel completes (handled in run())
    // But if already stopped, restore immediately
    if (stepper_.distanceToGo() == 0) {
        stepper_.setMaxSpeed(saved_max_speed_);
        jogging_ = false;
    }
}

bool Motor::isJogging() const {
    return jogging_;
}

void Motor::setHomed(bool h) {
    homed_ = h;
}

bool Motor::isHomed() const {
    return homed_;
}

void Motor::setHoming(bool h) {
    homing_ = h;
}

bool Motor::isHoming() const {
    return homing_;
}

// ---- Global init ----

void motors_init() {
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        motors[i].init(JOINTS[i].pins.step_pin, JOINTS[i].pins.dir_pin,
                       JOINTS[i].pins.dir_invert,
                       JOINTS[i].motion.max_speed, JOINTS[i].motion.accel);
        pinMode(JOINTS[i].pins.limit_pin, INPUT_PULLUP);
    }
}
