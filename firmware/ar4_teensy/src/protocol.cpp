#include "protocol.h"
#include "config.h"
#include "motor.h"
#include "homing.h"

static char cmd_buf[CMD_BUF_SIZE];
static uint8_t cmd_pos = 0;

// Forward declaration
static void dispatch(char* line);

void Protocol::init() {
    cmd_pos = 0;
}

void Protocol::poll() {
    while (Serial.available()) {
        char c = Serial.read();

        if (c == '\n' || c == '\r') {
            if (cmd_pos > 0) {
                cmd_buf[cmd_pos] = '\0';
                dispatch(cmd_buf);
                cmd_pos = 0;
            }
        } else if (cmd_pos < CMD_BUF_SIZE - 1) {
            cmd_buf[cmd_pos++] = c;
        }
    }
}

void Protocol::respond(const char* msg) {
    Serial.println(msg);
}

void Protocol::respondError(int code, const char* msg) {
    Serial.print("ERR ");
    Serial.print(code);
    Serial.print(' ');
    Serial.println(msg);
}

// ---- Command handlers ----

static void handlePing() {
    Protocol::respond("PONG");
}

static void handleEnable() {
    // No-op: MKS SERVO42C self-enables; kept for protocol compatibility
    Protocol::respond("OK");
}

static void handleDisable() {
    // No-op: MKS SERVO42C self-enables; kept for protocol compatibility
    Protocol::respond("OK");
}

static void handleMoveTo(char* args) {
    // Parse: MT <id> <steps>
    int id;
    long steps;
    if (sscanf(args, "%d %ld", &id, &steps) != 2) {
        Protocol::respondError(ERR_BAD_ARGS, "MT requires <id> <steps>");
        return;
    }

    if (id < 0 || id >= NUM_JOINTS) {
        Protocol::respondError(ERR_INVALID_ID, "Invalid motor id");
        return;
    }

    if (motors[id].isHoming()) {
        Protocol::respondError(ERR_MOTOR_BUSY, "Motor is homing");
        return;
    }

    if (!motors[id].isHomed()) {
        Protocol::respondError(ERR_MOTOR_BUSY, "Motor not homed");
        return;
    }

    if (JOINTS[id].limits.enabled) {
        if (steps < JOINTS[id].limits.min_steps || steps > JOINTS[id].limits.max_steps) {
            Protocol::respondError(ERR_BAD_ARGS, "Position outside soft limits");
            return;
        }
    }

    motors[id].moveTo(steps);
    Protocol::respond("OK");
}

static void handleGetPositions() {
    Serial.print("POS");
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        Serial.print(' ');
        Serial.print(motors[i].currentPosition());
    }
    Serial.println();
}

static void handleHome(char* args) {
    int id;
    if (sscanf(args, "%d", &id) != 1) {
        Protocol::respondError(ERR_BAD_ARGS, "HOME requires <id>");
        return;
    }

    if (id < 0 || id >= NUM_JOINTS) {
        Protocol::respondError(ERR_INVALID_ID, "Invalid motor id");
        return;
    }

    if (!homing.start(static_cast<uint8_t>(id))) {
        Protocol::respondError(ERR_MOTOR_BUSY, "Already homing");
        return;
    }
    // Response ("HOMED <id>") is sent when homing completes in loop()
}

static void handleStart() {
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        if (motors[i].isHoming()) {
            Protocol::respondError(ERR_MOTOR_BUSY, "Motor is homing");
            return;
        }
    }
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        motors[i].setCurrentPosition(JOINTS[i].start_position_steps);
        motors[i].setHomed(true);
    }
    Protocol::respond("OK");
}

static void handleStop() {
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        motors[i].stop();
    }
    Protocol::respond("OK");
}

static void handleReadPin() {
    // Print limit switch state for all joints
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        Serial.print("J");
        Serial.print(i);
        Serial.print(" pin=");
        Serial.print(JOINTS[i].pins.limit_pin);
        Serial.print(" val=");
        Serial.print(digitalRead(JOINTS[i].pins.limit_pin));
        Serial.print(digitalRead(JOINTS[i].pins.limit_pin) == LIMIT_TRIGGERED
                     ? " TRIGGERED" : " open");
        Serial.println();
    }
}

// ---- Dispatcher ----

static void dispatch(char* line) {
    // Skip leading whitespace
    while (*line == ' ') line++;

    if (strncmp(line, "PING", 4) == 0) {
        handlePing();
    } else if (strncmp(line, "EN", 2) == 0 && (line[2] == '\0' || line[2] == ' ')) {
        handleEnable();
    } else if (strncmp(line, "DIS", 3) == 0 && (line[3] == '\0' || line[3] == ' ')) {
        handleDisable();
    } else if (strncmp(line, "MT ", 3) == 0) {
        handleMoveTo(line + 3);
    } else if (strncmp(line, "GP", 2) == 0) {
        handleGetPositions();
    } else if (strncmp(line, "HOME ", 5) == 0) {
        handleHome(line + 5);
    } else if (strncmp(line, "START", 5) == 0 && (line[5] == '\0' || line[5] == ' ')) {
        handleStart();
    } else if (strncmp(line, "STOP", 4) == 0) {
        handleStop();
    } else if (strncmp(line, "RDPIN", 5) == 0) {
        handleReadPin();
    } else if (strncmp(line, "TEST", 4) == 0) {
        // Manually toggle step pin 200 times (slow, visible on driver screen)
        // Usage: TEST [id]  (default: 0)
        int id = 0;
        if (line[4] == ' ') sscanf(line + 5, "%d", &id);
        if (id < 0 || id >= NUM_JOINTS) {
            Protocol::respondError(ERR_INVALID_ID, "Invalid motor id");
        } else {
            uint8_t step = JOINTS[id].pins.step_pin;
            uint8_t dir = JOINTS[id].pins.dir_pin;
            Serial.print("DBG toggling step=");
            Serial.print(step);
            Serial.print(" dir=");
            Serial.println(dir);
            digitalWrite(dir, HIGH);
            for (int i = 0; i < 200; i++) {
                digitalWrite(step, HIGH);
                delayMicroseconds(5000);
                digitalWrite(step, LOW);
                delayMicroseconds(5000);
            }
            Serial.println("DBG TEST done, 200 pulses sent");
        }
    } else if (strncmp(line, "SCAN", 4) == 0) {
        // Read all digital pins 0-41 to find which one changes
        for (uint8_t p = 0; p <= 41; p++) {
            Serial.print(p);
            Serial.print("=");
            Serial.print(digitalRead(p));
            Serial.print(" ");
        }
        Serial.println();
    } else {
        Serial.print("DBG unknown cmd: '");
        Serial.print(line);
        Serial.println("'");
        Protocol::respondError(ERR_UNKNOWN_CMD, "Unknown command");
    }
}
