from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union


HEADER_INPUT = 0xF0   # device -> host frames often use 0xF0 in your JS parser
HEADER_OUTPUT = 0xF1  # host -> device frames

CMD_GET = 0xA1
CMD_BAUD = 0xB0
CMD_SET = 0xB1
CMD_SESSION = 0xC1

# Float "types" (register-like IDs)
VOLTAGE_SET = 193
CURRENT_SET = 194

GROUP1_VOLTAGE_SET = 197
GROUP1_CURRENT_SET = 198
GROUP2_VOLTAGE_SET = 199
GROUP2_CURRENT_SET = 200
GROUP3_VOLTAGE_SET = 201
GROUP3_CURRENT_SET = 202
GROUP4_VOLTAGE_SET = 203
GROUP4_CURRENT_SET = 204
GROUP5_VOLTAGE_SET = 205
GROUP5_CURRENT_SET = 206
GROUP6_VOLTAGE_SET = 207
GROUP6_CURRENT_SET = 208

OVP = 209
OCP = 210
OPP = 211
OTP = 212
LVP = 213

# Byte "types"
BRIGHTNESS = 214
VOLUME = 215

METERING_ENABLE = 216
OUTPUT_ENABLE = 219

MODEL_NAME = 222
HARDWARE_VERSION = 223
FIRMWARE_VERSION = 224

ALL = 255

PROTECTION_STATES = [
    "",
    "OVP",
    "OCP",
    "OPP",
    "OTP",
    "LVP",
    "REP",
]


@dataclass(frozen=True)
class Frame:
    header: int
    cmd: int
    type_id: int
    payload: bytes

    @property
    def length(self) -> int:
        return len(self.payload)


def checksum(type_id: int, payload: bytes) -> int:
    c4 = len(payload)
    s = type_id + c4 + sum(payload)
    return s & 0xFF


def encode_frame(header: int, cmd: int, type_id: int, payload: Union[bytes, bytearray]) -> bytes:
    payload_b = bytes(payload)
    c4 = len(payload_b)
    c6 = checksum(type_id, payload_b)
    return bytes([header, cmd, type_id, c4]) + payload_b + bytes([c6])


def encode_set_float(type_id: int, value: float, header: int = HEADER_OUTPUT) -> bytes:
    payload = struct.pack("<f", float(value))
    return encode_frame(header, CMD_SET, type_id, payload)


def encode_set_byte(type_id: int, value: int, header: int = HEADER_OUTPUT) -> bytes:
    payload = bytes([int(value) & 0xFF])
    return encode_frame(header, CMD_SET, type_id, payload)


def encode_get(type_id: int, header: int = HEADER_OUTPUT) -> bytes:
    # JS uses payload [0] for GET requests
    return encode_frame(header, CMD_GET, type_id, bytes([0]))


def encode_session(open_session: bool, header: int = HEADER_OUTPUT) -> bytes:
    # JS: sendCommand(HEADER_OUTPUT, CMD_SESSION, 0, 1|0)
    return encode_frame(header, CMD_SESSION, 0, bytes([1 if open_session else 0]))


def try_extract_frame(buffer: bytearray) -> Optional[Tuple[Frame, int]]:
    """
    Attempt to find and validate a frame inside `buffer`.
    Returns (frame, consumed_bytes) if found; otherwise None.

    We search for sequence [0xF0, 0xA1] like your JS reader (input header + CMD_GET),
    but to be more robust we accept headers 0xF0 or 0xF1 and any cmd.
    """
    n = len(buffer)
    if n < 6:
        return None

    for i in range(0, n - 5):
        header = buffer[i]
        if header not in (HEADER_INPUT, HEADER_OUTPUT):
            continue

        cmd = buffer[i + 1]
        type_id = buffer[i + 2]
        c4 = buffer[i + 3]

        end = i + 4 + c4  # end of payload
        if end >= n:
            # not enough yet
            return None

        payload = bytes(buffer[i + 4 : i + 4 + c4])
        c6 = buffer[i + 4 + c4]

        if checksum(type_id, payload) != c6:
            # checksum mismatch: skip this byte and continue searching
            continue

        frame = Frame(header=header, cmd=cmd, type_id=type_id, payload=payload)
        consumed = i + 5 + c4
        return frame, consumed

    return None


def parse_payload(type_id: int, payload: bytes) -> Dict[str, object]:
    """
    Mirrors your JS parseData() mapping and returns a dict with zero or more keys.
    """
    out: Dict[str, object] = {}

    def f32(offset: int) -> float:
        return struct.unpack_from("<f", payload, offset)[0]

    # Single-values and small frames
    if type_id == 192:  # input voltage
        out["inputVoltage"] = f32(0)
    elif type_id == 195:  # output voltage, current, power
        out["outputVoltage"] = f32(0)
        out["outputCurrent"] = f32(4)
        out["outputPower"] = f32(8)
    elif type_id == 196:  # temperature
        out["temperature"] = f32(0)
    elif type_id == 217:  # output capacity
        out["outputCapacity"] = f32(0)
    elif type_id == 218:  # output energy
        out["outputEnergy"] = f32(0)
    elif type_id == 219:  # output closed?
        out["outputClosed"] = (payload[0] == 1)
    elif type_id == 220:  # protection
        idx = payload[0]
        out["protectionState"] = PROTECTION_STATES[idx] if idx < len(PROTECTION_STATES) else str(idx)
    elif type_id == 221:  # cc=0 or cv=1
        out["mode"] = "CC" if payload[0] == 0 else "CV"
    elif type_id == 222:
        out["modelName"] = payload.decode(errors="replace")
    elif type_id == 223:
        out["hardwareVersion"] = payload.decode(errors="replace")
    elif type_id == 224:
        out["firmwareVersion"] = payload.decode(errors="replace")
    elif type_id == 226:
        out["upperLimitVoltage"] = f32(0)
    elif type_id == 227:
        out["upperLimitCurrent"] = f32(0)
    elif type_id == 255:
        # "ALL" block: follow your JS offsets exactly
        # NOTE: This assumes payload is at least 96+ etc. If shorter, we guard.
        if len(payload) < 95:
            out["rawAll"] = payload
            return out

        out.update(
            inputVoltage=f32(0),
            setVoltage=f32(4),
            setCurrent=f32(8),
            outputVoltage=f32(12),
            outputCurrent=f32(16),
            outputPower=f32(20),
            temperature=f32(24),

            group1setVoltage=f32(28),
            group1setCurrent=f32(32),
            group2setVoltage=f32(36),
            group2setCurrent=f32(40),
            group3setVoltage=f32(44),
            group3setCurrent=f32(48),
            group4setVoltage=f32(52),
            group4setCurrent=f32(56),
            group5setVoltage=f32(60),
            group5setCurrent=f32(64),
            group6setVoltage=f32(68),
            group6setCurrent=f32(72),

            overVoltageProtection=f32(76),
            overCurrentProtection=f32(80),
            overPowerProtection=f32(84),
            overTemperatureProtection=f32(88),
            lowVoltageProtection=f32(92),
        )

        # bytes at fixed positions
        if len(payload) > 98:
            out["brightness"] = payload[96]
            out["volume"] = payload[97]
            out["meteringClosed"] = (payload[98] == 0)

        if len(payload) >= 109:
            out["outputCapacity"] = f32(99)   # Ah
            out["outputEnergy"] = f32(103)    # Wh
            out["outputClosed"] = (payload[107] == 1)
            prot = payload[108]
            out["protectionState"] = PROTECTION_STATES[prot] if prot < len(PROTECTION_STATES) else str(prot)
            out["mode"] = "CC" if payload[109] == 0 else "CV"

        if len(payload) >= 119:
            out["upperLimitVoltage"] = f32(111)
            out["upperLimitCurrent"] = f32(115)

    # Unhandled type_ids are ignored
    return out
