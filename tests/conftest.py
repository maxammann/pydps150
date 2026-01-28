import os
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--dps150-port",
        action="store",
        default=os.environ.get("DPS150_PORT", "/dev/ttyACM0"),
        help="Serial port for DPS150 hardware tests (default: /dev/ttyACM0 or DPS150_PORT env var).",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "hw: marks tests as hardware/integration tests (skipped unless RUN_DPS150_HW=1)",
    )


@pytest.fixture(scope="session")
def dps150_port(pytestconfig):
    return pytestconfig.getoption("--dps150-port")


@pytest.fixture(scope="session")
def run_hw():
    return os.environ.get("RUN_DPS150_HW", "0") == "1"
