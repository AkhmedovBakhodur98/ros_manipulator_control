#pragma once

#include <string>

namespace ar4_hardware_interface {

/// POSIX serial port wrapper for communicating with Teensy 4.1.
class SerialPort {
public:
    SerialPort();
    ~SerialPort();

    SerialPort(const SerialPort&) = delete;
    SerialPort& operator=(const SerialPort&) = delete;

    /// Open serial port with given device path and baud rate.
    /// Returns true on success.
    bool open(const std::string& device, int baud_rate);

    /// Close the serial port.
    void close();

    /// Returns true if the port is open.
    bool isOpen() const;

    /// Write a line (appends '\n').
    bool writeLine(const std::string& line);

    /// Read a line (strips '\n' and '\r').
    /// Returns empty string on timeout.
    std::string readLine(int timeout_ms = 50);

private:
    int fd_;
};

}  // namespace ar4_hardware_interface
