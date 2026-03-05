#pragma once

// ============================================================
// AR4 Teensy 4.1 Firmware Configuration
// ============================================================

// --- Serial ---
#ifndef SERIAL_BAUD
#define SERIAL_BAUD 115200
#endif

// --- Number of joints (expand as joints are added) ---
#define NUM_JOINTS 6

// Limit switch wiring: NC (normally closed) with INPUT_PULLUP
// HIGH = switch triggered (contact open), LOW = switch not triggered
#define LIMIT_TRIGGERED HIGH

// --- Per-joint configuration (pins, motion, homing) ---
#include "joints_config.h"
