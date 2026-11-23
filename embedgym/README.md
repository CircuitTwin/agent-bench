# EmbedGym-Bench Evaluation on CircuitTwin

Independent third-party embedded firmware benchmark evaluation of **CircuitTwin (`ct`)** against **EmbedGym-Bench** (*EmbedGym: Letting Coding Agents Develop and Debug Embedded Firmware Without Physical Hardware*, Zhao et al., Duke University, [arXiv:2611.21845v1](https://arxiv.org/abs/2611.21845), 2026-11-16).

## Upstream Pin

All task specifications, timed test vectors, peripheral physics definitions, and pre-compiled agent firmware binaries (`.hex`) are fetched directly from the official EmbedGym release and verified by SHA-256 against upstream `manifest.json` (`embedgym/fetch_upstream.py`):

| Item | Value |
|---|---|
| Upstream repository | `https://github.com/EmbedGym/EmbedGym.github.io` |
| Pinned GitHub commit | `2d69dcf705344b671c3327b6f0f8de9a47c1b98a` |
| Upstream `manifest.json` `sourceCommit` | `8162351a66be2ff531de9ed9143b06ede4da4752` |
| Upstream task specifications | 117 specs (598 target instances across 6 MCU-framework pairs, 41 peripherals, 14,352 recorded agent runs) |

No upstream files are vendored into this repository; `embedgym/fetch_upstream.py` downloads and SHA-256-verifies them into a local cache directory.

## Target & Task Support Matrix (All 598 Upstream Instances Accounted For)

Every upstream target and every skipped task is explicitly accounted for in `embedgym/upstream-pin.json` and the generated evidence JSON (`coverage` section):

| EmbedGym Target | MCU | Upstream Tasks | Evaluated on `ct` | Status / Exact Reason |
|---|---|---:|---:|---|
| `atmega328p_arduino` | ATmega328P (`arduino-uno`) | 92 | 29 | Supported MCU twin (`ATMEGA328P`); 29 tasks use built-in GPIO/PWM/ADC/UART or official catalog I2C twins (`MPU6050`, `VL53L0X`). 63 tasks skipped for unmodelled external peripherals (listed in evidence JSON). |
| `atmega2560_arduino` | ATmega2560 (`arduino-mega2560`) | 92 | 29 | Supported MCU twin (`ATMEGA2560`); same 29 supported tasks, 63 skipped for unmodelled external peripherals. |
| `esp32s3_arduino` | ESP32-S3 (`esp32s3-devkitc`) | 100 | 0 | Excluded: CircuitTwin ships `ESP32-S3` in its catalog, but upstream EmbedGym does not publish prebuilt `.bin` binaries (`hasFirmware=false`) and requires patched Arduino ESP32 v2.0.17 / ESP-IDF v4.4.7 app-start markers not published in `EmbedGym.github.io`. |
| `esp32s3_espidf` | ESP32-S3 (`esp32s3-devkitc`) | 100 | 0 | Excluded: same upstream artifact unavailability (`hasFirmware=false` and unpublished patched ESP-IDF v4.4.7 build scripts). |
| `nrf52840_arduino` | nRF52840 (`nrf52840-dk`) | 107 | 0 | Unsupported MCU in CircuitTwin catalog today (`ct board list` reports `nrf52840-dk` as `needs twin`; catalog ships `nRF52833-QIAA` only). Upstream also publishes no prebuilt ELFs (`hasFirmware=false`). |
| `nrf52840_zephyr` | nRF52840 (`nrf52840-dk`) | 107 | 0 | Unsupported MCU in CircuitTwin catalog today (same as above). |

### Unmodelled External Peripherals Skipping 63/92 AVR Tasks (126 Instances)

- **I2C/SPI sensor & actuator ICs not in CircuitTwin catalog:** `bme280` (catalog has `BME680`/`BME688`, not `BME280`), `drv2605l`, `pmsa003i`, `amg8833`, `hmc5883l`, `mlx90614`, `ltr390`, `max17048`, `mpr121`, `sgp40`, `ds1307`, `max32664`.
- **Displays / UI / H-bridge modules:** `lcd1602`, `membrane-keypad`, `ky-040`, `l298n`, `water-level-sensor` (paired with `lcd1602`), `shock-sensor` (paired with `lcd1602`).
- **Pulse-timing / 1-Wire external devices:** `dht11`, `hc-sr04`, `ds18b20`.
- **External UART modules:** `pa1616s` GPS, `hm10` BLE serial module.
- *(Non-AVR targets only)*: virtual `wifi` (9 tasks) and `ble` (16 tasks).

## Methodology & Controls

For all **29 supported tasks × 2 AVR targets = 58 task instances**, the harness deterministically selects (zero cherry-picking):
1. **Passing controls (58 images):** the lexicographically first upstream EmbedGym passing run with `hasFirmware=true` for each `(target, task)`.
2. **Failing negative controls (22 images):** the lexicographically first upstream EmbedGym failing run with `hasFirmware=true` for every `(target, task)` where upstream contains at least one failing agent binary.

Each upstream `.hex` image is executed **unchanged** on CircuitTwin (`ct run --json`) with:
- CircuitTwin's built-in `arduino-uno` / `arduino-mega2560` boards (and `ct.board/1` files attaching catalog twins `MPU6050` / `VL53L0X` on `TWI` for the 3 I2C tasks).
- `ct.scenario/1` driving digital inputs via `circuit.electrical.drivers` (matching upstream `BounceButton.ts` bounce timing, `Ky038SoundSensor.ts` comparator chatter, and HC-SR501 3 s monostable pulse), analog voltages via `circuit.elements` (`VoltageSource` + `AnalogNet`), and I2C sensor telemetry via `streams`.
- Nanosecond-exact pin waveforms (`--vcd --signals pin.<X>`) and nanosecond-exact `USART0` TX byte logs (`--mem-trace --mem-range 0x8000C6:1`), graded directly against EmbedGym's verbatim upstream `tests` JSONL assertions.

## Published Clean-Tree Results (`2026-11-22`)

See [`results/2026-11-22/report.md`](results/2026-11-22/report.md) and [`results/2026-11-22/embedgym-2026-11-22.json`](results/2026-11-22/embedgym-2026-11-22.json) for the full clean-tree record and every per-run diagnostic.

## Reproduce

```bash
# 1. Fetch & SHA-256-verify pinned upstream EmbedGym task specs and selected agent .hex runs
python embedgym/fetch_upstream.py --cache /tmp/embedgym-upstream

# 2. Run all 80 controls (58 pass + 22 fail across 29 tasks x 2 AVR boards) on CircuitTwin
python embedgym/run_embedgym.py \
  --ct /path/to/ct \
  --cache /tmp/embedgym-upstream \
  --out embedgym/results/2026-11-22 \
  --source-revision <circuittwin-git-sha> \
  --clean-tree \
  --workers 4
```
