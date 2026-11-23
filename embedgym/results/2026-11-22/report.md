# EmbedGym-Bench Evaluation on CircuitTwin

Recorded: `2026-11-23T01:06:03Z`

## Upstream Pin & Provenance

| Field | Value |
|---|---|
| Benchmark | EmbedGym-Bench (arXiv:2611.21845v1) |
| Upstream Repo | `https://github.com/EmbedGym/EmbedGym.github.io` @ `2d69dcf705344b671c3327b6f0f8de9a47c1b98a` |
| Manifest `sourceCommit` | `8162351a66be2ff531de9ed9143b06ede4da4752` |
| CircuitTwin CLI | `ct 0.1.0` (`ct.exe`, sha256 `25f7bdc43645b13a1da0d587db9916f083861e18e28f5a9abc51ac94f85b757c`) |
| CircuitTwin Source | `176c4df5ec5bae5ecf7ccf51f13e9a44047a5ff3` (cleanTree: `True`) |
| Engine Revision | `87494d1b5be8808ad1195eeacd8a004d9d2f0f3d3a24c75ea640856a227756f9` |

## Coverage Accounting (598 Upstream Task Instances)

| Target | MCU | Upstream Tasks | Evaluated | Status / Reason |
|---|---|---:|---:|---|
| `atmega2560_arduino` | ATmega2560 | 92 | 29 | supported_subset: MCU twin ATMEGA2560 is in CircuitTwin catalog; 29/92 tasks use built-in GPIO/PWM/ADC/UART or official catalog I2C twins (MPU6050, VL53L0X). Remaining 63 tasks require external peripheral models not yet in CircuitTwin catalog. |
| `atmega328p_arduino` | ATmega328P | 92 | 29 | supported_subset: MCU twin ATMEGA328P is in CircuitTwin catalog; 29/92 tasks use built-in GPIO/PWM/ADC/UART or official catalog I2C twins (MPU6050, VL53L0X). Remaining 63 tasks require external peripheral models not yet in CircuitTwin catalog. |
| `esp32s3_arduino` | ESP32-S3 | 100 | 0 | excluded_upstream_artifacts: CircuitTwin ships esp32s3-devkitc (ESP32-S3) in its catalog, but upstream EmbedGym does not publish prebuilt .bin binaries (hasFirmware=false for all 2400 runs) and builds with patched Arduino ESP32 v2.0.17 / ESP-IDF v4.4.7 app-start markers not published in EmbedGym.github.io. |
| `esp32s3_espidf` | ESP32-S3 | 100 | 0 | excluded_upstream_artifacts: CircuitTwin ships esp32s3-devkitc (ESP32-S3) in its catalog, but upstream EmbedGym does not publish prebuilt .bin binaries (hasFirmware=false for all 2400 runs) and requires patched ESP-IDF v4.4.7 build scripts not published in EmbedGym.github.io. |
| `nrf52840_arduino` | nRF52840 | 107 | 0 | unsupported_mcu: CircuitTwin does not currently ship an nRF52840-QIAA twin in its catalog (ct board list reports nrf52840-dk as 'needs twin'; catalog ships nRF52833-QIAA only). Upstream EmbedGym also does not publish prebuilt ELFs for nRF52840 (hasFirmware=false). |
| `nrf52840_zephyr` | nRF52840 | 107 | 0 | unsupported_mcu: CircuitTwin does not currently ship an nRF52840-QIAA twin in its catalog (ct board list reports nrf52840-dk as 'needs twin'; catalog ships nRF52833-QIAA only). Upstream EmbedGym also does not publish prebuilt ELFs for nRF52840 (hasFirmware=false). |

## Summary Results (Real Upstream Agent `.hex` Controls)

| Metric | Value |
|---|---:|
| Evaluated task instances (29 tasks × 2 AVR boards) | 58 |
| Total real agent `.hex` binaries executed | 80 (58 pass controls, 22 fail controls) |
| Passing controls passed on CircuitTwin (True Positives) | 56 / 58 (96.5%) |
| Passing controls falsely flagged (False Alarms) | 2 / 58 |
| Failing controls caught by CircuitTwin (True Negatives) | 22 / 22 (100.0%) |
| Failing controls missed by CircuitTwin (False Negatives) | 0 / 22 |
| Inconclusive / Error runs | 0 inconclusive, 0 error |
| Overall exact verdict agreement with EmbedGym | 78 / 80 (97.5%) |

## Breakdown by Category

| Category | Tasks | Pass Controls (CT Pass / Total) | Fail Controls (CT Catch / Total) |
|---|---:|---:|---:|
| `analog_adc` | 11 | 22/22 | 9/9 |
| `catalog_i2c_sensors` | 3 | 6/6 | 3/3 |
| `gpio_input_output` | 10 | 18/20 | 6/6 |
| `gpio_pwm_output` | 5 | 10/10 | 4/4 |

## Every Disagreement / Miss (2)

| Target | Task | Upstream Verdict | CT Verdict | Diagnostic |
|---|---|---|---|---|
| `atmega2560_arduino` | `tilt_detection_alarm` | `pass` | `fail` (ct: `pass`) | {'at': 800, 'expect': 'buzzer.hasSignal == true', 'passed': False} |
| `atmega328p_arduino` | `tilt_detection_alarm` | `pass` | `fail` (ct: `pass`) | {'at': 800, 'expect': 'buzzer.hasSignal == true', 'passed': False} |

## Per-Run Results

| Target | Task | Upstream | CT Eval | CT Engine | Assertions | Wall (ms) |
|---|---|---|---|---|---:|---:|
| `atmega2560_arduino` | `blink_led_1hz` | `pass` | `pass` (OK) | `pass` | 6/6 | 8811 |
| `atmega2560_arduino` | `blink_led_morse_code` | `fail` | `fail` (OK) | `pass` | 15/20 | 17474 |
| `atmega2560_arduino` | `blink_led_morse_code` | `pass` | `pass` (OK) | `pass` | 20/20 | 16898 |
| `atmega2560_arduino` | `blink_led_no_delay` | `pass` | `pass` (OK) | `pass` | 6/6 | 8319 |
| `atmega2560_arduino` | `blink_two_leds` | `pass` | `pass` (OK) | `pass` | 14/14 | 5246 |
| `atmega2560_arduino` | `breathing_led` | `fail` | `fail` (OK) | `pass` | 2/4 | 5097 |
| `atmega2560_arduino` | `breathing_led` | `pass` | `pass` (OK) | `pass` | 4/4 | 8134 |
| `atmega2560_arduino` | `button_press_debounce` | `pass` | `pass` (OK) | `pass` | 7/7 | 8066 |
| `atmega2560_arduino` | `button_status_count` | `pass` | `pass` (OK) | `pass` | 8/8 | 7523 |
| `atmega2560_arduino` | `button_status_display` | `pass` | `pass` (OK) | `pass` | 4/4 | 6502 |
| `atmega2560_arduino` | `buzzer_button` | `pass` | `pass` (OK) | `pass` | 10/10 | 7397 |
| `atmega2560_arduino` | `buzzer_doorbell` | `pass` | `pass` (OK) | `pass` | 5/5 | 10348 |
| `atmega2560_arduino` | `buzzer_laser_tripwire` | `pass` | `pass` (OK) | `pass` | 4/4 | 16258 |
| `atmega2560_arduino` | `buzzer_toggle_led_freq` | `fail` | `fail` (OK) | `pass` | 11/20 | 11960 |
| `atmega2560_arduino` | `buzzer_toggle_led_freq` | `pass` | `pass` (OK) | `pass` | 20/20 | 13311 |
| `atmega2560_arduino` | `clap_switch` | `fail` | `fail` (OK) | `pass` | 2/4 | 7410 |
| `atmega2560_arduino` | `clap_switch` | `pass` | `pass` (OK) | `pass` | 4/4 | 11266 |
| `atmega2560_arduino` | `gas_ventilation_fan_control` | `pass` | `pass` (OK) | `pass` | 32/32 | 89779 |
| `atmega2560_arduino` | `hcsr501_motion_alarm` | `pass` | `pass` (OK) | `pass` | 4/4 | 12885 |
| `atmega2560_arduino` | `joystick_buzzer_pitch` | `pass` | `pass` (OK) | `pass` | 7/7 | 27727 |
| `atmega2560_arduino` | `mpu6050_read_i2c` | `fail` | `fail` (OK) | `pass` | 0/2 | 19019 |
| `atmega2560_arduino` | `mpu6050_read_i2c` | `pass` | `pass` (OK) | `pass` | 2/2 | 23632 |
| `atmega2560_arduino` | `mq2_gas_analog_read` | `pass` | `pass` (OK) | `pass` | 8/8 | 19639 |
| `atmega2560_arduino` | `mq2_gas_leak_detector` | `pass` | `pass` (OK) | `pass` | 10/10 | 23330 |
| `atmega2560_arduino` | `photoresistor_nightlight` | `fail` | `fail` (OK) | `pass` | 0/3 | 27941 |
| `atmega2560_arduino` | `photoresistor_nightlight` | `pass` | `pass` (OK) | `pass` | 3/3 | 21712 |
| `atmega2560_arduino` | `sen0244_quality_led_indicator` | `pass` | `pass` (OK) | `pass` | 16/16 | 34591 |
| `atmega2560_arduino` | `sen0244_stable_reading` | `fail` | `fail` (OK) | `pass` | 5/10 | 47465 |
| `atmega2560_arduino` | `sen0244_stable_reading` | `pass` | `pass` (OK) | `pass` | 10/10 | 44940 |
| `atmega2560_arduino` | `sen0244_tds_read` | `fail` | `fail` (OK) | `pass` | 0/6 | 28335 |
| `atmega2560_arduino` | `sen0244_tds_read` | `pass` | `pass` (OK) | `pass` | 6/6 | 25449 |
| `atmega2560_arduino` | `sen0244_water_quality_monitor` | `fail` | `fail` (OK) | `pass` | 1/8 | 31223 |
| `atmega2560_arduino` | `sen0244_water_quality_monitor` | `pass` | `pass` (OK) | `pass` | 8/8 | 35722 |
| `atmega2560_arduino` | `sensor_pir_human_motion` | `pass` | `pass` (OK) | `pass` | 7/7 | 13453 |
| `atmega2560_arduino` | `step_counter_print` | `fail` | `fail` (OK) | `inconclusive` | 1/3 | 7725 |
| `atmega2560_arduino` | `step_counter_print` | `pass` | `pass` (OK) | `pass` | 3/3 | 10138 |
| `atmega2560_arduino` | `tilt_detection_alarm` | `pass` | `fail` (DIFF) | `pass` | 3/5 | 8255 |
| `atmega2560_arduino` | `tmp36_read` | `pass` | `pass` (OK) | `pass` | 7/7 | 16916 |
| `atmega2560_arduino` | `tof_distance_pulling` | `pass` | `pass` (OK) | `pass` | 6/6 | 15127 |
| `atmega328p_arduino` | `blink_led_1hz` | `fail` | `fail` (OK) | `pass` | 0/6 | 11211 |
| `atmega328p_arduino` | `blink_led_1hz` | `pass` | `pass` (OK) | `pass` | 6/6 | 11732 |
| `atmega328p_arduino` | `blink_led_morse_code` | `fail` | `fail` (OK) | `pass` | 14/20 | 20056 |
| `atmega328p_arduino` | `blink_led_morse_code` | `pass` | `pass` (OK) | `pass` | 20/20 | 24041 |
| `atmega328p_arduino` | `blink_led_no_delay` | `pass` | `pass` (OK) | `pass` | 6/6 | 9176 |
| `atmega328p_arduino` | `blink_two_leds` | `pass` | `pass` (OK) | `pass` | 14/14 | 9087 |
| `atmega328p_arduino` | `breathing_led` | `pass` | `pass` (OK) | `pass` | 4/4 | 13842 |
| `atmega328p_arduino` | `button_press_debounce` | `pass` | `pass` (OK) | `pass` | 7/7 | 12139 |
| `atmega328p_arduino` | `button_status_count` | `pass` | `pass` (OK) | `pass` | 8/8 | 12480 |
| `atmega328p_arduino` | `button_status_display` | `fail` | `fail` (OK) | `pass` | 2/4 | 10985 |
| `atmega328p_arduino` | `button_status_display` | `pass` | `pass` (OK) | `pass` | 4/4 | 13536 |
| `atmega328p_arduino` | `buzzer_button` | `fail` | `fail` (OK) | `pass` | 7/10 | 15734 |
| `atmega328p_arduino` | `buzzer_button` | `pass` | `pass` (OK) | `pass` | 10/10 | 16085 |
| `atmega328p_arduino` | `buzzer_doorbell` | `pass` | `pass` (OK) | `pass` | 5/5 | 16975 |
| `atmega328p_arduino` | `buzzer_laser_tripwire` | `pass` | `pass` (OK) | `pass` | 4/4 | 18583 |
| `atmega328p_arduino` | `buzzer_toggle_led_freq` | `fail` | `fail` (OK) | `pass` | 14/20 | 12805 |
| `atmega328p_arduino` | `buzzer_toggle_led_freq` | `pass` | `pass` (OK) | `pass` | 20/20 | 15629 |
| `atmega328p_arduino` | `clap_switch` | `fail` | `fail` (OK) | `pass` | 2/4 | 8438 |
| `atmega328p_arduino` | `clap_switch` | `pass` | `pass` (OK) | `pass` | 4/4 | 10204 |
| `atmega328p_arduino` | `gas_ventilation_fan_control` | `pass` | `pass` (OK) | `pass` | 32/32 | 87681 |
| `atmega328p_arduino` | `hcsr501_motion_alarm` | `pass` | `pass` (OK) | `pass` | 4/4 | 22817 |
| `atmega328p_arduino` | `joystick_buzzer_pitch` | `pass` | `pass` (OK) | `pass` | 7/7 | 23845 |
| `atmega328p_arduino` | `mpu6050_read_i2c` | `pass` | `pass` (OK) | `pass` | 2/2 | 19574 |
| `atmega328p_arduino` | `mq2_gas_analog_read` | `pass` | `pass` (OK) | `pass` | 8/8 | 17836 |
| `atmega328p_arduino` | `mq2_gas_leak_detector` | `pass` | `pass` (OK) | `pass` | 10/10 | 31421 |
| `atmega328p_arduino` | `photoresistor_nightlight` | `fail` | `fail` (OK) | `pass` | 0/3 | 17515 |
| `atmega328p_arduino` | `photoresistor_nightlight` | `pass` | `pass` (OK) | `pass` | 3/3 | 18480 |
| `atmega328p_arduino` | `sen0244_quality_led_indicator` | `fail` | `fail` (OK) | `pass` | 14/16 | 37972 |
| `atmega328p_arduino` | `sen0244_quality_led_indicator` | `pass` | `pass` (OK) | `pass` | 16/16 | 31318 |
| `atmega328p_arduino` | `sen0244_stable_reading` | `fail` | `fail` (OK) | `pass` | 1/10 | 47916 |
| `atmega328p_arduino` | `sen0244_stable_reading` | `pass` | `pass` (OK) | `pass` | 10/10 | 47949 |
| `atmega328p_arduino` | `sen0244_tds_read` | `fail` | `fail` (OK) | `pass` | 5/6 | 17705 |
| `atmega328p_arduino` | `sen0244_tds_read` | `pass` | `pass` (OK) | `pass` | 6/6 | 24999 |
| `atmega328p_arduino` | `sen0244_water_quality_monitor` | `fail` | `fail` (OK) | `pass` | 1/8 | 26669 |
| `atmega328p_arduino` | `sen0244_water_quality_monitor` | `pass` | `pass` (OK) | `pass` | 8/8 | 30198 |
| `atmega328p_arduino` | `sensor_pir_human_motion` | `pass` | `pass` (OK) | `pass` | 7/7 | 11863 |
| `atmega328p_arduino` | `step_counter_print` | `fail` | `fail` (OK) | `pass` | 0/3 | 11316 |
| `atmega328p_arduino` | `step_counter_print` | `pass` | `pass` (OK) | `pass` | 3/3 | 10532 |
| `atmega328p_arduino` | `tilt_detection_alarm` | `pass` | `fail` (DIFF) | `pass` | 3/5 | 9093 |
| `atmega328p_arduino` | `tmp36_read` | `pass` | `pass` (OK) | `pass` | 7/7 | 14778 |
| `atmega328p_arduino` | `tof_distance_pulling` | `pass` | `pass` (OK) | `pass` | 6/6 | 19546 |
