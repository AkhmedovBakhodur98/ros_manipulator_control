#include "ar4_hardware_interface/teensy_protocol.hpp"

#include <sstream>

namespace ar4_hardware_interface {

TeensyProtocol::TeensyProtocol(SerialPort& port) : port_(port) {}

std::string TeensyProtocol::sendAndExpect(const std::string& cmd,
                                           const std::string& expected_prefix,
                                           int timeout_ms) {
    port_.writeLine(cmd);

    // Read lines until we get the expected response or timeout
    auto deadline = std::chrono::steady_clock::now()
                    + std::chrono::milliseconds(timeout_ms);

    while (std::chrono::steady_clock::now() < deadline) {
        auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(
            deadline - std::chrono::steady_clock::now());
        int read_timeout = std::max(1, static_cast<int>(remaining.count()));

        std::string line = port_.readLine(read_timeout);
        if (line.empty()) continue;

        // Skip informational lines (e.g. startup messages)
        if (line.substr(0, expected_prefix.size()) == expected_prefix) {
            return line;
        }
        // If we get an ERR response, return it so caller can detect failure
        if (line.substr(0, 3) == "ERR") {
            return line;
        }
    }

    return "";  // Timeout
}

bool TeensyProtocol::ping() {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string resp = sendAndExpect("PING", "PONG");
    return resp == "PONG";
}

bool TeensyProtocol::enable() {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string resp = sendAndExpect("EN", "OK");
    return resp == "OK";
}

bool TeensyProtocol::disable() {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string resp = sendAndExpect("DIS", "OK");
    return resp == "OK";
}

bool TeensyProtocol::moveTo(int id, long steps) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string cmd = "MT " + std::to_string(id) + " " + std::to_string(steps);
    std::string resp = sendAndExpect(cmd, "OK");
    return resp == "OK";
}

std::vector<long> TeensyProtocol::getPositions() {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string resp = sendAndExpect("GP", "POS");

    std::vector<long> positions;
    if (resp.empty() || resp.substr(0, 3) != "POS") {
        return positions;
    }

    // Parse "POS <s0> [s1 ...]"
    std::istringstream iss(resp.substr(3));
    long val;
    while (iss >> val) {
        positions.push_back(val);
    }

    return positions;
}

bool TeensyProtocol::home(int id, int timeout_ms) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string cmd = "HOME " + std::to_string(id);
    std::string expected = "HOMED " + std::to_string(id);
    std::string resp = sendAndExpect(cmd, "HOMED", timeout_ms);
    return resp == expected;
}

bool TeensyProtocol::stop() {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string resp = sendAndExpect("STOP", "OK");
    return resp == "OK";
}

std::mutex& TeensyProtocol::mutex() {
    return mutex_;
}

}  // namespace ar4_hardware_interface
