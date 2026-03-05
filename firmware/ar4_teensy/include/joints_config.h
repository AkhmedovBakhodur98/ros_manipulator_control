#pragma once

#include <stdint.h>

// ============================================================
// Per-joint configuration — edit this file when changing pins
// or adding new joints.
// ============================================================

struct JointPinConfig {
    uint8_t step_pin;
    uint8_t dir_pin;
    uint8_t limit_pin;
    bool    dir_invert;    // true = invert DIR signal via AccelStepper
};

struct JointMotionConfig {
    float max_speed;       // steps/sec
    float accel;           // steps/sec^2
};

struct JointHomingConfig {
    float speed_fast;      // steps/sec
    float speed_slow;      // steps/sec
    long  backoff_steps;
    int   home_dir;        // +1 or -1
    long  home_offset_steps;
};

struct JointLimitsConfig {
    long min_steps;     // software lower bound (reject/clamp below this)
    long max_steps;     // software upper bound (reject/clamp above this)
    bool enabled;       // false = no soft limits (e.g. J1 for now)
};

struct JointConfig {
    JointPinConfig    pins;
    JointMotionConfig motion;
    JointHomingConfig homing;
    JointLimitsConfig limits;
    long steps_per_output_rev;
    long start_position_steps;  // position (in steps) assumed when START command is received
};

constexpr JointConfig JOINTS[NUM_JOINTS] = {
    // J1: Base rotation
    // MKS SERVO42C (closed-loop) + NEMA 17 + Sumtor 42XG10 (40:1)
    {
        .pins   = { .step_pin = 0, .dir_pin = 1, .limit_pin = 29, .dir_invert = false },
        .motion = { .max_speed = 12000.0f, .accel = 6000.0f },
        .homing = { .speed_fast = 4000.0f, .speed_slow = 500.0f,
                    .backoff_steps = 800, .home_dir = 1, .home_offset_steps = 60444 },
        .limits = { .min_steps = 0, .max_steps = 0, .enabled = false },
        .steps_per_output_rev = 200L * 16 * 40,  // 128000
        .start_position_steps = 0,
    },

    // J2: Shoulder — NEMA 23 + MKS SERVO42C + 100:1 planetary
    // Limit switch at -42°, soft limits -44° to +90°
    {
        .pins   = { .step_pin = 2, .dir_pin = 3, .limit_pin = 30, .dir_invert = true },
        .motion = { .max_speed = 8000.0f, .accel = 4000.0f },
        .homing = { .speed_fast = 3000.0f, .speed_slow = 400.0f,
                    .backoff_steps = 800, .home_dir = -1, .home_offset_steps = -37333 },
        .limits = { .min_steps = -39111, .max_steps = 80000, .enabled = true },
        .steps_per_output_rev = 200L * 16 * 100,  // 320000
        .start_position_steps = 64889,  // 73°
    },

    // J3: Elbow — NEMA 17 + MKS SERVO42C + Sumtor 42XG50 (50:1)
    // Limit switch at -89°, soft limits -89° to +52°
    {
        .pins   = { .step_pin = 4, .dir_pin = 5, .limit_pin = 31, .dir_invert = false },  // PLACEHOLDER — set actual pins
        .motion = { .max_speed = 4000.0f, .accel = 2000.0f },
        .homing = { .speed_fast = 2000.0f, .speed_slow = 300.0f,
                    .backoff_steps = 800, .home_dir = -1, .home_offset_steps = -39556 },
        .limits = { .min_steps = -39556, .max_steps = 23111, .enabled = true },
        .steps_per_output_rev = 200L * 16 * 50,  // 160000
        .start_position_steps = -2800,  // -6.3°
    },

    // J4: Wrist roll — NEMA 11 (28hs5006a4) + MKS SERVO42C + 40:1 planetary
    {
        .pins   = { .step_pin = 6, .dir_pin = 7, .limit_pin = 26, .dir_invert = false },
        .motion = { .max_speed = 8000.0f, .accel = 4000.0f },
        .homing = { .speed_fast = 4000.0f, .speed_slow = 800.0f,
                    .backoff_steps = 800, .home_dir = -1, .home_offset_steps = -64000 },
        .limits = { .min_steps = -64000, .max_steps = 64000, .enabled = true },  // PLACEHOLDER — calibrate
        .steps_per_output_rev = 200L * 16 * 40,  // 128000
        .start_position_steps = 0,
    },

    // J5: Wrist pitch — NEMA 17 + MKS SERVO42C + T8 lead screw (no gear reducer)
    // Lead screw: T8×8mm lead, 200mm travel, linkage converts linear → rotation
    // Limit switch at +98° (positive end), range ±105°
    // PLACEHOLDER pins and steps — calibrate with real hardware
    {
        .pins   = { .step_pin = 8, .dir_pin = 9, .limit_pin = 27, .dir_invert = false },
        .motion = { .max_speed = 800.0f, .accel = 400.0f },
        .homing = { .speed_fast = 300.0f, .speed_slow = 100.0f,
                    .backoff_steps = 800, .home_dir = -1, .home_offset_steps = 5000 },  // PLACEHOLDER offset
        .limits = { .min_steps = -5500, .max_steps = 5500, .enabled = true },  // PLACEHOLDER — calibrate
        .steps_per_output_rev = 32000L,  // ~80mm travel on T8 lead screw (homing search distance)
        .start_position_steps = 1067,  // 12°
    },

    // J6: Wrist yaw — NEMA 14 (14hs2812-pg19) + MKS 35D RS485 + 19:1 built-in planetary
    // PLACEHOLDER pins — set actual pins before wiring
    {
        .pins   = { .step_pin = 10, .dir_pin = 11, .limit_pin = 28, .dir_invert = false },
        .motion = { .max_speed = 2000.0f, .accel = 1000.0f },
        .homing = { .speed_fast = 1000.0f, .speed_slow = 200.0f,
                    .backoff_steps = 800, .home_dir = 1, .home_offset_steps = 30400 },
        .limits = { .min_steps = -30400, .max_steps = 30400, .enabled = true },  // PLACEHOLDER — calibrate
        .steps_per_output_rev = 200L * 16 * 19,  // 60800
        .start_position_steps = 0,
    },
};
