#pragma once

#include <string>
#include <vector>
#include <mutex>

#include "ar4_hardware_interface/serial_port.hpp"

namespace ar4_hardware_interface {

/// Typed interface for the Teensy serial protocol.
/// Thread-safe: all methods lock a mutex around serial access.
class TeensyProtocol {
public:
    explicit TeensyProtocol(SerialPort& port);

    /// Send PING, expect PONG. Returns true on success.
    bool ping();

    /// Send EN (enable motors). Returns true on OK.
    bool enable();

    /// Send DIS (disable motors). Returns true on OK.
    bool disable();

    /// Send MT <id> <steps>. Returns true on OK.
    bool moveTo(int id, long steps);

    /// Send GP, parse POS response. Returns positions as vector of step counts.
    /// Returns empty vector on failure.
    std::vector<long> getPositions();

    /// Send HOME <id>, wait for HOMED response.
    /// Uses a longer timeout for the homing operation.
    /// Returns true if HOMED <id> received.
    bool home(int id, int timeout_ms = 30000);

    /// Send STOP. Returns true on OK.
    bool stop();

    /// Get mutex reference for external locking if needed.
    std::mutex& mutex();

private:
    SerialPort& port_;
    std::mutex mutex_;

    /// Send a command and wait for a specific expected response prefix.
    /// Returns the full response line, or empty string on timeout/mismatch.
    std::string sendAndExpect(const std::string& cmd, const std::string& expected_prefix,
                              int timeout_ms = 500);
};

}  // namespace ar4_hardware_interface
