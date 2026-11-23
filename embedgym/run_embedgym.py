#!/usr/bin/env python3
"""Run the supported subset of EmbedGym-Bench on CircuitTwin (`ct`).

Standard library only. Evaluates real EmbedGym agent firmware binaries (.hex)
from the pinned upstream dataset (both passing controls and failing negative
controls) against EmbedGym's exact upstream timed test vectors using
CircuitTwin's AVR twins, electrical layer, analog circuit solver, and catalog
I2C sensor twins (MPU6050, VL53L0X).

Usage:
  python embedgym/run_embedgym.py --ct <path/to/ct.exe> --cache D:/ct/tmp/embedgym-upstream --out out/embedgym
"""
import argparse
import concurrent.futures
import datetime
import gzip
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
PIN_PATH = os.path.join(HERE, "upstream-pin.json")

# Official Arduino Uno (ATmega328P) pin -> AVR port pin mapping
UNO_PINS = {
    "0": "PD0", "1": "PD1", "2": "PD2", "3": "PD3", "4": "PD4", "5": "PD5",
    "6": "PD6", "7": "PD7", "8": "PB0", "9": "PB1", "10": "PB2", "11": "PB3",
    "12": "PB4", "13": "PB5",
    "A0": "PC0", "A1": "PC1", "A2": "PC2", "A3": "PC3", "A4": "PC4", "A5": "PC5",
}

# Official Arduino Mega 2560 (ATmega2560) pin -> AVR port pin mapping
MEGA_PINS = {
    "0": "PE0", "1": "PE1", "2": "PE4", "3": "PE5", "4": "PG5", "5": "PE3",
    "6": "PH3", "7": "PH4", "8": "PH5", "9": "PH6", "10": "PB4", "11": "PB5",
    "12": "PB6", "13": "PB7", "14": "PJ1", "15": "PJ0", "16": "PH1", "17": "PH0",
    "18": "PD3", "19": "PD2", "20": "PD1", "21": "PD0", "22": "PA0", "23": "PA1",
    "24": "PA2", "25": "PA3", "26": "PA4", "27": "PA5", "28": "PA6", "29": "PA7",
    "30": "PC7", "31": "PC6", "32": "PC5", "33": "PC4", "34": "PC3", "35": "PC2",
    "36": "PC1", "37": "PC0", "38": "PD7", "39": "PG2", "40": "PG1", "41": "PG0",
    "42": "PL7", "43": "PL6", "44": "PL5", "45": "PL4", "46": "PL3", "47": "PL2",
    "48": "PL1", "49": "PL0", "50": "PB3", "51": "PB2", "52": "PB1", "53": "PB0",
    "A0": "PF0", "A1": "PF1", "A2": "PF2", "A3": "PF3", "A4": "PF4", "A5": "PF5",
    "A6": "PF6", "A7": "PF7", "A8": "PK0", "A9": "PK1", "A10": "PK2", "A11": "PK3",
    "A12": "PK4", "A13": "PK5", "A14": "PK6", "A15": "PK7",
}

TARGET_META = {
    "atmega328p_arduino": {
        "board": "arduino-uno",
        "mcu": "ATmega328P",
        "pins": UNO_PINS,
        "udr0_addr": "0x8000C6:1",
        "console_pins": [
            {"name": "CONSOLE_RX", "pin": "PD0", "kind": "header", "activeHigh": True},
            {"name": "CONSOLE_TX", "pin": "PD1", "kind": "header", "activeHigh": True},
        ],
    },
    "atmega2560_arduino": {
        "board": "arduino-mega2560",
        "mcu": "ATmega2560",
        "pins": MEGA_PINS,
        "udr0_addr": "0x8000C6:1",
        "console_pins": [
            {"name": "CONSOLE_RX", "pin": "PE0", "kind": "header", "activeHigh": True},
            {"name": "CONSOLE_TX", "pin": "PE1", "kind": "header", "activeHigh": True},
        ],
    },
}

# Upstream EmbedGym BounceButton.ts bounce offsets (seconds -> ns)
BOUNCE_OFFSETS_NS = [1_500_000, 3_000_000, 4_000_000, 4_800_000]
# Upstream EmbedGym Ky038SoundSensor.ts chatter offsets on rising edge (ns)
KY038_CHATTER_NS = [12_000_000, 24_000_000]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def git_state(repo_dir):
    def git(*args):
        try:
            p = subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True, check=False)
            return p.stdout.strip() if p.returncode == 0 else None
        except OSError:
            return None
    rev = git("rev-parse", "HEAD")
    if not rev:
        return None
    return {"revision": rev, "dirtyTree": bool(git("status", "--porcelain"))}


def make_scrubber(pairs):
    rules = []
    for path, name in sorted((p for p in pairs if p[0]), key=lambda p: -len(p[0])):
        path = path.rstrip("/\\")
        for variant in {path.replace("\\", "/"), path.replace("/", "\\")}:
            rules.append((re.compile(re.escape(variant) + r"([/\\])?", re.I),
                          lambda m, n=name: n + ("/" if m.group(1) else "")))

    def scrub(value):
        if isinstance(value, str):
            for rx, sub in rules:
                value = rx.sub(sub, value)
            return value
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        return value
    return scrub


def map_pin(target, raw_pin):
    s = str(raw_pin).strip()
    if s.startswith("D") and s[1:].isdigit():
        s = s[1:]
    m = TARGET_META[target]["pins"]
    if s not in m:
        raise ValueError(f"Unmapped Arduino pin {raw_pin!r} for {target}")
    return m[s]


def sen0244_tds_to_volts(tds_ppm):
    """Exact inverse of DFRobot Gravity SEN0244 formula:
       tds = (133.42*v^3 - 255.86*v^2 + 857.39*v) * 0.5
    Monotonically increasing on [0, 2.5 V]."""
    if tds_ppm <= 0:
        return 0.0
    lo, hi = 0.0, 2.6
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        val = (133.42 * mid * mid * mid - 255.86 * mid * mid + 857.39 * mid) * 0.5
        if val < tds_ppm:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def parse_wire_pins(target, variant):
    """Return {componentId: {compPinName: boardPinName}} for wires attached to the MCU board."""
    board_ids = {b["id"] for b in variant["circuit"].get("boards", [])}
    out = {}
    for w in variant["circuit"].get("wires", []):
        s, e = w["start"], w["end"]
        if s["componentId"] in board_ids and e["componentId"] not in board_ids:
            out.setdefault(e["componentId"], {})[e["pinName"]] = s["pinName"]
        elif e["componentId"] in board_ids and s["componentId"] not in board_ids:
            out.setdefault(s["componentId"], {})[s["pinName"]] = e["pinName"]
    return out


def find_component_for_binding(variant, part, bind_pin):
    """Find the circuit component id matching a test binding (part, pin)."""
    board_ids = {b["id"] for b in variant["circuit"].get("boards", [])}
    bpin = str(bind_pin)
    if bpin.startswith("D") and bpin[1:].isdigit():
        bpin = bpin[1:]
    cands = [c for c in variant["circuit"].get("components", []) if c.get("metadataId") == part]
    if len(cands) == 1:
        return cands[0]["id"]
    for c in cands:
        cid = c["id"]
        for w in variant["circuit"].get("wires", []):
            s, e = w["start"], w["end"]
            if s["componentId"] == cid and e["componentId"] in board_ids and e["pinName"] == bpin:
                return cid
            if e["componentId"] == cid and s["componentId"] in board_ids and s["pinName"] == bpin:
                return cid
    return cands[0]["id"] if cands else None


def build_task_artifacts(target, task_doc, work_dir):
    """Build board/scenario files and observer metadata for one (target, task).

    Returns dict with keys: board_arg, scenario_path, signals, max_ms, bindings,
    tests, has_uart_parse.
    """
    variant = task_doc["variants"][target]
    tests = variant["tests"]
    tmeta = TARGET_META[target]
    comp_wires = parse_wire_pins(target, variant)

    # Extract target bindings: name -> {part, pin, mcu_pin, comp_id, pins_map}
    bindings = {}
    for row in tests:
        if row.get("target") == target:
            name = row["name"]
            part = row["part"]
            raw_pin = row["pin"]
            mcu_pin = map_pin(target, raw_pin)
            cid = find_component_for_binding(variant, part, raw_pin)
            bindings[name] = {
                "part": part,
                "raw_pin": str(raw_pin),
                "mcu_pin": mcu_pin,
                "comp_id": cid,
                "comp_wires": comp_wires.get(cid, {}) if cid else {},
            }

    actions = [row for row in tests if "at" in row]
    max_at_ms = max((row["at"] for row in actions), default=1000)
    max_ms = max_at_ms + 150
    has_uart_parse = any("parse" in row for row in actions)

    # Collect VCD signals to observe (output LEDs, buzzers, relays, lasers, plus input pins)
    vcd_pins = set()
    for b in bindings.values():
        if b["part"] in ("led", "buzzer", "active-buzzer", "relay-module", "ky-008"):
            vcd_pins.add(b["mcu_pin"])

    # Build I2C board file if MPU6050 or VL53L0X is present
    board_devices = []
    streams = []
    for name, b in bindings.items():
        if b["part"] == "mpu6050":
            board_devices.append({
                "instance": name,
                "twin": {"part": "MPU6050"},
                "attachments": [{"kind": "i2c", "bus": "TWI", "address": 104}],
            })
        elif b["part"] == "vl53l0x":
            board_devices.append({
                "instance": name,
                "twin": {"part": "VL53L0X"},
                "attachments": [{"kind": "i2c", "bus": "TWI", "address": 41}],
            })

    if board_devices:
        board_doc = {
            "schemaVersion": "ct.board/1",
            "id": f"{tmeta['board']}-{task_doc['id']}",
            "name": f"{tmeta['board']} + {task_doc['id']}",
            "mcu": {"part": tmeta["mcu"]},
            "clocks": {"hseHz": 16000000, "hseBypass": False},
            "consoles": [{"name": "console", "port": "USART0"}],
            "devices": board_devices,
            "pins": tmeta["console_pins"],
        }
        board_arg = os.path.join(work_dir, f"board_{target}_{task_doc['id']}.json")
        open(board_arg, "w", encoding="utf-8").write(json.dumps(board_doc, indent=2))
    else:
        board_arg = tmeta["board"]

    # Collect timeline of stimuli for digital drivers, analog sources, and I2C streams
    elec_nets = {}      # mcu_pin -> net config
    elec_drivers = {}   # name -> {pin, steps: [(t_ns, state)]}
    analog_series = {}  # mcu_pin -> [(t_ns, volts)]
    i2c_series = {}     # (dev, port) -> [(t_ns, val_dict)]

    # Track stateful sensor defaults
    mq2_state = {}      # name -> {"voltage": 0.0, "threshold": 2.5, "do_pin": str|None}
    btn_polarity = {}   # name -> (idle_state, active_state)

    for name, b in bindings.items():
        part = b["part"]
        pin = b["mcu_pin"]
        cw = b["comp_wires"]
        if part in ("pushbutton", "bounce-button"):
            # Check if button connects to 5V (active-high with pull-down) or GND (active-low)
            vals = set(cw.values())
            active_high = ("5V" in vals) or ("3.3V" in vals) or ("GND" not in vals)
            idle_st = "low" if active_high else "high"
            act_st = "high" if active_high else "low"
            btn_polarity[name] = (idle_st, act_st)
            elec_nets[pin] = {"pin": pin, "rail": "VCC", "pulls": [{"ohms": 10000.0}]}
            elec_drivers[name] = {"pin": pin, "steps": [(0, idle_st)]}
        elif part == "pir-motion-sensor":
            elec_nets[pin] = {"pin": pin, "rail": "VCC"}
            elec_drivers[name] = {"pin": pin, "steps": [(0, "low")]}
        elif part == "ky-020-tilt-switch":
            elec_nets[pin] = {"pin": pin, "rail": "VCC"}
            elec_drivers[name] = {"pin": pin, "steps": [(0, "low")]}
        elif part == "ky-038-sound-sensor":
            elec_nets[pin] = {"pin": pin, "rail": "VCC"}
            elec_drivers[name] = {"pin": pin, "steps": [(0, "low")]}
        elif part == "tmp36":
            analog_series[pin] = [(0, 0.75)]  # default 25 C
        elif part == "ky-018-photoresistor":
            analog_series[pin] = [(0, 5.0 * (1.0 - 512.0 / 1023.0))]
        elif part == "sen0244":
            analog_series[pin] = [(0, 0.0)]
        elif part == "joystick":
            analog_series[pin] = [(0, 5.0 * 512.0 / 1023.0)]
        elif part == "mq2":
            ao_raw = cw.get("AO", b["raw_pin"])
            ao_pin = map_pin(target, ao_raw)
            do_raw = cw.get("DO")
            do_pin = map_pin(target, do_raw) if do_raw else None
            mq2_state[name] = {"voltage": 0.0, "threshold": 2.5, "ao_pin": ao_pin, "do_pin": do_pin}
            analog_series[ao_pin] = [(0, 0.0)]
            if do_pin:
                elec_nets[do_pin] = {"pin": do_pin, "rail": "VCC"}
                elec_drivers[f"{name}_do"] = {"pin": do_pin, "steps": [(0, "high")]}
        elif part == "mpu6050":
            # Upstream EmbedGym models/mpu6050.json defaults accelZ to +1g (16384 LSB) at rest.
            i2c_series[(name, "acceleration.z.accel_zout")] = [(0, {"raw": 16384})]
            i2c_series[(name, "angular_rate.x.gyro_xout")] = [(0, {"raw": 0})]
        elif part == "vl53l0x":
            i2c_series[(name, "distance.result_range_mm")] = [(0, {"si": 0.25})]

    # Process test actions (`do` and `set`) in chronological order
    # Group simultaneous actions at the same `at` ms so mq2 voltage+threshold update atomically
    by_at = {}
    for row in actions:
        by_at.setdefault(row["at"], []).append(row)

    for at_ms in sorted(by_at.keys()):
        t_ns = int(at_ms) * 1_000_000
        mq2_touched = set()
        for row in by_at[at_ms]:
            if "do" in row:
                obj, act = row["do"].split(".", 1)
                b = bindings[obj]
                idle_st, act_st = btn_polarity[obj]
                new_st = act_st if act == "down" else idle_st
                old_st = idle_st if act == "down" else act_st
                steps = elec_drivers[obj]["steps"]
                if b["part"] == "bounce-button":
                    steps.append((t_ns, new_st))
                    steps.append((t_ns + BOUNCE_OFFSETS_NS[0], old_st))
                    steps.append((t_ns + BOUNCE_OFFSETS_NS[1], new_st))
                    steps.append((t_ns + BOUNCE_OFFSETS_NS[2], old_st))
                    steps.append((t_ns + BOUNCE_OFFSETS_NS[3], new_st))
                else:
                    steps.append((t_ns, new_st))
            if "set" in row:
                lhs, rhs = [x.strip() for x in row["set"].split("=", 1)]
                obj, prop = lhs.split(".", 1)
                if rhs.lower() == "true":
                    val = True
                elif rhs.lower() == "false":
                    val = False
                else:
                    val = float(rhs)
                b = bindings[obj]
                part = b["part"]
                pin = b["mcu_pin"]
                if part == "pir-motion-sensor" and prop == "trigger":
                    if bool(val):
                        # Upstream HC-SR501 PIR sensor outputs a 3000 ms monostable HIGH pulse on trigger.
                        elec_drivers[obj]["steps"].append((t_ns, "high"))
                        elec_drivers[obj]["steps"].append((t_ns + 3_000_000_000, "low"))
                    else:
                        elec_drivers[obj]["steps"].append((t_ns, "low"))
                elif part == "ky-020-tilt-switch" and prop == "tilted":
                    elec_drivers[obj]["steps"].append((t_ns, "high" if bool(val) else "low"))
                elif part == "ky-038-sound-sensor" and prop == "soundLevel":
                    steps = elec_drivers[obj]["steps"]
                    prev_high = steps[-1][1] == "high"
                    now_high = float(val) > 512.0
                    if now_high and not prev_high:
                        steps.append((t_ns, "high"))
                        steps.append((t_ns + KY038_CHATTER_NS[0], "low"))
                        steps.append((t_ns + KY038_CHATTER_NS[1], "high"))
                    elif not now_high and prev_high:
                        steps.append((t_ns, "low"))
                elif part == "tmp36" and prop == "temperature":
                    analog_series[pin].append((t_ns, 0.5 + 0.01 * float(val)))
                elif part == "ky-018-photoresistor" and prop == "lightLevel":
                    analog_series[pin].append((t_ns, 5.0 * (1.0 - float(val) / 1023.0)))
                elif part == "sen0244" and prop == "tds":
                    analog_series[pin].append((t_ns, sen0244_tds_to_volts(float(val))))
                elif part == "joystick" and prop in ("x", "y"):
                    analog_series[pin].append((t_ns, 5.0 * float(val) / 1023.0))
                elif part == "mq2":
                    st = mq2_state[obj]
                    if prop == "voltage":
                        st["voltage"] = float(val)
                        analog_series[st["ao_pin"]].append((t_ns, float(val)))
                    elif prop == "threshold":
                        st["threshold"] = float(val)
                    mq2_touched.add(obj)
                elif part == "mpu6050":
                    if prop == "accelZ":
                        i2c_series[(obj, "acceleration.z.accel_zout")].append(
                            (t_ns, {"raw": int(round(float(val) * 16384.0))})
                        )
                    elif prop == "accelX":
                        i2c_series.setdefault((obj, "acceleration.x.accel_xout"), [(0, {"raw": 0})]).append(
                            (t_ns, {"raw": int(round(float(val) * 16384.0))})
                        )
                    elif prop == "accelY":
                        i2c_series.setdefault((obj, "acceleration.y.accel_yout"), [(0, {"raw": 0})]).append(
                            (t_ns, {"raw": int(round(float(val) * 16384.0))})
                        )
                    elif prop == "gyroX":
                        i2c_series[(obj, "angular_rate.x.gyro_xout")].append(
                            (t_ns, {"raw": int(round(float(val) * 131.0))})
                        )
                elif part == "vl53l0x" and prop == "distance":
                    i2c_series[(obj, "distance.result_range_mm")].append(
                        (t_ns, {"si": float(val) / 1000.0})
                    )
        for obj in mq2_touched:
            st = mq2_state[obj]
            if st["do_pin"]:
                do_state = "low" if st["voltage"] > st["threshold"] else "high"
                elec_drivers[f"{obj}_do"]["steps"].append((t_ns, do_state))

    # Deduplicate same-timestamp points (keep last value at any given t_ns)
    def dedup_series(pts):
        d = {}
        for t, v in pts:
            d[t] = v
        return sorted(d.items(), key=lambda x: x[0])

    # Build ct.scenario/1 if any digital drivers, analog sources, or I2C streams are needed
    scenario_path = None
    if elec_drivers or analog_series or i2c_series:
        scen = {
            "schemaVersion": "ct.scenario/1",
            "id": f"eg-{target}-{task_doc['id']}",
            "name": f"EmbedGym {target} {task_doc['id']}",
            "durationNs": int(max_ms) * 1_000_000,
            "physicsStepNs": 10_000_000,
        }
        if elec_drivers or analog_series:
            elements = []
            analog_nets = []
            for idx, (pin, pts) in enumerate(sorted(analog_series.items())):
                clean = dedup_series(pts)
                node = f"n_a{idx}"
                elements.append({
                    "kind": "voltage_source",
                    "name": f"V_{pin}",
                    "nodes": [node, "gnd"],
                    "volts": {
                        "kind": "keyframes",
                        "interpolation": "hold",
                        "points": [{"tNs": t, "value": v} for t, v in clean],
                    },
                })
                elements.append({
                    "kind": "resistor",
                    "name": f"R_{pin}",
                    "nodes": [node, "gnd"],
                    "ohms": 100000.0,
                })
                analog_nets.append({"net": pin, "node": node})
            if not elements:
                # ct.scenario/1 requires non-empty circuit.elements when circuit is present
                elements.append({"kind": "resistor", "name": "R_REF", "nodes": ["n_ref", "gnd"], "ohms": 10000.0})
            circuit = {
                "stepNs": 10_000_000,
                "elements": elements,
            }
            if analog_nets:
                circuit["analogNets"] = analog_nets
            if elec_drivers:
                drivers_out = []
                for dname, dspec in sorted(elec_drivers.items()):
                    clean_steps = dedup_series(dspec["steps"])
                    drivers_out.append({
                        "name": dname,
                        "pin": dspec["pin"],
                        "kind": "push_pull",
                        "steps": [{"tNs": t, "state": st} for t, st in clean_steps],
                    })
                circuit["electrical"] = {
                    "rails": [{"name": "VCC", "volts": 5.0}],
                    "mcuRail": "VCC",
                    "nets": list(elec_nets.values()),
                    "drivers": drivers_out,
                }
            scen["circuit"] = circuit
        if i2c_series:
            scen["streams"] = []
            for (dev, port), pts in sorted(i2c_series.items()):
                clean = dedup_series(pts)
                scen["streams"].append({
                    "target": {"device": dev, "port": port},
                    "interpolation": "hold",
                    "samples": [{"tNs": t, "value": v} for t, v in clean],
                })
        scenario_path = os.path.join(work_dir, f"scen_{target}_{task_doc['id']}.json")
        open(scenario_path, "w", encoding="utf-8").write(json.dumps(scen, indent=2))

    return {
        "board_arg": board_arg,
        "scenario_path": scenario_path,
        "vcd_pins": sorted(vcd_pins),
        "max_ms": max_ms,
        "bindings": bindings,
        "actions": actions,
        "has_uart_parse": has_uart_parse,
    }


def parse_vcd(vcd_path):
    """Parse VCD into {net_name: [(t_ns, int_level), ...]}."""
    if not vcd_path or not os.path.isfile(vcd_path):
        return {}
    code_to_name = {}
    traces = {}
    t_ns = 0
    in_defs = True
    with open(vcd_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if in_defs:
                if line.startswith("$var "):
                    parts = line.split()
                    code = parts[3]
                    name = parts[4]
                    code_to_name[code] = name
                    traces[name] = []
                elif line.startswith("$enddefinitions"):
                    in_defs = False
                continue
            if line.startswith("#"):
                t_ns = int(line[1:])
            elif line[0] in ("0", "1"):
                lvl = 1 if line[0] == "1" else 0
                code = line[1:]
                name = code_to_name.get(code)
                if name is not None:
                    tr = traces[name]
                    if not tr or tr[-1][1] != lvl:
                        tr.append((t_ns, lvl))
    return traces


def pin_level_at(trace, at_ns):
    lvl = 0
    for t, v in trace:
        if t <= at_ns:
            lvl = v
        else:
            break
    return bool(lvl)


def pin_brightness_at(trace, at_ns, window_ns=5_000_000):
    """Fraction of time pin was HIGH in [max(0, at_ns - window_ns), at_ns].
    5 ms spans ~2.5-5 Arduino AVR PWM periods (490/980 Hz) without smearing 50 ms blink checks."""
    w0 = max(0, at_ns - window_ns)
    w1 = at_ns
    if w1 <= w0:
        return 1.0 if pin_level_at(trace, at_ns) else 0.0
    cur_t = w0
    cur_v = 1 if pin_level_at(trace, w0) else 0
    high_ns = 0
    for t, v in trace:
        if t <= w0:
            continue
        if t >= w1:
            break
        if cur_v:
            high_ns += (t - cur_t)
        cur_t = t
        cur_v = v
    if cur_v:
        high_ns += (w1 - cur_t)
    return high_ns / float(w1 - w0)


def pin_edges_in_window(trace, w0, w1):
    return [(t, v) for t, v in trace if w0 <= t <= w1]


def buzzer_metrics_at(trace, at_ns):
    """Compute hasSignal, frequency (Hz), and pulseRate around at_ns."""
    edges_50 = pin_edges_in_window(trace, max(0, at_ns - 50_000_000), at_ns)
    has_sig = len(edges_50) >= 4

    edges_100 = pin_edges_in_window(trace, max(0, at_ns - 100_000_000), at_ns)
    rises = [t for t, v in edges_100 if v == 1]
    if len(rises) >= 2:
        dts = [rises[i + 1] - rises[i] for i in range(len(rises) - 1) if rises[i + 1] > rises[i]]
        dts.sort()
        med_dt = dts[len(dts) // 2] if dts else 0
        freq = (1e9 / med_dt) if med_dt > 0 else 0.0
    else:
        freq = 0.0

    # Pulse rate: count distinct tone bursts in [max(0, at_ns - 400ms), at_ns]
    # A gap > 10 ms between consecutive edges separates distinct bursts.
    edges_400 = pin_edges_in_window(trace, max(0, at_ns - 400_000_000), at_ns)
    if len(edges_400) < 2:
        pulse_rate = 0
    else:
        bursts = 1
        for i in range(1, len(edges_400)):
            if edges_400[i][0] - edges_400[i - 1][0] > 10_000_000:
                bursts += 1
        pulse_rate = bursts

    return {"hasSignal": has_sig, "frequency": freq, "pulseRate": pulse_rate}


def parse_udr0_lines(mem_trace_path):
    """Reconstruct timestamped serial lines [(t_ms, line_str), ...] from UDR0 writes."""
    if not mem_trace_path or not os.path.isfile(mem_trace_path):
        return []
    lines = []
    buf = bytearray()
    last_t_ns = 0
    with open(mem_trace_path, encoding="utf-8", errors="replace") as f:
        for idx, raw in enumerate(f):
            if idx == 0:
                continue  # header line
            raw = raw.strip()
            if not raw:
                continue
            rec = json.loads(raw)
            if not rec.get("write"):
                continue
            b = int(rec["value"]) & 0xFF
            t_ns = int(rec["tNs"])
            last_t_ns = t_ns
            if b == 0x0A:  # '\n'
                text = buf.decode("utf-8", "replace").rstrip("\r")
                lines.append((t_ns / 1e6, text))
                buf.clear()
            elif b != 0x0D:
                buf.append(b)
    if buf:
        lines.append((last_t_ns / 1e6, buf.decode("utf-8", "replace").rstrip("\r")))
    return lines


def compile_embedgym_parse_template(tmpl):
    """Compile EmbedGym parse template like 'Humidity: {hum:f.1} Temp: {temp:f.1} C'
    or 'aX: {d} aY: {d} aZ: {az:d}' into (regex, [(var_name, converter), ...])."""
    fields = []
    parts = []
    pos = 0
    for m in re.finditer(r"\{([^}]+)\}", tmpl):
        parts.append(re.escape(tmpl[pos:m.start()]))
        spec = m.group(1)
        if ":" in spec:
            vname, fmt = spec.split(":", 1)
        else:
            vname, fmt = None, spec
        if fmt == "d":
            parts.append(r"([+-]?\d+)")
            conv = int
        elif fmt.startswith("f"):
            parts.append(r"([+-]?\d+(?:\.\d+)?)")
            conv = float
        elif fmt == "s":
            parts.append(r"(\S+)")
            conv = str
        else:
            parts.append(r"(\S+)")
            conv = str
        fields.append((vname, conv))
        pos = m.end()
    parts.append(re.escape(tmpl[pos:]))
    return re.compile("".join(parts)), fields


class _AttrObj:
    def __init__(self, d):
        self._d = d

    def __getattr__(self, k):
        if k in self._d:
            return self._d[k]
        raise AttributeError(k)


def translate_expr(expr):
    """Translate EmbedGym JS-like test expression into Python expression."""
    s = expr
    # Replace @name.t with _T['name'] and @name with _V['name']
    s = re.sub(r"@([A-Za-z_][A-Za-z0-9_]*)\.t\b", r"_T['\1']", s)
    s = re.sub(r"@([A-Za-z_][A-Za-z0-9_]*)\b", r"_V['\1']", s)
    s = s.replace("&&", " and ").replace("||", " or ")
    s = re.sub(r"(?<![=!<>])!(?!=)", " not ", s)
    s = re.sub(r"\btrue\b", "True", s)
    s = re.sub(r"\bfalse\b", "False", s)
    s = s.replace("Math.abs", "abs").replace("Math.max", "max").replace("Math.min", "min")
    return s


def evaluate_embedgym_tests(spec, vcd_traces, serial_lines):
    """Evaluate all upstream EmbedGym test assertions against CircuitTwin traces."""
    bindings = spec["bindings"]
    actions = spec["actions"]

    vars_v = {}  # var -> list or scalar
    vars_t = {}  # var -> list of ms timestamps

    def hw_env(at_ms):
        at_ns = int(at_ms) * 1_000_000
        env = {"_V": vars_v, "_T": vars_t, "len": len, "abs": abs, "min": min, "max": max}
        for name, b in bindings.items():
            part = b["part"]
            pin_key = f"pin.{b['mcu_pin']}"
            tr = vcd_traces.get(pin_key, [])
            if part == "led":
                val = pin_level_at(tr, at_ns)
                bri = pin_brightness_at(tr, at_ns)
                env[name] = _AttrObj({"value": val, "brightness": bri})
            elif part == "relay-module":
                val = pin_level_at(tr, at_ns)
                env[name] = _AttrObj({"energized": val, "value": val})
            elif part == "ky-008":
                val = pin_level_at(tr, at_ns)
                env[name] = _AttrObj({"laserOn": val, "value": val})
            elif part in ("buzzer", "active-buzzer"):
                bm = buzzer_metrics_at(tr, at_ns)
                env[name] = _AttrObj(bm)
        return env

    results = []
    for row in actions:
        at_ms = row["at"]
        if "parse" in row:
            tmpl = row["parse"]
            alias = row.get("as")
            lines_so_far = [(t, ln) for t, ln in serial_lines if t <= at_ms]
            if alias:
                vals = []
                ts = []
                for t, ln in lines_so_far:
                    if ln.strip().startswith(tmpl):
                        vals.append(ln)
                        ts.append(t)
                vars_v[alias] = vals
                vars_t[alias] = ts
            else:
                rx, fields = compile_embedgym_parse_template(tmpl)
                tmp_v = {vn: [] for vn, _ in fields if vn}
                tmp_t = {vn: [] for vn, _ in fields if vn}
                for t, ln in lines_so_far:
                    m = rx.search(ln)
                    if m:
                        for idx, (vn, conv) in enumerate(fields, 1):
                            if vn:
                                tmp_v[vn].append(conv(m.group(idx)))
                                tmp_t[vn].append(t)
                for vn in tmp_v:
                    vars_v[vn] = tmp_v[vn]
                    vars_t[vn] = tmp_t[vn]
        if "capture" in row:
            lhs, rhs = [x.strip() for x in row["capture"].split("=", 1)]
            py_expr = translate_expr(rhs)
            try:
                val = eval(py_expr, {"__builtins__": {}}, hw_env(at_ms))
                vars_v[lhs] = val
            except Exception as e:
                results.append({"at": at_ms, "capture": row["capture"], "passed": False, "error": str(e)})
        if "expect" in row:
            py_expr = translate_expr(row["expect"])
            try:
                ok = bool(eval(py_expr, {"__builtins__": {}}, hw_env(at_ms)))
                results.append({"at": at_ms, "expect": row["expect"], "passed": ok})
            except Exception as e:
                results.append({"at": at_ms, "expect": row["expect"], "passed": False, "error": str(e)})

    passed_n = sum(1 for r in results if r["passed"])
    failed_list = [r for r in results if not r["passed"]]
    return {
        "totalAssertions": len(results),
        "passedAssertions": passed_n,
        "failedAssertions": len(failed_list),
        "allPassed": len(results) > 0 and len(failed_list) == 0,
        "failures": failed_list[:10],
    }


def run_one_case(ct_exe, cache_dir, item, env, wall_timeout_s, scrub):
    target = item["target"]
    task_id = item["task"]
    run_id = item["id"]
    eg_verdict = item["verdict"]
    tmeta = TARGET_META[target]

    task_doc = json.load(open(os.path.join(cache_dir, "tasks", f"{task_id}.json"), encoding="utf-8"))
    run_gz = os.path.join(cache_dir, "runs", f"{run_id}.json.gz")
    run_obj = json.loads(gzip.decompress(open(run_gz, "rb").read()))
    hex_text = run_obj.get("hex")
    if not hex_text:
        return {
            "runId": run_id,
            "target": target,
            "task": task_id,
            "embedgymVerdict": eg_verdict,
            "ctVerdict": "error",
            "evalVerdict": "error",
            "agreed": False,
            "error": "missing hex in upstream run archive",
        }

    hex_bytes = hex_text.encode("utf-8")
    hex_sha256 = sha256_bytes(hex_bytes)

    with tempfile.TemporaryDirectory(prefix="eg_ct_") as tmp:
        hex_path = os.path.join(tmp, f"{task_id}.hex")
        open(hex_path, "wb").write(hex_bytes)

        spec = build_task_artifacts(target, task_doc, tmp)
        vcd_path = os.path.join(tmp, "signals.vcd") if spec["vcd_pins"] else None
        mt_path = os.path.join(tmp, "udr0.jsonl") if spec["has_uart_parse"] else None

        cmd = [
            ct_exe, "--json", "run", hex_path,
            "--board", spec["board_arg"],
            "--max-ms", str(spec["max_ms"]),
        ]
        if spec["scenario_path"]:
            cmd += ["--scenario", spec["scenario_path"]]
        if vcd_path:
            cmd += ["--vcd", vcd_path, "--signals", ",".join(f"pin.{p}" for p in spec["vcd_pins"])]
        if mt_path:
            cmd += ["--mem-trace", mt_path, "--trace-format", "jsonl", "--mem-range", tmeta["udr0_addr"]]

        t0 = time.monotonic()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=wall_timeout_s, env=env)
            rc = proc.returncode
            out, err = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            rc, out, err = None, "", f"wall timeout after {wall_timeout_s}s"
        elapsed_ms = int(round((time.monotonic() - t0) * 1000))

        ct_doc = None
        if out:
            pos = out.find("{")
            if pos >= 0:
                try:
                    ct_doc = json.loads(out[pos:])
                except ValueError:
                    ct_doc = None

        ct_verdict = (ct_doc or {}).get("verdict") or "error"
        ct_stats = (ct_doc or {}).get("stats") or {}
        ct_issues = [
            {"code": i.get("code"), "severity": i.get("severity"), "message": scrub(str(i.get("message", "")))[:200]}
            for i in (ct_doc or {}).get("issues", [])
            if i.get("severity") != "info"
        ]
        ct_error = (ct_doc or {}).get("error")

        if ct_verdict in ("pass", "inconclusive") and ct_doc is not None:
            vcd_traces = parse_vcd(vcd_path)
            serial_lines = parse_udr0_lines(mt_path)
            grading = evaluate_embedgym_tests(spec, vcd_traces, serial_lines)
            if not grading["allPassed"]:
                eval_verdict = "fail"
            elif ct_verdict == "inconclusive":
                eval_verdict = "inconclusive"
            else:
                eval_verdict = "pass"
        else:
            grading = {
                "totalAssertions": sum(1 for a in spec["actions"] if "expect" in a),
                "passedAssertions": 0,
                "failedAssertions": 0,
                "allPassed": False,
                "failures": [],
            }
            eval_verdict = "error" if ct_verdict == "error" else "fail"

        agreed = (eval_verdict == eg_verdict)
        return {
            "runId": run_id,
            "target": target,
            "ctBoard": tmeta["board"],
            "task": task_id,
            "model": item["model"],
            "mode": item["mode"],
            "firmwareSha256": hex_sha256,
            "embedgymVerdict": eg_verdict,
            "embedgymGradeSummary": run_obj.get("gradeSummary"),
            "embedgymFailing": (run_obj.get("failing") or [])[:5],
            "ctExit": rc,
            "ctVerdict": ct_verdict,
            "evalVerdict": eval_verdict,
            "agreed": agreed,
            "grading": grading,
            "stats": {
                "instructions": ct_stats.get("instructions"),
                "virtualTimeNs": ct_stats.get("virtualTimeNs"),
                "ctWallMs": ct_stats.get("wallMs"),
                "harnessWallMs": elapsed_ms,
            },
            "digests": {
                "finalState": ((ct_doc or {}).get("digests") or {}).get("finalState"),
                "inputs": ((ct_doc or {}).get("digests") or {}).get("inputs"),
            },
            "engineRevision": ((ct_doc or {}).get("engine") or {}).get("revision"),
            "nonInfoIssues": ct_issues[:8],
            "error": scrub(str(ct_error))[:300] if ct_error else (scrub(err)[-300:] if rc not in (0, 1) else None),
        }


def build_coverage_audit(pin, cache_dir):
    """Explicitly account for all 117 task specs and 598 task instances."""
    catalog = json.load(open(os.path.join(cache_dir, "catalog.json"), encoding="utf-8"))
    supported_by_cat = pin["supportedTasks"]
    task_to_cat = {tid: cat for cat, tids in supported_by_cat.items() for tid in tids}

    # CircuitTwin catalog parts & built-in pin models
    ct_supported_parts = {
        "led", "pushbutton", "bounce-button", "buzzer", "active-buzzer", "relay-module",
        "ky-008", "pir-motion-sensor", "ky-020-tilt-switch", "ky-038-sound-sensor",
        "tmp36", "ky-018-photoresistor", "mq2", "sen0244", "joystick",
        "mpu6050", "vl53l0x",
    }

    skipped_avr_tasks = []
    for t in sorted(catalog["tasks"], key=lambda x: x["id"]):
        tid = t["id"]
        if "atmega328p_arduino" not in t["targets"]:
            continue
        if tid in task_to_cat:
            continue
        missing_parts = sorted(p for p in t["parts"] if p not in ct_supported_parts)
        skipped_avr_tasks.append({
            "task": tid,
            "interface": t["interface"],
            "parts": t["parts"],
            "missingParts": missing_parts,
            "reason": f"external peripheral model(s) not in CircuitTwin catalog: {', '.join(missing_parts)}",
        })

    return {
        "totalUpstreamSpecs": len(catalog["tasks"]),
        "totalUpstreamInstances": 598,
        "supportedSpecs": len(task_to_cat),
        "supportedInstances": len(task_to_cat) * 2,
        "unsupportedAvrSpecs": len(skipped_avr_tasks),
        "unsupportedAvrInstances": len(skipped_avr_tasks) * 2,
        "excludedEsp32s3Instances": 200,
        "unsupportedNrf52840Instances": 214,
        "targets": pin["targets"],
        "supportedTasksByCategory": supported_by_cat,
        "skippedAvrTasks": skipped_avr_tasks,
    }


def write_markdown_report(record, md_path):
    s = record["summary"]
    lines = [
        "# EmbedGym-Bench Evaluation on CircuitTwin",
        "",
        f"Recorded: `{record['recordedAt']}`",
        "",
        "## Upstream Pin & Provenance",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Benchmark | {record['upstream']['benchmark']} (arXiv:{record['upstream']['paper']['arxivId']}) |",
        f"| Upstream Repo | `{record['upstream']['repository']}` @ `{record['upstream']['commitSha']}` |",
        f"| Manifest `sourceCommit` | `{record['upstream']['manifestSourceCommit']}` |",
        f"| CircuitTwin CLI | `{record['ct']['version']}` (`{record['ct']['exe']}`, sha256 `{record['ct']['exeSha256']}`) |",
        f"| CircuitTwin Source | `{record['ct'].get('sourceRevision') or 'unspecified'}` (cleanTree: `{record['ct'].get('cleanTree')}`) |",
        f"| Engine Revision | `{record['ct'].get('engineRevision')}` |",
        "",
        "## Coverage Accounting (598 Upstream Task Instances)",
        "",
        "| Target | MCU | Upstream Tasks | Evaluated | Status / Reason |",
        "|---|---|---:|---:|---|",
    ]
    for tgt, info in sorted(record["coverage"]["targets"].items()):
        lines.append(f"| `{tgt}` | {info['mcu']} | {info['totalTasks']} | {info['supportedTasks']} | {info['status']}: {info['notes']} |")

    lines += [
        "",
        "## Summary Results (Real Upstream Agent `.hex` Controls)",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Evaluated task instances (29 tasks × 2 AVR boards) | {s['evaluatedTaskInstances']} |",
        f"| Total real agent `.hex` binaries executed | {s['totalRuns']} ({s['passingControlsTotal']} pass controls, {s['failingControlsTotal']} fail controls) |",
        f"| Passing controls passed on CircuitTwin (True Positives) | {s['passingControlsPassed']} / {s['passingControlsTotal']} ({s['passingControlAgreementPct']:.1f}%) |",
        f"| Passing controls falsely flagged (False Alarms) | {s['passingControlsFailed']} / {s['passingControlsTotal']} |",
        f"| Failing controls caught by CircuitTwin (True Negatives) | {s['failingControlsCaught']} / {s['failingControlsTotal']} ({s['failingControlCatchPct']:.1f}%) |",
        f"| Failing controls missed by CircuitTwin (False Negatives) | {s['failingControlsMissed']} / {s['failingControlsTotal']} |",
        f"| Inconclusive / Error runs | {s['inconclusiveRuns']} inconclusive, {s['errorRuns']} error |",
        f"| Overall exact verdict agreement with EmbedGym | {s['agreedRuns']} / {s['totalRuns']} ({s['overallAgreementPct']:.1f}%) |",
        "",
        "## Breakdown by Category",
        "",
        "| Category | Tasks | Pass Controls (CT Pass / Total) | Fail Controls (CT Catch / Total) |",
        "|---|---:|---:|---:|",
    ]
    for cat, cs in sorted(s["byCategory"].items()):
        lines.append(f"| `{cat}` | {cs['tasks']} | {cs['passPassed']}/{cs['passTotal']} | {cs['failCaught']}/{cs['failTotal']} |")

    disagreements = [r for r in record["results"] if not r["agreed"]]
    lines += ["", f"## Every Disagreement / Miss ({len(disagreements)})", ""]
    if not disagreements:
        lines.append("None — 100% agreement across all evaluated passing and failing controls.")
    else:
        lines += [
            "| Target | Task | Upstream Verdict | CT Verdict | Diagnostic |",
            "|---|---|---|---|---|",
        ]
        for r in disagreements:
            diag = r.get("error") or (
                str(r["grading"]["failures"][0]) if r["grading"]["failures"]
                else (str(r["nonInfoIssues"][0]) if r["nonInfoIssues"] else "assertion mismatch")
            )
            diag = diag.replace("|", "\\|").replace("\n", " ")[:180]
            lines.append(f"| `{r['target']}` | `{r['task']}` | `{r['embedgymVerdict']}` | `{r['evalVerdict']}` (ct: `{r['ctVerdict']}`) | {diag} |")

    lines += ["", "## Per-Run Results", "", "| Target | Task | Upstream | CT Eval | CT Engine | Assertions | Wall (ms) |", "|---|---|---|---|---|---:|---:|"]
    for r in record["results"]:
        g = r["grading"]
        mark = "OK" if r["agreed"] else "DIFF"
        lines.append(
            f"| `{r['target']}` | `{r['task']}` | `{r['embedgymVerdict']}` | `{r['evalVerdict']}` ({mark}) | `{r['ctVerdict']}` | {g['passedAssertions']}/{g['totalAssertions']} | {r['stats']['harnessWallMs']} |"
        )
    open(md_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ct", required=True, help="Path to CircuitTwin ct binary")
    ap.add_argument("--cache", required=True, help="Upstream EmbedGym cache directory (from fetch_upstream.py)")
    ap.add_argument("--out", required=True, help="Output directory for JSON and Markdown evidence")
    ap.add_argument("--source-revision", default=None, help="CircuitTwin source git SHA for provenance")
    ap.add_argument("--clean-tree", action="store_true", help="Record that CircuitTwin binary was built from a clean tree")
    ap.add_argument("--workers", type=int, default=4, help="Parallel ct run workers")
    ap.add_argument("--timeout", type=int, default=240, help="Per-run wall timeout in seconds")
    ap.add_argument("--filter", default=None, help="Optional substring filter on task id (debug only; omit for authoritative run)")
    args = ap.parse_args()

    pin = json.load(open(PIN_PATH, encoding="utf-8"))
    cache = os.path.abspath(args.cache)
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    ct_exe = os.path.abspath(args.ct)

    idx_path = os.path.join(cache, "selected-runs.json")
    if not os.path.isfile(idx_path):
        sys.exit(f"Missing {idx_path}: run embedgym/fetch_upstream.py --cache {cache} first")
    cache_idx = json.load(open(idx_path, encoding="utf-8"))
    selected = cache_idx["selectedRuns"]
    if args.filter:
        selected = [r for r in selected if args.filter in r["task"]]

    ver_proc = subprocess.run([ct_exe, "--version"], capture_output=True, text=True, timeout=30)
    ct_version = ver_proc.stdout.strip()
    ct_sha = sha256_file(ct_exe)

    scrub = make_scrubber([
        (cache, "<cache>"),
        (out_dir, "<out>"),
        (ROOT, "<repo>"),
        (os.path.dirname(ct_exe), "<ct>"),
        (os.path.expanduser("~"), "<home>"),
    ])

    env = dict(os.environ)
    print(f"Running {len(selected)} EmbedGym agent binaries on {os.path.basename(ct_exe)} ({ct_version}) with {args.workers} workers...", flush=True)
    t_start = time.monotonic()

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        fut_map = {ex.submit(run_one_case, ct_exe, cache, item, env, args.timeout, scrub): item for item in selected}
        for fut in concurrent.futures.as_completed(fut_map):
            res = fut.result()
            results.append(res)
            tag = "AGREE" if res["agreed"] else "DIFF "
            print(f"  [{tag}] {res['target']:18s} {res['task']:32s} eg={res['embedgymVerdict']:4s} ct={res['evalVerdict']:12s} ({res['grading']['passedAssertions']}/{res['grading']['totalAssertions']}) {res['stats']['harnessWallMs']}ms", flush=True)

    results.sort(key=lambda r: (r["target"], r["task"], r["embedgymVerdict"]))
    total_wall_s = round(time.monotonic() - t_start, 2)

    task_to_cat = {tid: cat for cat, tids in pin["supportedTasks"].items() for tid in tids}
    pass_runs = [r for r in results if r["embedgymVerdict"] == "pass"]
    fail_runs = [r for r in results if r["embedgymVerdict"] == "fail"]
    pass_passed = sum(1 for r in pass_runs if r["evalVerdict"] == "pass")
    pass_failed = len(pass_runs) - pass_passed
    fail_caught = sum(1 for r in fail_runs if r["evalVerdict"] == "fail")
    fail_missed = sum(1 for r in fail_runs if r["evalVerdict"] == "pass")
    inconclusive = sum(1 for r in results if r["evalVerdict"] == "inconclusive")
    errors = sum(1 for r in results if r["evalVerdict"] == "error")
    agreed = sum(1 for r in results if r["agreed"])

    by_cat = {}
    for cat, tids in pin["supportedTasks"].items():
        cset = set(tids)
        cp = [r for r in pass_runs if r["task"] in cset]
        cf = [r for r in fail_runs if r["task"] in cset]
        by_cat[cat] = {
            "tasks": len(tids),
            "passTotal": len(cp),
            "passPassed": sum(1 for r in cp if r["evalVerdict"] == "pass"),
            "failTotal": len(cf),
            "failCaught": sum(1 for r in cf if r["evalVerdict"] == "fail"),
        }

    by_target = {}
    for tgt in sorted({r["target"] for r in results}):
        tp = [r for r in pass_runs if r["target"] == tgt]
        tf = [r for r in fail_runs if r["target"] == tgt]
        tr = [r for r in results if r["target"] == tgt]
        by_target[tgt] = {
            "passTotal": len(tp),
            "passPassed": sum(1 for r in tp if r["evalVerdict"] == "pass"),
            "failTotal": len(tf),
            "failCaught": sum(1 for r in tf if r["evalVerdict"] == "fail"),
            "agreed": sum(1 for r in tr if r["agreed"]),
            "total": len(tr),
        }

    engine_revs = sorted({r.get("engineRevision") for r in results if r.get("engineRevision")})
    coverage = build_coverage_audit(pin, cache)

    record = {
        "schema": "agent-bench.embedgym-eval/1",
        "recordedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "filtered": bool(args.filter),
        "harnessGit": git_state(ROOT),
        "upstream": {
            "benchmark": pin["benchmark"],
            "paper": pin["paper"],
            "repository": pin["upstream"]["repository"],
            "commitSha": pin["upstream"]["commitSha"],
            "manifestSourceCommit": cache_idx["manifestSourceCommit"],
            "manifestSha256": cache_idx["manifestSha256"],
        },
        "ct": {
            "exe": os.path.basename(ct_exe),
            "exeSha256": ct_sha,
            "version": ct_version,
            "sourceRevision": args.source_revision,
            "cleanTree": bool(args.clean_tree),
            "engineRevision": engine_revs[0] if len(engine_revs) == 1 else engine_revs,
        },
        "coverage": coverage,
        "summary": {
            "evaluatedTaskInstances": len({(r["target"], r["task"]) for r in results}),
            "totalRuns": len(results),
            "passingControlsTotal": len(pass_runs),
            "passingControlsPassed": pass_passed,
            "passingControlsFailed": pass_failed,
            "passingControlAgreementPct": round(100.0 * pass_passed / len(pass_runs), 2) if pass_runs else 0.0,
            "failingControlsTotal": len(fail_runs),
            "failingControlsCaught": fail_caught,
            "failingControlsMissed": fail_missed,
            "failingControlCatchPct": round(100.0 * fail_caught / len(fail_runs), 2) if fail_runs else 0.0,
            "inconclusiveRuns": inconclusive,
            "errorRuns": errors,
            "agreedRuns": agreed,
            "overallAgreementPct": round(100.0 * agreed / len(results), 2) if results else 0.0,
            "totalWallSeconds": total_wall_s,
            "byCategory": by_cat,
            "byTarget": by_target,
        },
        "results": results,
    }

    json_path = os.path.join(out_dir, "embedgym-2026-11-22.json")
    md_path = os.path.join(out_dir, "report.md")
    open(json_path, "w", encoding="utf-8").write(json.dumps(record, indent=2) + "\n")
    write_markdown_report(record, md_path)

    print(
        f"\nCompleted {len(results)} runs in {total_wall_s}s: "
        f"pass controls {pass_passed}/{len(pass_runs)}, "
        f"fail controls caught {fail_caught}/{len(fail_runs)}, "
        f"overall agreement {agreed}/{len(results)} ({record['summary']['overallAgreementPct']}%)."
    )
    print(f"Wrote {json_path} and {md_path}")


if __name__ == "__main__":
    main()
