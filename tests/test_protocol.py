import struct
import pytest

from dps150.protocol import (
    Frame,
    checksum,
    encode_frame,
    encode_get,
    encode_session,
    encode_set_byte,
    encode_set_float,
    try_extract_frame,
    parse_payload,
    HEADER_OUTPUT,
    HEADER_INPUT,
    CMD_GET,
    CMD_SET,
    CMD_SESSION,
    ALL,
)


def test_checksum_matches_js_definition():
    # JS: s = type_id + len + sum(payload); s %= 0x100
    type_id = 0xC1
    payload = bytes([1, 2, 3, 255])
    expected = (type_id + len(payload) + sum(payload)) & 0xFF
    assert checksum(type_id, payload) == expected


def test_encode_frame_layout_and_checksum():
    header = HEADER_OUTPUT
    cmd = 0xA1
    type_id = 0xDE
    payload = bytes([0x00, 0x01, 0x02])
    frame = encode_frame(header, cmd, type_id, payload)

    assert frame[0] == header
    assert frame[1] == cmd
    assert frame[2] == type_id
    assert frame[3] == len(payload)
    assert frame[4:4 + len(payload)] == payload
    assert frame[-1] == checksum(type_id, payload)


def test_encode_get_payload_is_single_zero():
    f = encode_get(0x22)
    assert f[0] == HEADER_OUTPUT
    assert f[1] == CMD_GET
    assert f[2] == 0x22
    assert f[3] == 1
    assert f[4] == 0
    assert f[-1] == checksum(0x22, bytes([0]))


def test_encode_session_open_close():
    open_f = encode_session(True)
    close_f = encode_session(False)

    assert open_f[1] == CMD_SESSION and open_f[4] == 1
    assert close_f[1] == CMD_SESSION and close_f[4] == 0


def test_encode_set_float_is_little_endian_float32():
    # float32 little-endian expected
    v = 12.5
    f = encode_set_float(type_id=193, value=v)
    assert f[1] == CMD_SET
    payload = f[4:8]  # 4 bytes
    assert payload == struct.pack("<f", v)


def test_encode_set_byte_is_single_byte():
    f = encode_set_byte(type_id=214, value=7)
    assert f[1] == CMD_SET
    assert f[3] == 1
    assert f[4] == 7


def test_try_extract_frame_finds_frame_with_noise_prefix():
    payload = bytes([0x10, 0x20])
    frame_bytes = encode_frame(HEADER_INPUT, 0xA1, 0x55, payload)

    buf = bytearray(b"\x00\x01garbage" + frame_bytes + b"\x99\x88")
    res = try_extract_frame(buf)
    assert res is not None

    frame, consumed = res
    assert isinstance(frame, Frame)
    assert frame.header == HEADER_INPUT
    assert frame.cmd == 0xA1
    assert frame.type_id == 0x55
    assert frame.payload == payload

    # After consuming, remaining should start with the trailing bytes
    del buf[:consumed]
    assert buf.startswith(b"\x99\x88")


def test_try_extract_frame_rejects_bad_checksum_and_continues():
    payload = bytes([0x10, 0x20])
    good = encode_frame(HEADER_INPUT, 0xA1, 0x55, payload)
    bad = bytearray(good)
    bad[-1] ^= 0xFF  # corrupt checksum

    buf = bytearray(bad + good)
    res = try_extract_frame(buf)
    assert res is not None
    frame, consumed = res
    assert frame.payload == payload  # should find the second (good) frame


def test_parse_payload_input_voltage_type_192():
    # type_id 192: float32 at offset 0
    payload = struct.pack("<f", 19.0)
    out = parse_payload(192, payload)
    assert out["inputVoltage"] == pytest.approx(19.0, rel=1e-6)


def test_parse_payload_output_bundle_type_195():
    payload = struct.pack("<fff", 12.0, 1.5, 18.0)
    out = parse_payload(195, payload)
    assert out["outputVoltage"] == pytest.approx(12.0)
    assert out["outputCurrent"] == pytest.approx(1.5)
    assert out["outputPower"] == pytest.approx(18.0)


def test_parse_payload_strings_model_hw_fw():
    out = parse_payload(222, b"DPS150")
    assert out["modelName"] == "DPS150"

    out = parse_payload(223, b"HW1.0")
    assert out["hardwareVersion"] == "HW1.0"

    out = parse_payload(224, b"FW1.2.3")
    assert out["firmwareVersion"] == "FW1.2.3"


def test_parse_payload_all_minimum_short_payload_returns_raw():
    out = parse_payload(ALL, b"\x00" * 20)
    assert "rawAll" in out


def test_parse_payload_all_happy_path_extracts_key_fields():
    # Build a minimally consistent ALL payload up to upperLimitCurrent.
    # Offsets follow your JS mapping used in protocol.parse_payload().
    payload = bytearray(b"\x00" * 119)  # up to and incl float at 115

    def put_f32(off, val):
        payload[off:off+4] = struct.pack("<f", float(val))

    put_f32(0, 19.0)    # inputVoltage
    put_f32(4, 12.0)    # setVoltage
    put_f32(8, 1.0)     # setCurrent
    put_f32(12, 11.9)   # outputVoltage
    put_f32(16, 0.9)    # outputCurrent
    put_f32(20, 10.7)   # outputPower
    put_f32(24, 35.0)   # temperature
    put_f32(76, 13.0)   # ovp
    put_f32(80, 2.0)    # ocp

    payload[96] = 5     # brightness
    payload[97] = 3     # volume
    payload[98] = 0     # meteringClosed (0 means closed per JS mapping)

    put_f32(99, 0.123)  # outputCapacity
    put_f32(103, 1.234) # outputEnergy
    payload[107] = 1    # outputClosed -> True
    payload[108] = 1    # protectionState -> OVP
    payload[109] = 0    # mode -> CC

    put_f32(111, 20.0)  # upperLimitVoltage
    put_f32(115, 5.0)   # upperLimitCurrent

    out = parse_payload(ALL, bytes(payload))
    assert out["inputVoltage"] == pytest.approx(19.0)
    assert out["setVoltage"] == pytest.approx(12.0)
    assert out["setCurrent"] == pytest.approx(1.0)
    assert out["brightness"] == 5
    assert out["volume"] == 3
    assert out["meteringClosed"] is True
    assert out["outputClosed"] is True
    assert out["protectionState"] == "OVP"
    assert out["mode"] == "CC"
    assert out["upperLimitVoltage"] == pytest.approx(20.0)
    assert out["upperLimitCurrent"] == pytest.approx(5.0)
