#pragma once

#include <Arduino.h>

// Maximum length of a single command line
#define CMD_BUF_SIZE 64

// Error codes
#define ERR_UNKNOWN_CMD   1
#define ERR_BAD_ARGS      2
#define ERR_MOTOR_BUSY    3
#define ERR_INVALID_ID    4

/// Serial command parser and dispatcher.
/// Reads newline-terminated commands from Serial and dispatches them.
namespace Protocol {

/// Initialize the protocol (call in setup())
void init();

/// Poll for incoming commands (call in loop())
/// Reads characters, dispatches complete lines.
void poll();

/// Send a response line
void respond(const char* msg);

/// Send an error response
void respondError(int code, const char* msg);

}  // namespace Protocol
