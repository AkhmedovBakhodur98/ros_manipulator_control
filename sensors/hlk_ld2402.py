#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        HLK-LD2402 Radar Sensor                             ║
║              24 ГГц радарный датчик присутствия человека                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

Описание:
    Этот файл реализует взаимодействие с датчиком HLK-LD2402 от Hi-Link
    по протоколу UART. Датчик работает на частоте 24 ГГц и предназначен для
    обнаружения присутствия человека (движение, микродвижение, статическое
    присутствие) на расстоянии до 10 метров с точностью ±15 см.

Функциональность:
    1. Подключение к датчику через последовательный порт (USB-UART адаптер).
    2. Чтение данных в реальном времени:
       - расстояние до обнаруженного объекта (в сантиметрах)
       - статус обнаружения (через текстовые сообщения: distance / OFF)
    3. Конфигурация датчика через командный протокол:
       - чтение версии прошивки (команда 0x0000)
       - чтение серийного номера (команды 0x0016 hex / 0x0011 строка)
       - чтение и установка параметров (команды 0x0008 / 0x0007)
       - сохранение параметров в flash (команда 0x00FD)
       - переключение режима вывода (команда 0x0012)
       - автонастройка усиления (команда 0x00EE)
    4. Автокалибровка порогов обнаружения (команда 0x0009):
       Требует 6 байт данных — коэффициенты генерации порогов:
         - 2 байта: коэффициент триггера (×10, диапазон 0x000A-0x00C8)
         - 2 байта: коэффициент удержания (×10)
         - 2 байта: коэффициент микродвижения (×10)
       По умолчанию: триггер=3.0, удержание=2.0, микродвижение=3.0
    5. Программная фильтрация данных:
       - медианный фильтр для сглаживания показаний
       - ограничение макс./мин. дистанции (отсечение стен)
    6. Инженерный режим (команда 0x0012):
       Фреймы данных: [F4 F3 F2 F1] [LEN 2B] [RESULT 1B] [DIST 2B]
                      [MOTION_ENERGY 64B] [MICRO_ENERGY 64B] [F8 F7 F6 F5]
       Показывает энергию по каждому из 32 гейтов (16 движение + 16 микродвижение).

Параметры датчика (таблица 5-5 даташита V1.08):
    ID          Описание                    Диапазон
    ─────────────────────────────────────────────────────────────────
    0x0001      Макс. дистанция             7-100 (в единицах 0.1м, т.е. 100 = 10м)
    0x0004      Таймаут исчезновения цели   0-65535 (секунды)
    0x0005      Помехи питания (только чт.) 0=не проверялось, 1=нет, 2=есть
    0x0010-0x001F  Пороги движения (16 гейтов)    0-95 (квадрат модуля)
    0x0030-0x003F  Пороги микродвижения (16 гейтов) 0-95 (квадрат модуля)

    Формула пересчёта порогов:
        UI_dB = 10 × log10(serial_value)
        serial_value = 10^(UI_dB / 10)

Формат данных датчика:
    Нормальный режим (текст ASCII):
        distance:201\\r\\n    — расстояние до цели в сантиметрах
        OFF\\r\\n             — нет обнаружения

    Инженерный режим (бинарные фреймы):
        [F4 F3 F2 F1] [LEN 2B] [DETECT 1B] [DIST 2B] [32×4B энергия] [F8 F7 F6 F5]

    Командный протокол:
        Запрос:  [FD FC FB FA] [LEN 2B] [CMD 2B] [DATA] [04 03 02 01]
        Ответ:   [FD FC FB FA] [LEN 2B] [CMD|0x100 2B] [STATUS 2B] [DATA] [04 03 02 01]

Подключение:
    HLK-LD2402          USB-UART адаптер (CP2102 / CH340 / FT232)
    ─────────────────────────────────────────────────────────────
    VCC (3.3-5V) ──────→ VCC (3.3V или 5V)
    GND          ──────→ GND
    TX           ──────→ RX
    RX           ──────→ TX

Параметры UART:
    - Скорость:       115200 бод (по умолчанию)
    - Биты данных:    8
    - Стоп-биты:      1
    - Чётность:       нет

Прошивка (протестировано): v3.3.5
Даташит: HLK-LD2402 用户手册 V1.08

Зависимости:
    pip install pyserial

Использование:
    python3 hlk_ld2402.py                          # чтение данных
    python3 hlk_ld2402.py --info                   # информация о датчике
    python3 hlk_ld2402.py --calibrate              # автокалибровка (ПРАВИЛЬНАЯ!)
    python3 hlk_ld2402.py --calibrate --trigger-coeff 3.0 --hold-coeff 2.0 --micro-coeff 3.0
    python3 hlk_ld2402.py --engineering            # инженерный режим
    python3 hlk_ld2402.py --auto-gain              # автонастройка усиления
    python3 hlk_ld2402.py --dump-params            # все параметры
    python3 hlk_ld2402.py --set-param 0x0001 85    # установить макс. дистанцию
    python3 hlk_ld2402.py --factory-reset          # сброс к заводским
    python3 hlk_ld2402.py --max-dist 120 --avg 5   # фильтрация
    python3 hlk_ld2402.py --debug                  # подробный TX/RX
"""

import serial
import struct
import time
import argparse
import sys
import re
import statistics
import math
from collections import deque
from enum import IntEnum
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# Константы протокола
# ═══════════════════════════════════════════════════════════════════════════════

# Заголовки и окончания фреймов (командный протокол)
CMD_HEADER = bytes([0xFD, 0xFC, 0xFB, 0xFA])
CMD_FOOTER = bytes([0x04, 0x03, 0x02, 0x01])

# Заголовки и окончания фреймов (инженерный режим)
ENG_HEADER = bytes([0xF4, 0xF3, 0xF2, 0xF1])
ENG_FOOTER = bytes([0xF8, 0xF7, 0xF6, 0xF5])

# Настройки UART по умолчанию
DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 2

# Регулярное выражение для парсинга текстовых данных датчика
RE_DISTANCE = re.compile(r'distance:(\d+)')

# Количество гейтов (дистанционных зон)
NUM_GATES = 16
GATE_SIZE_CM = 70  # Один гейт = 70 см


class Command(IntEnum):
    """
    Коды команд протокола HLK-LD2402 (даташит V1.08).

    В ACK-ответе код команды = отправленный_код | 0x0100.
    Например: отправили 0x0000 → в ACK придёт 0x0100.
    """
    READ_FIRMWARE_VERSION = 0x0000   # Чтение версии прошивки
    ENABLE_CONFIG = 0x00FF           # Включить режим конфигурации (данные: 0x0001)
    END_CONFIG = 0x00FE              # Выйти из режима конфигурации
    SAVE_TO_FLASH = 0x00FD           # Сохранить параметры в flash (v3.3.2+)
    READ_SERIAL_HEX = 0x0016        # Чтение серийного номера HEX (v3.3.5+)
    READ_SERIAL_STR = 0x0011        # Чтение серийного номера (строка)
    READ_PARAMETERS = 0x0008        # Чтение параметров (данные: N × 2B param_id)
    SET_PARAMETERS = 0x0007         # Установка параметров (данные: N × (2B id + 4B value))
    SET_OUTPUT_MODE = 0x0012        # Режим вывода (данные: 2B cmd_val + 4B mode)
    START_AUTO_THRESHOLD = 0x0009   # Автокалибровка (данные: 6B коэффициенты)
    QUERY_AUTO_THRESHOLD = 0x000A   # Запрос прогресса автокалибровки
    REPORT_INTERFERENCE = 0x0014    # Датчик сообщает о помехах при калибровке
    FACTORY_RESET = 0x0060          # Сброс к заводским настройкам
    AUTO_GAIN_ADJUST = 0x00EE       # Автонастройка усиления (v3.3.5+)
    AUTO_GAIN_DONE = 0x00F0         # Ответ: автонастройка усиления завершена


class OutputMode(IntEnum):
    """Режимы вывода данных (параметр для команды 0x0012)."""
    NORMAL = 0x00000064       # Обычный: distance:XXX (текст)
    ENGINEERING = 0x00000004  # Инженерный: бинарные фреймы с энергией по гейтам


# Параметры датчика (таблица 5-5 даташита)
PARAM_NAMES = {
    0x0000: ("Мин. гейт/дистанция", "внутренний параметр"),
    0x0001: ("Макс. дистанция", "7-100 (единицы 0.1м, т.е. 85=8.5м)"),
    0x0002: ("Режим вывода", "внутренний параметр"),
    0x0003: ("Внутренний параметр", ""),
    0x0004: ("Таймаут исчезновения цели", "0-65535 секунд"),
    0x0005: ("Помехи питания (только чт.)", "0=не проверено, 1=нет, 2=есть"),
}

# Добавляем пороги движения (0x0010-0x001F)
for _g in range(NUM_GATES):
    _id = 0x0010 + _g
    PARAM_NAMES[_id] = (
        f"Порог движения гейт {_g}",
        f"зона {_g * GATE_SIZE_CM}-{(_g + 1) * GATE_SIZE_CM} см"
    )

# Добавляем пороги микродвижения (0x0030-0x003F)
for _g in range(NUM_GATES):
    _id = 0x0030 + _g
    PARAM_NAMES[_id] = (
        f"Порог микродвиж. гейт {_g}",
        f"зона {_g * GATE_SIZE_CM}-{(_g + 1) * GATE_SIZE_CM} см"
    )

# Специальный параметр для сохранения
PARAM_NAMES[0x003F] = ("Параметр сохранения (0x3F)", "нужен для掉电保存")


def threshold_to_db(value: int) -> float:
    """Пересчитать серийное значение порога в дБ (для отображения в UI)."""
    if value <= 0:
        return 0.0
    return 10.0 * math.log10(value)


def db_to_threshold(db_value: float) -> int:
    """Пересчитать дБ (UI) в серийное значение порога."""
    return int(10 ** (db_value / 10.0))


# ═══════════════════════════════════════════════════════════════════════════════
# Класс датчика
# ═══════════════════════════════════════════════════════════════════════════════

class HlkLd2402:
    """
    Драйвер для взаимодействия с датчиком HLK-LD2402 по UART.

    Позволяет читать данные о расстоянии и присутствии, настраивать
    параметры и проводить автокалибровку.
    """

    def __init__(self, port: str = DEFAULT_PORT, baudrate: int = DEFAULT_BAUD,
                 timeout: float = DEFAULT_TIMEOUT, debug: bool = False):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.debug = debug
        self.serial: Optional[serial.Serial] = None

    def connect(self) -> bool:
        """Открыть соединение с датчиком."""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
            )
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            print(f"[OK] Подключено к {self.port} @ {self.baudrate} бод")
            return True
        except serial.SerialException as e:
            print(f"[ОШИБКА] Не удалось подключиться к {self.port}: {e}")
            return False

    def disconnect(self):
        """Закрыть соединение с датчиком."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            print(f"[OK] Отключено от {self.port}")

    # ───────────────────────────────────────────────────────────────────────
    # Низкоуровневый протокол
    # ───────────────────────────────────────────────────────────────────────

    def _build_command_frame(self, command: int, data: bytes = b'') -> bytes:
        """
        Собрать командный фрейм.
        Формат: [FD FC FB FA] [LENGTH 2B] [COMMAND 2B] [DATA nB] [04 03 02 01]
        """
        cmd_bytes = struct.pack('<H', command)
        payload = cmd_bytes + data
        length = struct.pack('<H', len(payload))
        return CMD_HEADER + length + payload + CMD_FOOTER

    def _send_command(self, command: int, data: bytes = b'',
                      wait: float = 0.15) -> Optional[bytes]:
        """Отправить команду датчику и прочитать ответ."""
        if not self.serial or not self.serial.is_open:
            print("[ОШИБКА] Нет подключения к датчику")
            return None

        frame = self._build_command_frame(command, data)

        if self.debug:
            print(f"  [TX] {frame.hex(' ')}")

        self.serial.reset_input_buffer()
        self.serial.write(frame)
        time.sleep(wait)

        response = self.serial.read(512)

        if self.debug:
            if response:
                print(f"  [RX] {response.hex(' ')}")
                ascii_repr = ''.join(
                    chr(b) if 32 <= b < 127 else '.' for b in response
                )
                print(f"  [AS] {ascii_repr}")
            else:
                print("  [RX] (пустой ответ)")

        return response if response else None

    def _parse_ack(self, response: bytes) -> Optional[dict]:
        """
        Разобрать ACK-ответ от датчика.
        Формат: [FD FC FB FA] [LEN 2B] [CMD|0x0100 2B] [STATUS 2B] [DATA...] [04 03 02 01]
        """
        if not response or len(response) < 10:
            return None

        idx = response.find(CMD_HEADER)
        if idx == -1:
            return None

        resp = response[idx:]
        if len(resp) < 10:
            return None

        length = struct.unpack_from('<H', resp, 4)[0]
        frame_end = 6 + length
        if len(resp) < frame_end + 4:
            return None

        if resp[frame_end:frame_end + 4] != CMD_FOOTER:
            return None

        cmd = struct.unpack_from('<H', resp, 6)[0]
        status = struct.unpack_from('<H', resp, 8)[0] if length >= 4 else None
        payload = resp[10:frame_end] if length > 4 else b''

        return {
            'command': cmd,
            'status': status,
            'data': payload,
        }

    # ───────────────────────────────────────────────────────────────────────
    # Команды конфигурации
    # ───────────────────────────────────────────────────────────────────────

    def _drain_input(self):
        """Сбросить входной буфер — прочитать и выбросить все данные."""
        if not self.serial or not self.serial.is_open:
            return
        self.serial.reset_input_buffer()
        time.sleep(0.1)
        while self.serial.in_waiting > 0:
            self.serial.read(self.serial.in_waiting)
            time.sleep(0.05)

    def enable_config(self) -> bool:
        """
        Включить режим конфигурации (команда 0x00FF, данные 0x0001).
        Делает до 3 попыток с увеличивающимся таймаутом.
        """
        self._drain_input()
        if self.debug:
            print("  [PRE] Отправляем end_config на случай зависания...")
        self.serial.write(self._build_command_frame(Command.END_CONFIG))
        time.sleep(0.3)
        self._drain_input()

        for attempt in range(3):
            self._drain_input()
            resp = self._send_command(
                Command.ENABLE_CONFIG, b'\x01\x00',
                wait=0.3 + attempt * 0.3
            )

            if not resp and self.serial:
                time.sleep(0.3)
                extra = self.serial.read(512)
                if extra:
                    resp = extra
                    if self.debug:
                        print(f"  [RX+] {extra.hex(' ')}")

            ack = self._parse_ack(resp) if resp else None
            if ack and ack['status'] == 0:
                print("[OK] Режим конфигурации включён")
                return True

            if self.debug and attempt < 2:
                print(f"  [RETRY] Попытка {attempt + 2}/3...")
            time.sleep(0.5)

        print("[ОШИБКА] Не удалось войти в режим конфигурации (3 попытки)")
        print("  Попробуйте: передёрнуть питание датчика")
        return False

    def end_config(self) -> bool:
        """Выйти из режима конфигурации (команда 0x00FE)."""
        resp = self._send_command(Command.END_CONFIG)
        ack = self._parse_ack(resp) if resp else None
        if ack and ack['status'] == 0:
            print("[OK] Режим конфигурации завершён")
            return True
        print("[ПРЕДУПРЕЖДЕНИЕ] Не удалось выйти из режима конфигурации")
        return False

    def save_to_flash(self) -> bool:
        """
        Сохранить параметры в энергонезависимую память (команда 0x00FD).
        Вызывать ПОСЛЕ записи параметров и ДО end_config.
        Поддерживается в v3.3.2 и выше.
        """
        resp = self._send_command(Command.SAVE_TO_FLASH, wait=0.3)
        ack = self._parse_ack(resp) if resp else None
        if ack and ack['status'] == 0:
            if self.debug:
                print("  [OK] Параметры сохранены в flash")
            return True
        if self.debug:
            print("  [ПРЕДУПРЕЖДЕНИЕ] Не удалось сохранить в flash")
        return False

    # ───────────────────────────────────────────────────────────────────────
    # Чтение информации
    # ───────────────────────────────────────────────────────────────────────

    def read_firmware_version(self) -> Optional[str]:
        """Прочитать версию прошивки (команда 0x0000)."""
        resp = self._send_command(Command.READ_FIRMWARE_VERSION)
        ack = self._parse_ack(resp) if resp else None
        if ack and ack['status'] == 0 and ack['data']:
            raw = ack['data']
            if len(raw) >= 3:
                str_len = struct.unpack_from('<H', raw, 0)[0]
                version = raw[2:2 + str_len].decode('ascii', errors='replace')
                return version
            return raw.decode('ascii', errors='replace').strip('\x00')
        return None

    def read_serial_number(self) -> Optional[str]:
        """Прочитать серийный номер (строка, команда 0x0011)."""
        resp = self._send_command(Command.READ_SERIAL_STR)
        ack = self._parse_ack(resp) if resp else None
        if ack and ack['status'] == 0:
            if ack['data'] and len(ack['data']) > 2:
                sn_len = struct.unpack_from('<H', ack['data'], 0)[0]
                sn = ack['data'][2:2 + sn_len].decode('ascii', errors='replace')
                return sn if sn.strip('\x00') else "(пустой)"
            return "(пустой — серийный номер не записан)"
        return None

    def read_serial_hex(self) -> Optional[str]:
        """Прочитать серийный номер HEX (команда 0x0016, v3.3.5+)."""
        resp = self._send_command(Command.READ_SERIAL_HEX)
        ack = self._parse_ack(resp) if resp else None
        if ack and ack['status'] == 0:
            if ack['data'] and len(ack['data']) > 2:
                sn_len = struct.unpack_from('<H', ack['data'], 0)[0]
                sn_bytes = ack['data'][2:2 + sn_len]
                return sn_bytes.hex(' ')
            return "(пустой)"
        return None

    # ───────────────────────────────────────────────────────────────────────
    # Управление параметрами
    # ───────────────────────────────────────────────────────────────────────

    def read_param_by_index(self, index: int) -> Optional[int]:
        """
        Прочитать параметр по индексу (команда 0x0008).
        Формат запроса: [param_id 2B]
        Формат ответа:  [param_value 4B]
        """
        data = struct.pack('<H', index)
        resp = self._send_command(Command.READ_PARAMETERS, data, wait=0.2)
        ack = self._parse_ack(resp) if resp else None
        if ack and ack['status'] == 0 and ack['data'] and len(ack['data']) >= 4:
            return struct.unpack_from('<I', ack['data'])[0]
        return None

    def set_param_by_index(self, index: int, value: int) -> bool:
        """
        Установить параметр по индексу (команда 0x0007).
        Формат: [param_id 2B] [param_value 4B]
        """
        data = struct.pack('<HI', index, value)
        resp = self._send_command(Command.SET_PARAMETERS, data, wait=0.2)
        ack = self._parse_ack(resp) if resp else None
        return bool(ack and ack['status'] == 0)

    def set_output_mode(self, mode: OutputMode) -> bool:
        """
        Установить режим вывода данных (команда 0x0012).

        Формат по даташиту: [cmd_value 2B = 0x0000] [param_value 4B]
          - 0x00000064 = нормальный (distance:XXX текст)
          - 0x00000004 = инженерный (бинарные фреймы с энергией по гейтам)
        """
        # Даташит: команда 0x0012, данные = 0x0000 (2B) + mode (4B)
        data = struct.pack('<HI', 0x0000, int(mode))
        resp = self._send_command(Command.SET_OUTPUT_MODE, data)
        ack = self._parse_ack(resp) if resp else None
        mode_name = "инженерный" if mode == OutputMode.ENGINEERING else "нормальный"
        if ack and ack['status'] == 0:
            print(f"[OK] Режим вывода: {mode_name}")
            return True
        print(f"[ОШИБКА] Не удалось переключить режим на {mode_name}")
        return False

    def dump_all_params(self):
        """Прочитать и показать все параметры датчика."""
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║        ПАРАМЕТРЫ ДАТЧИКА HLK-LD2402              ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

        if not self.enable_config():
            return

        # Все параметры для чтения
        indices_to_read = sorted(set(
            list(range(0x0000, 0x0006)) +      # Общие
            list(range(0x0010, 0x0020)) +       # Пороги движения
            list(range(0x0030, 0x0040)) +       # Пороги микродвижения
            [0x003F]                             # Параметр сохранения
        ))

        print(f"  {'ID':<8s}  {'Значение':>10s}  {'HEX':>12s}  {'дБ':>8s}  {'Описание'}")
        print("  " + "─" * 80)

        for idx in indices_to_read:
            val = self.read_param_by_index(idx)
            if val is None:
                continue
            # Пропускаем 0x7FFFFFFF (не определено)
            if val == 0x7FFFFFFF and idx not in PARAM_NAMES:
                continue

            name_info = PARAM_NAMES.get(idx)
            name = name_info[0] if name_info else "?"
            note = name_info[1] if name_info else ""

            # Для порогов показываем дБ
            db_str = ""
            is_threshold = (0x0010 <= idx <= 0x001F) or (0x0030 <= idx <= 0x003F)
            if is_threshold and val > 0:
                db_str = f"{threshold_to_db(val):>6.1f} дБ"

            # Для макс. дистанции показываем метры
            extra = ""
            if idx == 0x0001:
                extra = f" = {val * 0.1:.1f} м"

            print(
                f"  0x{idx:04X}  {val:>10d}  0x{val:08X}  "
                f"{db_str:>8s}  {name}{extra}"
            )
            if note:
                print(f"  {'':8s}  {'':>10s}  {'':>12s}  {'':>8s}  └─ {note}")
            time.sleep(0.05)

        print()
        self.end_config()

    def set_param_interactive(self, index: int, value: int):
        """Установить параметр с проверкой + сохранить в flash."""
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║        УСТАНОВКА ПАРАМЕТРА ДАТЧИКА               ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

        if not self.enable_config():
            return

        # Читаем текущее значение
        old_val = self.read_param_by_index(index)
        name = PARAM_NAMES.get(index, ("Неизвестный параметр", ""))[0]
        print(f"  Параметр:   0x{index:04X} ({name})")
        if old_val is not None:
            print(f"  Текущее:    {old_val} (0x{old_val:08X})")
        else:
            print(f"  Текущее:    не удалось прочитать")

        print(f"  Новое:      {value} (0x{value:08X})")
        print()

        # Записываем
        ok = self.set_param_by_index(index, value)
        if ok:
            print("[OK] Параметр записан")
        else:
            print("[ОШИБКА] Не удалось записать параметр")
            self.end_config()
            return

        # Для сохранения в flash нужно также записать 0x003F
        # (даташит 5.5: "固件中只有识别到参数名为0x003F后才会保存下来")
        if index != 0x003F:
            # Читаем текущее значение 0x003F и перезаписываем его
            val_3f = self.read_param_by_index(0x003F)
            if val_3f is not None:
                self.set_param_by_index(0x003F, val_3f)
                if self.debug:
                    print(f"  [OK] 0x003F перезаписан ({val_3f})")

        # Сохраняем в flash
        self.save_to_flash()

        # Проверяем
        time.sleep(0.2)
        new_val = self.read_param_by_index(index)
        if new_val is not None:
            if new_val == value:
                print(f"[OK] Проверка: значение = {new_val} ✓")
            else:
                print(f"[ПРЕДУПРЕЖДЕНИЕ] Проверка: значение = {new_val} "
                      f"(ожидалось {value})")
        else:
            print("[ПРЕДУПРЕЖДЕНИЕ] Не удалось проверить")

        self.end_config()

    # ───────────────────────────────────────────────────────────────────────
    # Сброс к заводским настройкам
    # ───────────────────────────────────────────────────────────────────────

    def factory_reset(self) -> bool:
        """Сброс датчика к заводским настройкам (команда 0x0060)."""
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║      СБРОС К ЗАВОДСКИМ НАСТРОЙКАМ               ║")
        print("╠══════════════════════════════════════════════════╣")
        print("║  ⚠️  Все параметры и пороги будут сброшены!      ║")
        print("║  После сброса потребуется повторная калибровка.  ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

        if not self.enable_config():
            return False

        for attempt in range(3):
            self._drain_input()
            resp = self._send_command(
                Command.FACTORY_RESET,
                wait=0.5 + attempt * 0.5
            )
            ack = self._parse_ack(resp) if resp else None

            if ack and ack['status'] == 0:
                print("[OK] Заводские настройки восстановлены!")
                print()
                print("  Рекомендуется:")
                print("  1. Передёрнуть питание датчика")
                print("  2. Запустить автокалибровку:")
                print("     python3 sensors/hlk_ld2402.py --calibrate")
                print()
                self.end_config()
                return True

            if resp and CMD_HEADER in resp:
                print("[OK] Получен ответ (предположительно сброс выполнен)")
                self.end_config()
                return True

            if self.debug and attempt < 2:
                print(f"  [RETRY] Попытка {attempt + 2}/3...")
            time.sleep(0.5)

        print("[ОШИБКА] Не удалось выполнить сброс")
        self.end_config()
        return False

    # ───────────────────────────────────────────────────────────────────────
    # Автонастройка усиления (0x00EE)
    # ───────────────────────────────────────────────────────────────────────

    def auto_gain_adjust(self) -> bool:
        """
        Автонастройка усиления (команда 0x00EE, v3.3.5+).

        Если радар в корпусе или рядом с большой отражающей поверхностью,
        сигнал может насыщаться. Эта команда автоматически снижает усиление
        до оптимального уровня.
        """
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║     АВТОНАСТРОЙКА УСИЛЕНИЯ (Auto Gain)          ║")
        print("╠══════════════════════════════════════════════════╣")
        print("║  Датчик автоматически подберёт оптимальное      ║")
        print("║  усиление приёмника. Это помогает, если:        ║")
        print("║  - датчик в корпусе (отражения от стенок)       ║")
        print("║  - рядом большая отражающая поверхность         ║")
        print("║  - сигнал «зашкаливает» (насыщение)             ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

        if not self.enable_config():
            return False

        print("  Запуск автонастройки усиления...")
        resp = self._send_command(Command.AUTO_GAIN_ADJUST, wait=0.5)
        ack = self._parse_ack(resp) if resp else None

        if ack and ack['status'] == 0:
            print("  [OK] Команда принята, ожидание завершения...")
        else:
            print("  [ПРЕДУПРЕЖДЕНИЕ] Нет подтверждения, ожидаем...")

        # Ждём завершения (ответ 0x00F0)
        for i in range(30):  # макс. 30 секунд
            time.sleep(1)
            data = self.serial.read(512) if self.serial else b''
            if data:
                ack2 = self._parse_ack(data)
                if ack2 and (ack2['command'] & 0xFF) == 0xF0:
                    print("[OK] Автонастройка усиления завершена!")
                    self.end_config()
                    return True
                if self.debug:
                    print(f"  [{i+1}с] ожидание...")

        print("[ПРЕДУПРЕЖДЕНИЕ] Таймаут ожидания завершения")
        self.end_config()
        return False

    # ───────────────────────────────────────────────────────────────────────
    # Автокалибровка (ИСПРАВЛЕННАЯ!)
    # ───────────────────────────────────────────────────────────────────────

    def start_auto_threshold(self, trigger_coeff: float = 3.0,
                             hold_coeff: float = 2.0,
                             micro_coeff: float = 3.0) -> bool:
        """
        Запустить автоматическую генерацию порогов (команда 0x0009).

        ⚠️  ВАЖНО: команда требует 6 байт данных — коэффициенты генерации!
        Без них калибровка НЕ РАБОТАЕТ корректно.

        Формат данных (даташит 5.2.9):
            [триггер 2B LE] [удержание 2B LE] [микродвижение 2B LE]

        Коэффициенты передаются ×10 (т.е. 3.0 → 0x001E = 30):
            Диапазон: 1.0 - 20.0 (0x000A - 0x00C8)

        Args:
            trigger_coeff: Коэффициент триггера (по умолчанию 3.0).
            hold_coeff: Коэффициент удержания (по умолчанию 2.0).
            micro_coeff: Коэффициент микродвижения (по умолчанию 3.0).
        """
        # Проверяем диапазон
        for name, val in [("триггер", trigger_coeff),
                          ("удержание", hold_coeff),
                          ("микродвижение", micro_coeff)]:
            if not (1.0 <= val <= 20.0):
                print(f"[ОШИБКА] Коэффициент {name} = {val} вне диапазона 1.0-20.0")
                return False

        # Конвертируем в ×10
        trigger_val = int(trigger_coeff * 10)
        hold_val = int(hold_coeff * 10)
        micro_val = int(micro_coeff * 10)

        # Формат: 6 байт = 3 × uint16 LE
        data = struct.pack('<HHH', trigger_val, hold_val, micro_val)

        if self.debug:
            print(f"  [CAL] Коэффициенты: триггер={trigger_coeff}, "
                  f"удержание={hold_coeff}, микродвижение={micro_coeff}")
            print(f"  [CAL] Данные: {data.hex(' ')}")

        resp = self._send_command(Command.START_AUTO_THRESHOLD, data, wait=0.3)
        ack = self._parse_ack(resp) if resp else None
        if ack and ack['status'] == 0:
            print("[OK] Автокалибровка запущена")
            return True

        print("[ПРЕДУПРЕЖДЕНИЕ] ACK автокалибровки не получен, проверяем статус...")
        return True  # Продолжаем, проверим прогресс далее

    def query_auto_threshold_progress(self) -> Optional[int]:
        """
        Запросить прогресс автокалибровки (команда 0x000A).
        Возвращает процент (0-100) или None.
        """
        resp = self._send_command(Command.QUERY_AUTO_THRESHOLD, wait=0.3)
        ack = self._parse_ack(resp) if resp else None
        if ack and ack['status'] == 0 and ack['data'] and len(ack['data']) >= 2:
            return struct.unpack_from('<H', ack['data'])[0]
        if ack and ack['data'] and len(ack['data']) >= 1:
            return ack['data'][0]
        return None

    def run_auto_calibration(self, trigger_coeff: float = 3.0,
                             hold_coeff: float = 2.0,
                             micro_coeff: float = 3.0) -> bool:
        """
        Полный цикл автокалибровки порогов с ожиданием завершения.

        Args:
            trigger_coeff: Коэффициент триггера (1.0-20.0, по умолчанию 3.0).
            hold_coeff: Коэффициент удержания (1.0-20.0, по умолчанию 2.0).
            micro_coeff: Коэффициент микродвижения (1.0-20.0, по умолчанию 3.0).
        """
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║          АВТОКАЛИБРОВКА HLK-LD2402              ║")
        print("╠══════════════════════════════════════════════════╣")
        print("║  ВНИМАНИЕ: В зоне датчика НЕ должно быть       ║")
        print("║  людей и движущихся объектов!                   ║")
        print("║                                                  ║")
        print("║  Датчик будет анализировать пустое помещение    ║")
        print("║  и автоматически настроит пороги обнаружения.   ║")
        print("╠══════════════════════════════════════════════════╣")
        print(f"║  Коэффициенты:                                  ║")
        print(f"║    Триггер:       {trigger_coeff:>4.1f}  (чувствительность)    ║")
        print(f"║    Удержание:     {hold_coeff:>4.1f}                          ║")
        print(f"║    Микродвижение: {micro_coeff:>4.1f}                          ║")
        print("║                                                  ║")
        print("║  Выше = менее чувствительный (меньше помех)     ║")
        print("║  Ниже = более чувствительный (дальше видит)     ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

        try:
            input("Нажмите Enter, когда помещение будет ПУСТЫМ (выйдите из комнаты!)...")
        except EOFError:
            pass

        if not self.enable_config():
            return False

        if not self.start_auto_threshold(trigger_coeff, hold_coeff, micro_coeff):
            self.end_config()
            return False

        print("Ожидание завершения калибровки...")
        interference_reported = False

        for i in range(120):  # макс. 10 минут
            time.sleep(5)

            # Проверяем прогресс
            progress = self.query_auto_threshold_progress()
            if progress is not None:
                bar = "█" * (progress // 5) + "░" * (20 - progress // 5)
                print(f"\r  [{bar}] {progress}%", end="", flush=True)
                if progress >= 100:
                    print()
                    print("[OK] Автокалибровка завершена!")

                    # Проверяем, не было ли помех
                    if not interference_reported:
                        print("  ✓ Помехи не обнаружены")

                    self.end_config()
                    return True
            else:
                # Возможно, пришёл отчёт о помехах (0x0014)
                print(".", end="", flush=True)

        print()
        print("[ПРЕДУПРЕЖДЕНИЕ] Калибровка не завершилась за отведённое время")
        self.end_config()
        return False

    # ───────────────────────────────────────────────────────────────────────
    # Чтение данных (текстовый режим)
    # ───────────────────────────────────────────────────────────────────────

    def read_data_stream(self, callback=None, duration: float = 0,
                         max_dist: int = 0, min_dist: int = 0,
                         avg_window: int = 1):
        """
        Непрерывное чтение данных с программной фильтрацией.

        В нормальном режиме датчик выводит:
            distance:XXX\\r\\n   — расстояние в сантиметрах
            OFF\\r\\n            — нет обнаружения
        """
        if not self.serial or not self.serial.is_open:
            print("[ОШИБКА] Нет подключения к датчику")
            return

        filter_active = max_dist > 0 or min_dist > 0 or avg_window > 1
        history = deque(maxlen=max(avg_window, 1))

        print("[СТАРТ] Чтение данных... (Ctrl+C для остановки)")
        if filter_active:
            filters = []
            if max_dist > 0:
                filters.append(f"макс: {max_dist} см")
            if min_dist > 0:
                filters.append(f"мин: {min_dist} см")
            if avg_window > 1:
                filters.append(f"медиана: {avg_window} замеров")
            print(f"[ФИЛЬТР] {', '.join(filters)}")

        print(f"{'Время':>10s}  {'Статус':<12s}  {'Расстояние':>15s}  ", end="")
        if filter_active:
            print(f"{'(сырое)':>10s}", end="")
        print()
        print("─" * (55 if filter_active else 42))

        start_time = time.time()
        line_buffer = ""
        rejected_count = 0

        try:
            while True:
                if duration > 0 and (time.time() - start_time) > duration:
                    break

                chunk = self.serial.read(256)
                if not chunk:
                    continue

                try:
                    line_buffer += chunk.decode('ascii', errors='ignore')
                except Exception:
                    continue

                while '\n' in line_buffer:
                    line, line_buffer = line_buffer.split('\n', 1)
                    line = line.strip()

                    if not line:
                        continue

                    elapsed = time.time() - start_time
                    match = RE_DISTANCE.match(line)

                    if match:
                        raw_cm = int(match.group(1))

                        if max_dist > 0 and raw_cm > max_dist:
                            rejected_count += 1
                            continue

                        if min_dist > 0 and raw_cm < min_dist:
                            rejected_count += 1
                            continue

                        history.append(raw_cm)

                        if avg_window > 1 and len(history) >= 2:
                            filtered_cm = int(statistics.median(history))
                        else:
                            filtered_cm = raw_cm

                        distance_m = filtered_cm / 100.0

                        data = {
                            'distance_cm': filtered_cm,
                            'distance_m': distance_m,
                            'raw_cm': raw_cm,
                            'status': 'Обнаружение',
                            'filtered': avg_window > 1,
                        }

                        if callback:
                            callback(data)
                        else:
                            line_str = (
                                f"\r{elapsed:>8.1f}с  "
                                f"{'Обнаружение':<12s}  "
                                f"{filtered_cm:>5d} см ({distance_m:.2f} м)"
                            )
                            if filter_active and raw_cm != filtered_cm:
                                line_str += f"  (сырое: {raw_cm})"
                            print(line_str, end="", flush=True)

                    elif line == "OFF":
                        data = {
                            'distance_cm': 0,
                            'distance_m': 0.0,
                            'raw_cm': 0,
                            'status': 'Нет цели',
                            'filtered': False,
                        }
                        history.clear()

                        if callback:
                            callback(data)
                        else:
                            print(
                                f"\r{elapsed:>8.1f}с  "
                                f"{'Нет цели':<12s}  "
                                f"{'---':>15s}",
                                end="", flush=True
                            )

                    elif self.debug:
                        print(f"\r{elapsed:>8.1f}с  [RAW] {line}")

        except KeyboardInterrupt:
            print()
            print("[СТОП] Чтение данных остановлено")
            if rejected_count > 0:
                print(f"  Отброшено замеров (вне диапазона): {rejected_count}")

    # ───────────────────────────────────────────────────────────────────────
    # Инженерный режим (ИСПРАВЛЕННЫЙ!)
    # ───────────────────────────────────────────────────────────────────────

    def read_engineering_stream(self, duration: float = 30):
        """
        Переключить в инженерный режим и показать данные по гейтам.

        Формат инженерного фрейма (даташит 5.6.2):
            Заголовок:  F4 F3 F2 F1
            Длина:      2 байта (LE)
            Результат:  1 байт (0x00=нет цели, 0x01=движение, 0x02=статика)
            Дистанция:  2 байта (LE, в см)
            Энергия:    128 байт = 32 гейта × 4 байта (LE uint32)
                        Первые 16 гейтов = энергия движения
                        Следующие 16 = энергия микродвижения
            Окончание:  F8 F7 F6 F5

        Каждый гейт = 70 см.
        """
        if not self.serial or not self.serial.is_open:
            print("[ОШИБКА] Нет подключения к датчику")
            return

        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║       ИНЖЕНЕРНЫЙ РЕЖИМ HLK-LD2402               ║")
        print("╠══════════════════════════════════════════════════╣")
        print("║  Показывает энергию сигнала по каждому гейту.   ║")
        print("║  Каждый гейт = 70 см.                          ║")
        print("║                                                  ║")
        print("║  Движение: энергия от движущихся объектов       ║")
        print("║  Микродвиж.: энергия от дыхания/покачивания     ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

        # Переключаемся в инженерный режим
        if not self.enable_config():
            return

        eng_ok = self.set_output_mode(OutputMode.ENGINEERING)
        self.end_config()

        if not eng_ok:
            print("[ОШИБКА] Не удалось переключить в инженерный режим")
            return

        print(f"[СТАРТ] Чтение инженерных данных ({duration} сек)...")
        print("  Ctrl+C для остановки")
        print()

        start_time = time.time()
        raw_buffer = b''
        frame_count = 0
        detect_names = {0: "Нет цели", 1: "Движение", 2: "Статика"}

        try:
            while (time.time() - start_time) < duration:
                data = self.serial.read(512)
                if not data:
                    continue

                raw_buffer += data

                # Ищем инженерные фреймы (F4 F3 F2 F1 ... F8 F7 F6 F5)
                while True:
                    hdr_pos = raw_buffer.find(ENG_HEADER)
                    if hdr_pos == -1:
                        # Сохраняем хвост на случай частичного заголовка
                        if len(raw_buffer) > 4:
                            raw_buffer = raw_buffer[-4:]
                        break

                    # Нужно минимум 6 байт для заголовка + длины
                    if hdr_pos + 6 > len(raw_buffer):
                        break

                    frame_len = struct.unpack_from('<H', raw_buffer, hdr_pos + 4)[0]
                    frame_end = hdr_pos + 6 + frame_len + 4  # +4 для footer

                    if frame_end > len(raw_buffer):
                        break  # Неполный фрейм, ждём ещё данных

                    # Проверяем footer
                    footer = raw_buffer[frame_end - 4:frame_end]
                    if footer != ENG_FOOTER:
                        raw_buffer = raw_buffer[hdr_pos + 4:]
                        continue

                    # Извлекаем данные фрейма
                    frame_data = raw_buffer[hdr_pos + 6:frame_end - 4]
                    raw_buffer = raw_buffer[frame_end:]

                    if len(frame_data) < 3:
                        continue

                    detect_result = frame_data[0]
                    target_dist = struct.unpack_from('<H', frame_data, 1)[0]
                    detect_str = detect_names.get(detect_result, f"?{detect_result}")

                    elapsed = time.time() - start_time

                    print(f"\n  ─── {elapsed:>5.1f}с │ {detect_str} │ "
                          f"Расстояние: {target_dist} см ({target_dist/100:.2f} м) ───")

                    # Парсим энергию по гейтам (32 × uint32)
                    energy_data = frame_data[3:]
                    if len(energy_data) >= 128:
                        # Первые 16 гейтов = движение
                        print(f"  {'Гейт':>6s}  {'Зона':>12s}  "
                              f"{'Движение':>10s}  {'дБ':>7s}  "
                              f"{'Микродвиж.':>10s}  {'дБ':>7s}  График")
                        print("  " + "─" * 85)

                        for g in range(NUM_GATES):
                            motion_energy = struct.unpack_from(
                                '<I', energy_data, g * 4
                            )[0]
                            micro_energy = struct.unpack_from(
                                '<I', energy_data, (NUM_GATES + g) * 4
                            )[0]

                            motion_db = threshold_to_db(motion_energy) if motion_energy > 0 else 0
                            micro_db = threshold_to_db(micro_energy) if micro_energy > 0 else 0

                            # Визуализация
                            bar_motion = "█" * min(int(motion_db / 2), 20)
                            bar_micro = "▒" * min(int(micro_db / 2), 20)

                            zone_start = g * GATE_SIZE_CM
                            zone_end = (g + 1) * GATE_SIZE_CM

                            print(
                                f"  {g:>4d}  "
                                f"  {zone_start:>4d}-{zone_end:>4d}см"
                                f"  {motion_energy:>10d}  {motion_db:>6.1f}"
                                f"  {micro_energy:>10d}  {micro_db:>6.1f}"
                                f"  {bar_motion}{bar_micro}"
                            )

                    frame_count += 1

                # Также обрабатываем текстовые данные, если есть
                # (датчик может продолжать слать distance:XXX)
                text_part = b''
                for byte in data:
                    if 32 <= byte < 127 or byte in (10, 13):
                        text_part += bytes([byte])

                if text_part and self.debug:
                    text_lines = text_part.decode('ascii', errors='ignore').strip()
                    if text_lines:
                        for tl in text_lines.split('\n'):
                            tl = tl.strip()
                            if tl and tl != 'OFF' and not RE_DISTANCE.match(tl):
                                elapsed = time.time() - start_time
                                print(f"  {elapsed:>6.1f}с  [TXT] {tl}")

        except KeyboardInterrupt:
            print()
            print("[СТОП] Остановлено")

        # Возвращаемся в обычный режим
        print()
        print("Возврат в нормальный режим...")
        if self.enable_config():
            self.set_output_mode(OutputMode.NORMAL)
            self.end_config()

        print(f"  Получено фреймов: {frame_count}")

    # ───────────────────────────────────────────────────────────────────────
    # Тест дистанции
    # ───────────────────────────────────────────────────────────────────────

    def test_distance(self):
        """
        Интерактивный тест для определения точности измерений.
        Просит встать на известных расстояниях и собирает показания.
        """
        if not self.serial or not self.serial.is_open:
            print("[ОШИБКА] Нет подключения к датчику")
            return

        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║   ТЕСТ ТОЧНОСТИ ИЗМЕРЕНИЯ РАССТОЯНИЯ            ║")
        print("╠══════════════════════════════════════════════════╣")
        print("║  Встаньте на ИЗВЕСТНОМ расстоянии от датчика.   ║")
        print("║  Убедитесь, что за вами НЕТ стены ближе 3 м.   ║")
        print("║  Мин. расстояние для 24 ГГц радара: ~50 см.    ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

        test_distances = [50, 100, 150, 200]
        results = []

        for real_cm in test_distances:
            try:
                input(f"  Встаньте на {real_cm} см ({real_cm/100:.1f} м) "
                      f"от датчика и нажмите Enter...")
            except EOFError:
                break

            readings = []
            line_buffer = ""
            self.serial.reset_input_buffer()
            start = time.time()

            while time.time() - start < 4:
                chunk = self.serial.read(256)
                if not chunk:
                    continue
                try:
                    line_buffer += chunk.decode('ascii', errors='ignore')
                except Exception:
                    continue

                while '\n' in line_buffer:
                    line, line_buffer = line_buffer.split('\n', 1)
                    line = line.strip()
                    match = RE_DISTANCE.match(line)
                    if match:
                        readings.append(int(match.group(1)))

            if readings:
                med = int(statistics.median(readings))
                avg = int(sum(readings) / len(readings))
                mn = min(readings)
                mx = max(readings)
                results.append((real_cm, med, avg, mn, mx, len(readings)))
                print(f"    Реальное: {real_cm:>4d} см  →  "
                      f"Датчик: медиана={med}, "
                      f"средн={avg}, мин={mn}, макс={mx} "
                      f"({len(readings)} замеров)")
            else:
                print(f"    Реальное: {real_cm:>4d} см  →  нет данных!")

            print()

        if not results:
            print("[ОШИБКА] Нет данных для анализа")
            return

        print()
        print("═" * 60)
        print("РЕЗУЛЬТАТЫ:")
        print("═" * 60)
        print(f"  {'Реальное (см)':>14s}  {'Датчик':>8s}  {'Коэффициент':>12s}")
        print("  " + "─" * 40)

        ratios = []
        for real_cm, med, avg, mn, mx, cnt in results:
            if med > 0:
                ratio = real_cm / med
                ratios.append(ratio)
                print(f"  {real_cm:>14d}  {med:>8d}  {ratio:>12.3f}")
            else:
                print(f"  {real_cm:>14d}  {med:>8d}  {'N/A':>12s}")

        if ratios:
            avg_ratio = sum(ratios) / len(ratios)
            print()
            if 0.9 < avg_ratio < 1.1:
                print(f"  → Точность ХОРОШАЯ (коэффициент ≈ {avg_ratio:.3f})")
            else:
                print(f"  → Систематическая ошибка! Коэффициент: {avg_ratio:.3f}")
                print(f"    Для коррекции: distance_cm = distance_raw × {avg_ratio:.3f}")
            print()

    def read_raw_stream(self, duration: float = 10):
        """Чтение сырых данных — HEX + текст (для отладки)."""
        if not self.serial or not self.serial.is_open:
            print("[ОШИБКА] Нет подключения к датчику")
            return

        print(f"[СТАРТ] Чтение RAW данных ({duration} сек)...")
        print()

        start_time = time.time()
        try:
            while (time.time() - start_time) < duration:
                data = self.serial.read(128)
                if data:
                    hex_str = ' '.join(f'{b:02X}' for b in data)
                    ascii_str = ''.join(
                        chr(b) if 32 <= b < 127 else '.' for b in data
                    )
                    print(f"HEX: {hex_str}")
                    print(f"ASC: {ascii_str}")
                    print()
        except KeyboardInterrupt:
            print()
            print("[СТОП]")

    # ───────────────────────────────────────────────────────────────────────
    # Информация о датчике
    # ───────────────────────────────────────────────────────────────────────

    def print_device_info(self):
        """Вывести полную информацию о датчике."""
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║           ИНФОРМАЦИЯ О ДАТЧИКЕ                  ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

        if not self.enable_config():
            return

        time.sleep(0.1)

        # Прошивка
        fw = self.read_firmware_version()
        print(f"  Прошивка:      {fw if fw else 'не удалось прочитать'}")

        # Серийный номер (строка)
        sn = self.read_serial_number()
        print(f"  Серийный №:    {sn if sn else 'не удалось прочитать'}")

        # Серийный номер (HEX, v3.3.5+)
        sn_hex = self.read_serial_hex()
        print(f"  Серийный (HEX):{sn_hex if sn_hex else 'не удалось прочитать'}")

        # Ключевые параметры
        max_dist = self.read_param_by_index(0x0001)
        if max_dist is not None:
            print(f"  Макс. дистанция: {max_dist} (= {max_dist * 0.1:.1f} м)")

        timeout = self.read_param_by_index(0x0004)
        if timeout is not None:
            print(f"  Таймаут:       {timeout} с")

        pwr_alarm = self.read_param_by_index(0x0005)
        if pwr_alarm is not None:
            pwr_str = {0: "не проверено", 1: "нет помех ✓", 2: "ЕСТЬ ПОМЕХИ ⚠️"}
            print(f"  Помехи питания: {pwr_str.get(pwr_alarm, f'?{pwr_alarm}')}")

        print(f"  Порт:          {self.port}")
        print(f"  Скорость:      {self.baudrate} бод")
        print()

        self.end_config()

    # ───────────────────────────────────────────────────────────────────────
    # Сканирование команд
    # ───────────────────────────────────────────────────────────────────────

    def scan_commands(self):
        """Перебор команд для определения рабочих кодов."""
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║        СКАНИРОВАНИЕ КОМАНД HLK-LD2402           ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

        print("─── Включение режима конфигурации ───")
        resp = self._send_command(Command.ENABLE_CONFIG, b'\x01\x00')
        ack = self._parse_ack(resp) if resp else None
        if not (ack and ack['status'] == 0):
            print("[ОШИБКА] Не удалось войти в режим конфигурации")
            return
        print("[OK] Режим конфигурации включён")
        print()

        commands_to_try = [
            (0x0000, "Чтение версии прошивки", b''),
            (0x0011, "Чтение серийного номера (STR)", b''),
            (0x0016, "Чтение серийного номера (HEX)", b''),
            (0x0008, "Чтение параметров", b''),
            (0x0012, "Режим вывода данных", b''),
            (0x00EE, "Автонастройка усиления", b''),
            (0x00FD, "Сохранение в flash", b''),
            (0x0060, "Сброс к заводским", b''),
        ]

        found_commands = []

        for cmd_code, cmd_name, cmd_data in commands_to_try:
            print(f"─── {cmd_name} (0x{cmd_code:04X}) ───")
            resp = self._send_command(cmd_code, cmd_data, wait=0.2)

            if resp:
                ack = self._parse_ack(resp)
                if ack:
                    data_str = ack['data'].hex(' ') if ack['data'] else '(нет)'
                    status_str = "OK" if ack['status'] == 0 else f"ERR({ack['status']})"
                    print(f"  ✅ ACK [{status_str}]: {data_str}")
                    found_commands.append((cmd_code, cmd_name, ack))
                else:
                    try:
                        text = resp.decode('ascii', errors='ignore').strip()[:100]
                        if text:
                            print(f"  ⚠️  Текстовый ответ: {text}")
                    except Exception:
                        print(f"  ⚠️  Ответ ({len(resp)} байт): {resp[:30].hex(' ')}...")
            else:
                print("  ❌ Нет ответа")

            print()
            time.sleep(0.15)

        print("─── Выход из режима конфигурации ───")
        self._send_command(Command.END_CONFIG)
        print()

        print("═" * 55)
        print("РЕЗУЛЬТАТЫ СКАНИРОВАНИЯ:")
        print("═" * 55)
        if found_commands:
            for cmd_code, cmd_name, ack in found_commands:
                status_str = "OK" if ack['status'] == 0 else f"ERR({ack['status']})"
                data_str = ack['data'].hex(' ') if ack['data'] else "(нет данных)"
                print(f"  ✅ 0x{cmd_code:04X}  [{status_str:>6s}]  {cmd_name}")
                if ack['data']:
                    print(f"     Данные: {data_str}")
        else:
            print("  Ни одна команда не вернула валидный ACK")
        print()


# ═══════════════════════════════════════════════════════════════════════════════
# Точка входа (CLI)
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="HLK-LD2402 — 24 ГГц радарный датчик присутствия",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s                           Чтение данных с порта по умолчанию
  %(prog)s --info                    Показать информацию о датчике
  %(prog)s --calibrate               Автокалибровка (коэфф. по умолчанию)
  %(prog)s --calibrate --trigger-coeff 3.0 --hold-coeff 2.0 --micro-coeff 3.0
  %(prog)s --auto-gain               Автонастройка усиления
  %(prog)s --engineering             Инженерный режим (энергия по гейтам)
  %(prog)s --dump-params             Все параметры с расшифровкой
  %(prog)s --set-param 0x0001 85     Установить макс. дистанцию 8.5м
  %(prog)s --factory-reset           Сброс к заводским настройкам
  %(prog)s --max-dist 120 --avg 5    Фильтрация: макс 120 см + медиана по 5
  %(prog)s --test-distance           Тест точности на известных расстояниях
  %(prog)s --raw                     Сырые данные (отладка)
  %(prog)s --debug                   Подробный TX/RX
        """,
    )

    parser.add_argument("--port", "-p", default=DEFAULT_PORT,
                        help=f"Последовательный порт (по умолчанию: {DEFAULT_PORT})")
    parser.add_argument("--baud", "-b", type=int, default=DEFAULT_BAUD,
                        help=f"Скорость UART (по умолчанию: {DEFAULT_BAUD})")
    parser.add_argument("--info", "-i", action="store_true",
                        help="Показать информацию о датчике")
    parser.add_argument("--calibrate", "-c", action="store_true",
                        help="Запустить автокалибровку порогов")
    parser.add_argument("--trigger-coeff", type=float, default=3.0,
                        help="Коэффициент триггера для калибровки (1.0-20.0, по умолч. 3.0)")
    parser.add_argument("--hold-coeff", type=float, default=2.0,
                        help="Коэффициент удержания для калибровки (1.0-20.0, по умолч. 2.0)")
    parser.add_argument("--micro-coeff", type=float, default=3.0,
                        help="Коэффициент микродвижения для калибровки (1.0-20.0, по умолч. 3.0)")
    parser.add_argument("--auto-gain", action="store_true",
                        help="Автонастройка усиления (если сигнал насыщается)")
    parser.add_argument("--raw", "-r", action="store_true",
                        help="Сырые данные в HEX (отладка)")
    parser.add_argument("--duration", "-d", type=float, default=0,
                        help="Длительность чтения в секундах (0 = бесконечно)")
    parser.add_argument("--debug", action="store_true",
                        help="Подробный TX/RX для отладки протокола")
    parser.add_argument("--scan", "-s", action="store_true",
                        help="Сканировать команды")
    parser.add_argument("--max-dist", type=int, default=0, metavar="СМ",
                        help="Программный фильтр: игнорировать > N см")
    parser.add_argument("--min-dist", type=int, default=0, metavar="СМ",
                        help="Программный фильтр: игнорировать < N см")
    parser.add_argument("--avg", type=int, default=1, metavar="N",
                        help="Медианный фильтр по N замерам")
    parser.add_argument("--engineering", "-e", action="store_true",
                        help="Инженерный режим: энергия по каждому гейту")
    parser.add_argument("--factory-reset", action="store_true",
                        help="Сброс к заводским настройкам")
    parser.add_argument("--test-distance", action="store_true",
                        help="Тест точности на известных расстояниях")
    parser.add_argument("--dump-params", action="store_true",
                        help="Показать все параметры датчика")
    parser.add_argument("--set-param", nargs=2, type=str,
                        metavar=("ID", "ЗНАЧЕНИЕ"),
                        help="Установить параметр: --set-param 0x0001 85")

    args = parser.parse_args()

    sensor = HlkLd2402(port=args.port, baudrate=args.baud, debug=args.debug)

    if not sensor.connect():
        sys.exit(1)

    try:
        if args.test_distance:
            sensor.test_distance()

        elif args.factory_reset:
            sensor.factory_reset()

        elif args.auto_gain:
            sensor.auto_gain_adjust()

        elif args.dump_params:
            sensor.dump_all_params()

        elif args.set_param:
            idx_str, val_str = args.set_param
            idx = int(idx_str, 0)
            val = int(val_str, 0)
            sensor.set_param_interactive(idx, val)

        elif args.scan:
            sensor.scan_commands()

        elif args.info:
            sensor.print_device_info()

        elif args.calibrate:
            sensor.run_auto_calibration(
                trigger_coeff=args.trigger_coeff,
                hold_coeff=args.hold_coeff,
                micro_coeff=args.micro_coeff,
            )

        elif args.engineering:
            sensor.read_engineering_stream(
                duration=args.duration or 30
            )

        elif args.raw:
            sensor.read_raw_stream(duration=args.duration or 10)

        else:
            sensor.read_data_stream(
                duration=args.duration,
                max_dist=args.max_dist,
                min_dist=args.min_dist,
                avg_window=args.avg,
            )

    except KeyboardInterrupt:
        print("\n[СТОП] Прервано пользователем")

    finally:
        sensor.disconnect()


if __name__ == "__main__":
    main()
