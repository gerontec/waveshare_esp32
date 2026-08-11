# MQTT Interface — sofar-waveshare (Waveshare 6CH ESP32-S3)

Firmware `3.6.2`. Broker `192.168.178.218:1883`, client id `sofar_waveshare`,
Home Assistant discovery disabled. All topics below are the literal strings the
firmware subscribes to or publishes — there is no topic prefix.

Payload parsing is hand-written in lambdas, so the accepted formats are quirky
and are documented exactly as implemented. **Where a colon is required, a bare
number is silently ignored.**

---

## 1. Command topics (write these to control the board)

### `soyo/set` — Soyo grid-tie inverter setpoint (W)

| | |
|---|---|
| Accepts | `{"W":350}` or a bare number `350` |
| Range | clamped to `0…900` |
| Expiry | **90 s** — without a fresh value the setpoint falls back to `0` |

The value is transmitted on RS485 channel A by `rs485_mux` every 3800 ms.
Because the Soyo never answers, this topic is the only way to observe control;
verify indirectly via battery current (see `ebox/pwr`).

```bash
mosquitto_pub -h 192.168.178.218 -t soyo/set -m 90     # 90 W
mosquitto_pub -h 192.168.178.218 -t soyo/set -m 0      # stop immediately
```

Note: a setpoint below roughly 20 W is not measurable at the battery — the BMS
reports per-pack current in mA and stays in `Idle`. 10 W produced no readable
current; 90 W showed −548/−552/−659 mA across three parallel packs (≈ 94 W).

### `sofar/auto` — arm or disarm the automatic controller

| | |
|---|---|
| Accepts | `{"ENABLE":1}` / `{"ENABLE":0}` |
| Requires | **a colon** — a bare `1` is ignored |
| Effect | `auto_enable`; reported back as `auto` in `sofar/waveshare/status` |

### `sofar/ladesperre` — arm or disarm the charge block

Same format as `sofar/auto`: `{"ENABLE":1}` / `{"ENABLE":0}`, colon required.
Reported back as `ladesperre_en`.

### `sofar/ratio` — bad-weather release threshold

| | |
|---|---|
| Accepts | `{"RATIO":0.62}`, `:0.62`, or a bare `0.62` |
| Range | `0 < v <= 1`, values outside are ignored |
| Default | `0.5` |

### `sofar/bat1_factor` — share of Sofar charge counted as EBox surplus

| | |
|---|---|
| Accepts | `{"FACTOR":0.5}`, `:0.5`, or a bare `0.5` |
| Range | `0 <= v <= 1`, values outside are ignored |
| Default | `0.5` |

### `waveshare/relay/1` … `waveshare/relay/6` — manual single-relay test

| | |
|---|---|
| Accepts | any payload **containing a colon**, e.g. `{"ON":1}` or `:1` |
| Effect | non-zero after the colon = on, zero = off |
| Caution | a bare `1` does nothing — the handler returns if no colon is found |

### `waveshare/relay/all` — switch all six relays at once

Same format as the single-relay topics; colon required.

### `sofar/openwifi` — enable/disable joining open WiFi

| | |
|---|---|
| Accepts | `{"ENABLE":1}` / `{"ENABLE":0}` |
| Parsing | **any payload containing the character `1` enables**; anything else disables |
| On disable | clears the remembered AP and forces the board back to the configured SSID |

### `sofar/openwifi/scan` — trigger an immediate open-WiFi scan

Any payload. Result is published on `sofar/waveshare/survey`.

### `rs485/scan` — non-blocking GPIO edge scan

Any payload. Result after ~3 s on `rs485/scan_result`.

### `rs485/relay_test` — relay test (CH1 pulls A to GND during the scan)

Any payload. Result on `rs485/relay_test_result`.

---

## 2. Data input topics (the board consumes these; do not use them as commands)

| Topic | Fields read | Used for |
|---|---|---|
| `inverter/power_grid_exchange/json` | `ActivePower_PCC_Total`, `Power_Bat1`, `Power_Bat1_avg5`, `ActivePower_PCC_Total_avg5`, `SOC_Bat1`, `Power_PV1`, `Power_PV2` (kW, multiplied by 1000) | PCC, battery 1, SOC1, PV power |
| `ebox/pwr` | `soc`, `power_w` | SOC2 and EBox power |
| `fox2db/state` | `state`, `soc_bat2` | relay state and SOC2 for the Soyo calculation |
| `r290/heatpump/all` | `comp_freq_actual` (Hz) | summer Soyo boost |
| `aussen/temp` | bare float °C, accepted for `-40 < v < 55` | DC temperature derating |

---

## 3. Published topics (read these)

| Topic | Content |
|---|---|
| `sofar/waveshare/status` | ip, ssid, open AP + RSSI, state, target_state, auto, ladesperre_en, ratio_th, bat1_f, ratio_ist, peak_h, win_end_h, soyo_w, uptime, mem_free, fw, fw_date |
| `sofar/waveshare/survey` | open-WiFi scan result: list of APs with ssid, rssi, channel, open flag |
| `sofar/state` | controller decision: pcc, bat1, soc1, soc2, ebox, excess, dc_expected, ratio, ladesperre, do4, plus a human-readable `trace` |
| `soyo/sent` | every transmitted Soyo frame: `w`, `hex`, `sends`, `changes`, `dt` (actual gap in ms), `mux` (channel) |
| `soyo/calc` | intermediate values of the Soyo calculation |
| `rs485/rx` | raw RS485 frames received (25 ms gap detection) |
| `rs485/scan_result` | GPIO scan result |
| `rs485/relay_test_result` | relay test result |

`dt` in `soyo/sent` is the measured interval between two frames. The Soyo drops
out after 4 s without a frame, so `dt` must stay below 4000 ms — it is the
health signal for the RS485 time multiplex.

---

## 4. RS485 multiplex

One transceiver carries two channels (`rs485_mux.h`):

* **Channel A** — Soyo, 4800 baud, transmit only, every 3800 ms, always wins.
* **Channel B** — FoxESS Modbus RTU, 9600 baud, runs inside channel A's gap.
  Currently disabled (`B_ENABLE = false`); slave address and register map of the
  T20-G3 are not yet confirmed.

Channel B aborts and returns the bus if it would run within `A_GUARD_MS` (600 ms)
of channel A's next slot, so the Soyo keepalive can never be missed.
