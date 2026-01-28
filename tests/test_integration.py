import time
import pytest

from dps150.device import DPS150
from dps150 import protocol


@pytest.mark.hw
def test_hw_open_and_reads_info(run_hw, dps150_port):
    if not run_hw:
        pytest.skip("Set RUN_DPS150_HW=1 to run hardware tests")

    updates = []

    def cb(d):
        updates.append(d)

    dev = DPS150(port=dps150_port, callback=cb)
    dev.open()
    try:
        # open() sends model/hw/fw and get_all; give it time
        time.sleep(1.2)

        # Expect at least one of these to appear
        combined = {}
        for u in updates:
            combined.update(u)

        assert "modelName" in combined or "hardwareVersion" in combined or "firmwareVersion" in combined
    finally:
        dev.close()

@pytest.mark.hw
def test_hw_toggle_metering(run_hw, dps150_port):
    if not run_hw:
        pytest.skip("Set RUN_DPS150_HW=1 to run hardware tests")

    seen = {}

    def cb(d):
        seen.update(d)

    dev = DPS150(port=dps150_port, callback=cb)
    dev.open()
    try:
        # Turn metering on and fetch ALL
        dev.start_metering()
        time.sleep(0.2)
        dev.get_all()
        time.sleep(0.5)

        # Some firmwares report meteringClosed in ALL
        if "meteringClosed" in seen:
            assert seen["meteringClosed"] in (True, False)

        # Turn metering off again (restore)
        dev.stop_metering()
        time.sleep(0.2)
        dev.get_all()
        time.sleep(0.5)
    finally:
        dev.close()


@pytest.mark.hw
def test_hw_enable_disable_output_restores_state(run_hw, dps150_port):
    """
    Conservative: read initial outputClosed state, toggle, then restore.
    If outputClosed isn't reported by your firmware, we still exercise the commands.
    """
    if not run_hw:
        pytest.skip("Set RUN_DPS150_HW=1 to run hardware tests")

    seen = {}

    def cb(d):
        seen.update(d)

    dev = DPS150(port=dps150_port, callback=cb)
    dev.open()
    try:
        dev.get_all()
        time.sleep(0.6)
        initial = seen.get("outputClosed", None)

        # Enable output
        dev.enable_output()
        time.sleep(0.2)
        dev.get_all()
        time.sleep(0.6)
        after_enable = seen.get("outputClosed", None)

        # Disable output
        dev.disable_output()
        time.sleep(2.0)
        dev.get_all()
        time.sleep(2.0)
        after_disable = seen.get("outputClosed", None)

        # If we have a readable state, make sure "disable" results in closed=True
        if after_disable is not None:
            assert after_disable is True

        # Restore initial state if known
        if initial is False:
            dev.enable_output()
        else:
            dev.disable_output()

    finally:
        dev.close()


@pytest.mark.hw
@pytest.mark.parametrize(
    "type_id,value",
    [
        (protocol.VOLTAGE_SET, 5.0),
        (protocol.CURRENT_SET, 0.5),
    ],
)
def test_hw_set_float_then_readback_from_all(run_hw, dps150_port, type_id, value):
    """
    Sets a float register and expects ALL to reflect it as setVoltage/setCurrent.
    Some firmwares may not reflect immediately; we poll a bit.
    """
    if not run_hw:
        pytest.skip("Set RUN_DPS150_HW=1 to run hardware tests")

    seen = {}

    def cb(d):
        seen.update(d)

    dev = DPS150(port=dps150_port, callback=cb)
    dev.open()
    try:
        # Set value
        dev.set_float(type_id, value)
        time.sleep(0.2)

        # Poll ALL for up to ~2 seconds
        key = "setVoltage" if type_id == protocol.VOLTAGE_SET else "setCurrent"
        ok = False
        for _ in range(8):
            dev.get_all()
            time.sleep(0.25)
            if key in seen and abs(seen[key] - value) < 0.2:
                ok = True
                break

        assert ok, f"Did not see {key}≈{value} in ALL. Last seen: {seen.get(key)}"
    finally:
        dev.close()
