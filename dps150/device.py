from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional

import serial  # pyserial

from .protocol import (
    HEADER_OUTPUT,
    CMD_BAUD,
    CMD_SESSION,
    ALL,
    MODEL_NAME,
    HARDWARE_VERSION,
    FIRMWARE_VERSION,
    METERING_ENABLE,
    OUTPUT_ENABLE,
    encode_frame,
    encode_get,
    encode_session,
    encode_set_byte,
    encode_set_float,
    parse_payload,
    try_extract_frame,
)


UpdateCallback = Callable[[Dict[str, object]], None]


class DPS150:
    """
    Simple DPS150 serial client.

    - open(): opens serial and starts background reader thread.
    - close(): stops reader and closes serial.
    - callback(update_dict): called whenever a frame is parsed into updates.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.2,
        callback: Optional[UpdateCallback] = None,
        write_delay_s: float = 0.05,
    ) -> None:
        self.port_name = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.callback = callback or (lambda d: None)
        self.write_delay_s = write_delay_s

        self._ser: Optional[serial.Serial] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._rx_buf = bytearray()
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def open(self) -> None:
        if self.is_open:
            return

        self._ser = serial.Serial(
            self.port_name,
            self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            xonxoff=False,
            rtscts=True,      # matches JS 'hardware' flowControl
            dsrdtr=False,
        )

        self._stop_evt.clear()
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

        # init sequence like JS
        self._init_commands()

    def close(self) -> None:
        if not self.is_open:
            return

        # send session close (mirrors JS stop())
        try:
            self._send(encode_session(False))
        except Exception:
            pass

        self._stop_evt.set()
        if self._reader_thread:
            self._reader_thread.join(timeout=1.0)

        if self._ser:
            try:
                self._ser.close()
            finally:
                self._ser = None

    def _send(self, data: bytes) -> None:
        if not self._ser:
            raise RuntimeError("Serial not open")
        with self._lock:
            self._ser.write(data)
            self._ser.flush()
        time.sleep(self.write_delay_s)

    def _reader_loop(self) -> None:
        assert self._ser is not None
        while not self._stop_evt.is_set():
            try:
                chunk = self._ser.read(1024)
                if chunk:
                    self._rx_buf.extend(chunk)

                    while True:
                        res = try_extract_frame(self._rx_buf)
                        if res is None:
                            break
                        frame, consumed = res
                        # consume
                        del self._rx_buf[:consumed]

                        updates = parse_payload(frame.type_id, frame.payload)
                        if updates:
                            self.callback(updates)
            except Exception:
                # Keep loop alive; caller can restart by reopening.
                time.sleep(0.1)

    def _init_commands(self) -> None:
        # JS:
        # sendCommand(HEADER_OUTPUT, CMD_SESSION, 0, 1)
        # sendCommand(HEADER_OUTPUT, CMD_BAUD, 0, idx(115200)+1)
        self._send(encode_session(True))

        # baud table: [9600, 19200, 38400, 57600, 115200]
        baud_table = [9600, 19200, 38400, 57600, 115200]
        idx = baud_table.index(self.baudrate) if self.baudrate in baud_table else (len(baud_table) - 1)
        # frame: header, cmd, type_id=0, payload=[idx+1]
        self._send(encode_frame(HEADER_OUTPUT, CMD_BAUD, 0, bytes([idx + 1])))

        self.get(MODEL_NAME)
        self.get(HARDWARE_VERSION)
        self.get(FIRMWARE_VERSION)
        self.get_all()

    # -------- Public commands --------

    def get(self, type_id: int) -> None:
        self._send(encode_get(type_id))

    def get_all(self) -> None:
        self._send(encode_get(ALL))

    def set_float(self, type_id: int, value: float) -> None:
        self._send(encode_set_float(type_id, value))

    def set_byte(self, type_id: int, value: int) -> None:
        self._send(encode_set_byte(type_id, value))

    def enable_output(self) -> None:
        self.set_byte(OUTPUT_ENABLE, 1)

    def disable_output(self) -> None:
        self.set_byte(OUTPUT_ENABLE, 0)

    def start_metering(self) -> None:
        self.set_byte(METERING_ENABLE, 1)

    def stop_metering(self) -> None:
        self.set_byte(METERING_ENABLE, 0)
