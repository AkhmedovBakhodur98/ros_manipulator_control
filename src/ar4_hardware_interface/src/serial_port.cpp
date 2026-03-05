#include "ar4_hardware_interface/serial_port.hpp"

#include <chrono>
#include <algorithm>
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <poll.h>
#include <cstring>

namespace ar4_hardware_interface {

SerialPort::SerialPort() : fd_(-1) {}

SerialPort::~SerialPort() {
    close();
}

bool SerialPort::open(const std::string& device, int baud_rate) {
    fd_ = ::open(device.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd_ < 0) {
        return false;
    }

    // Convert baud rate to termios constant
    speed_t speed;
    switch (baud_rate) {
        case 9600:   speed = B9600;   break;
        case 19200:  speed = B19200;  break;
        case 38400:  speed = B38400;  break;
        case 57600:  speed = B57600;  break;
        case 115200: speed = B115200; break;
        case 230400: speed = B230400; break;
        case 460800: speed = B460800; break;
        default:     speed = B115200; break;
    }

    struct termios tty;
    memset(&tty, 0, sizeof(tty));
    if (tcgetattr(fd_, &tty) != 0) {
        ::close(fd_);
        fd_ = -1;
        return false;
    }

    // Set baud rate
    cfsetospeed(&tty, speed);
    cfsetispeed(&tty, speed);

    // 8N1, no flow control
    tty.c_cflag &= ~PARENB;
    tty.c_cflag &= ~CSTOPB;
    tty.c_cflag &= ~CSIZE;
    tty.c_cflag |= CS8;
    tty.c_cflag &= ~CRTSCTS;
    tty.c_cflag |= CREAD | CLOCAL;

    // Raw mode (no canonical processing, no echo, no signals)
    tty.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
    tty.c_iflag &= ~(IXON | IXOFF | IXANY);
    tty.c_iflag &= ~(IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL);
    tty.c_oflag &= ~OPOST;

    // Non-blocking reads
    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 0;

    if (tcsetattr(fd_, TCSANOW, &tty) != 0) {
        ::close(fd_);
        fd_ = -1;
        return false;
    }

    // Flush any stale data
    tcflush(fd_, TCIOFLUSH);

    return true;
}

void SerialPort::close() {
    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
    }
}

bool SerialPort::isOpen() const {
    return fd_ >= 0;
}

bool SerialPort::writeLine(const std::string& line) {
    if (fd_ < 0) return false;

    std::string data = line + "\n";
    ssize_t written = ::write(fd_, data.c_str(), data.size());
    return written == static_cast<ssize_t>(data.size());
}

std::string SerialPort::readLine(int timeout_ms) {
    if (fd_ < 0) return "";

    std::string result;
    auto deadline = std::chrono::steady_clock::now()
                    + std::chrono::milliseconds(timeout_ms);

    while (std::chrono::steady_clock::now() < deadline) {
        struct pollfd pfd;
        pfd.fd = fd_;
        pfd.events = POLLIN;

        auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(
            deadline - std::chrono::steady_clock::now());
        int poll_ms = std::max(1, static_cast<int>(remaining.count()));

        int ret = poll(&pfd, 1, poll_ms);
        if (ret <= 0) continue;

        char c;
        ssize_t n = ::read(fd_, &c, 1);
        if (n <= 0) continue;

        if (c == '\n') {
            // Strip trailing \r if present
            if (!result.empty() && result.back() == '\r') {
                result.pop_back();
            }
            return result;
        }
        result += c;
    }

    return "";  // Timeout
}

}  // namespace ar4_hardware_interface
