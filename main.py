from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Dict, Optional

from dps150.device import DPS150
from dps150 import protocol


def _print_update(d: Dict[str, object]) -> None:
    # one JSON per line: easy to pipe into jq / logs
    print(json.dumps(d, ensure_ascii=False), flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dps150", description="DPS150 serial CLI")
    p.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyUSB0, /dev/ttyACM0")
    p.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    p.add_argument("--timeout", type=float, default=0.2, help="Serial read timeout in seconds")
    p.add_argument("--json", action="store_true", help="Print updates as JSON lines (default)")
    p.add_argument("--pretty", action="store_true", help="Pretty-print updates")

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="Query model/hw/fw + get-all once")
    sub.add_parser("get-all", help="Request ALL block once")

    sp_set = sub.add_parser("set", help="Set a value")
    sp_set.add_argument("what", help="What to set: vset, cset, brightness, volume, ovp, ocp, opp, otp, lvp")
    sp_set.add_argument("value", help="Value (float for most, int for brightness/volume)")

    sub.add_parser("enable", help="Enable output")
    sub.add_parser("disable", help="Disable output")

    sp_met = sub.add_parser("metering", help="Enable/disable metering")
    sp_met.add_argument("state", choices=["on", "off"])

    sp_mon = sub.add_parser("monitor", help="Continuously print updates")
    sp_mon.add_argument("--duration", type=float, default=0.0, help="Seconds to run (0 = forever)")
    sp_mon.add_argument("--get-all-interval", type=float, default=1.0, help="Poll ALL every N seconds (0 disables)")

    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    def cb(d: Dict[str, object]) -> None:
        if args.pretty:
            for k, v in d.items():
                print(f"{k}: {v}")
            print("-" * 20, flush=True)
        else:
            _print_update(d)

    dev = DPS150(port=args.port, baudrate=args.baud, timeout=args.timeout, callback=cb)

    try:
        dev.open()

        if args.cmd == "info":
            # open() already queries model/hw/fw and calls get_all()
            time.sleep(0.8)
            return 0

        if args.cmd == "get-all":
            dev.get_all()
            time.sleep(0.5)
            return 0

        if args.cmd == "enable":
            dev.enable_output()
            time.sleep(0.2)
            return 0

        if args.cmd == "disable":
            dev.disable_output()
            time.sleep(0.2)
            return 0

        if args.cmd == "metering":
            if args.state == "on":
                dev.start_metering()
            else:
                dev.stop_metering()
            time.sleep(0.2)
            return 0

        if args.cmd == "set":
            name = args.what.lower()
            # map friendly names to type_ids
            float_map = {
                "vset": protocol.VOLTAGE_SET,
                "cset": protocol.CURRENT_SET,
                "ovp": protocol.OVP,
                "ocp": protocol.OCP,
                "opp": protocol.OPP,
                "otp": protocol.OTP,
                "lvp": protocol.LVP,
            }
            byte_map = {
                "brightness": protocol.BRIGHTNESS,
                "volume": protocol.VOLUME,
            }

            if name in byte_map:
                dev.set_byte(byte_map[name], int(float(args.value)))
            elif name in float_map:
                dev.set_float(float_map[name], float(args.value))
            else:
                raise SystemExit(f"Unknown 'set' target: {args.what}")

            time.sleep(0.3)
            return 0

        if args.cmd == "monitor":
            t0 = time.time()
            last_poll = 0.0
            while True:
                now = time.time()
                if args.duration > 0 and (now - t0) >= args.duration:
                    return 0

                if args.get_all_interval > 0 and (now - last_poll) >= args.get_all_interval:
                    dev.get_all()
                    last_poll = now

                time.sleep(0.05)

        return 0

    except KeyboardInterrupt:
        return 130
    finally:
        dev.close()


if __name__ == "__main__":
    raise SystemExit(main())
