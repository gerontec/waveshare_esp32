# nors485 — Waveshare ESP32-S3-Relay-6CH mit defektem RS485

Firmware für ein Board, dessen SP3485-Zweig (GPIO17/18/3) defekt ist. Die
6 Relais funktionieren einwandfrei, deshalb läuft das Board als reines
Relais-/Telemetrie-Gerät weiter. UART/RS485 ist bewusst **nicht** konfiguriert.

Board: MAC `50:78:7D:07:FF:E4`, Gerätename `rs485defect-wav-esp32s3`.

## Dateien

| Datei | Inhalt |
|---|---|
| `rs485defect.yaml` | ESPHome-Konfiguration |
| `open_wifi_join.h` | Lib: offenes WLAN bevorzugen, `f24` als Fallback |
| `usb_mux.h` | Lib: zwei logische Kanäle auf der USB-Leitung (Transport) |
| `usbmux.c` + `Makefile` | Host-Daemon: hält `/dev/ttyACM0`, bietet Steuerung, Log und einen rohen Kanal an |
| `usbmux_stress.sh` | Belastungs- und Korrektheitstest für den Mux |
| `usbmux.md` | Doku dazu: Protokoll, Grenzen, PTY-Messungen, Fallstricke |

## USB-Multiplex (seit 1.5)

Der ESP32-S3 hat nur ein USB-Serial-Interface — wer `/dev/ttyACM0` öffnet, hat es
exklusiv. `usbmux` teilt es zeilenweise auf: Steuerung (Präfix `#K1# `), Log und
ein roher Durchreichkanal für esptool. Steuerung läuft damit auch dann, wenn das
Board am offenen AP in `192.168.4.x` hängt und weder OTA noch MQTT herankommen.

```bash
make usbmux
./usbmux daemon &
./usbmux cmd status      # Steuerung
./usbmux mon             # Log, beliebig oft parallel
./usbmux esptool flash_id
```

Fremdwerkzeuge bekommen PTYs mit festen Symlinks und merken nichts vom Mux:

```bash
esphome logs rs485defect.yaml --device $XDG_RUNTIME_DIR/usbmux/tty-log-ttyACM0
```

Details in [usbmux.md](usbmux.md).

## Relais

| Kanal | GPIO |
|---|---|
| CH1 | GPIO1 |
| CH2 | GPIO2 |
| CH3 | GPIO41 |
| CH4 | GPIO42 |
| CH5 | GPIO45 |
| CH6 | GPIO46 |

Beim Boot immer `ALWAYS_OFF`. GPIO45/46 sind Strapping-Pins — ESPHome warnt
beim Build, im Betrieb unkritisch.

## WLAN — passwortlos bevorzugt

`open_wifi_join.h` sucht offene APs und trägt den stärksten mit Priorität 10
vor `f24` (Priorität 0) in die STA-Liste ein. Ein passwortloser `WiFiAP` setzt
in ESPHome automatisch `threshold.authmode = WIFI_AUTH_OPEN`; `min_auth_mode`
(Default WPA2 auf ESP32) greift nur bei gesetztem Passwort.

Zwei Fallstricke, die hier gelöst sind:

* **`clear_sta()` wirft die laufende Verbindung weg** (`selected_sta_index_ = -1`).
  Die STA-Liste wird deshalb nur bei echter Änderung neu gebaut, sonst löst
  jeder Scan-Durchlauf einen Reconnect aus.
* **Eigener Blocking-Scan kollidiert mit ESPHomes Scan-Statemachine**
  (`esp_wifi_scan_get_ap_record failed: ESP_FAIL`, 0 Treffer). Liefert der
  eigene Scan nichts, werden ESPHomes eigene Scan-Ergebnisse ausgewertet
  (`get_scan_result()` / `get_with_auth()`).

Nicht als Component, sondern als Funktions-Header: `open_wifi_scan.h` im
Hauptordner definierte eine `esphome::Component`, die per `includes:` zwar
instanziiert, aber nie mit `App.register_component()` registriert wurde —
`setup()` lief nie.

### Filter

* Geräte-APs (`ESP_*`, `ESP-*`, `ESPHome*`) werden übersprungen — Fallback-APs
  ohne Uplink.
* Der eigene AP (`RS485defect-AP`) ebenfalls.
* **Watchdog:** Hängt das Board am offenen AP und MQTT kommt 180 s nicht
  zustande, wandert die SSID auf eine RAM-Blacklist und `f24` übernimmt wieder.
  Nach einem Reboot wird alles neu probiert.

## MQTT

Broker `192.168.178.218:1883`, Prefix `rs485defect-wav-esp32s3`, alles
`retain: false`.

Status alle 30 s auf `rs485defect-wav-esp32s3/status`:

```json
{"name":"rs485defect-wav-esp32s3","ip":"192.168.4.249","ssid":"OpenWrtDach",
 "rssi":-78,"open_ap":"OpenWrtDach","open_rssi":-63,"open_count":2,
 "relays":[0,0,0,0,0,0],"uptime":121,"mem_free":252172,
 "fw":"1.1","rs485":"defekt"}
```

Steuerung:

```bash
mosquitto_pub -h 192.168.178.218 -t rs485defect-wav-esp32s3/relay/1   -m '{"v":1}'
mosquitto_pub -h 192.168.178.218 -t rs485defect-wav-esp32s3/relay/all -m '{"v":0}'
mosquitto_pub -h 192.168.178.218 -t rs485defect-wav-esp32s3/scan      -m 'go'
mosquitto_pub -h 192.168.178.218 -t rs485defect-wav-esp32s3/openwifi  -m '{"ENABLE":0}'
```

## OTA — erst zurück auf f24

Am offenen AP hängt das Board in einem fremden Subnetz (`OpenWrtDach` →
`192.168.4.x`), das von `192.168.178.x`/`192.168.5.x` aus **nicht erreichbar**
ist — OTA läuft dort in `Connection refused` auf Port 3232. Deshalb vorher:

```bash
mosquitto_pub -h 192.168.178.218 -t rs485defect-wav-esp32s3/openwifi -m '{"ENABLE":0}'
# ~30 s warten, IP aus .../status lesen, dann:
esphome upload rs485defect.yaml --device <ip-aus-status>
```

`open_enabled` ist nicht persistent: nach dem OTA-Reboot wird wieder das offene
WLAN bevorzugt. Verifiziert: Rückkehr auf `f24` (`192.168.178.58`, RSSI −56),
OTA-Upload in 3,66 s, `OTA successful`.

## Auswahl: bester RSSI, Subnetz egal

Gewählt wird schlicht der stärkste offene AP. Dass der in einem fremden Subnetz
liegen kann (und OTA dann nur noch über USB oder nach `{"ENABLE":0}` geht), ist
bewusst in Kauf genommen.

Verifiziert am Schreibtisch (fw 1.4):

```
[I][open_wifi:113]:   offen: 'OpenWrtDach'     RSSI=-68
[I][open_wifi:113]:   offen: 'FRITZ!Box 7490'  RSSI=-88
[I][open_wifi:113]:   offen: 'f7240'           RSSI=-91
[I][open_wifi:188]: 3 offene APs, gewählt 'OpenWrtDach' (-68 dBm)
```

Verbunden auf `OpenWrtDach`, IP `192.168.4.249`, MQTT läuft darüber weiter —
der Watchdog schlägt dort also nicht zu. `ESP_F5246E` erscheint nicht in der
Liste: Geräte-AP, per Präfixfilter raus.

RSSI ist stark standortabhängig — dasselbe `f7240` misst am Prod-Board −50 dBm.

Der eigene MQTT-Prefix hält die Produktions-Topics `waveshare/relay/*` des
Boards `192.168.178.187` frei — sonst würden beide Boards mitschalten.

Zusätzlich Web-Oberfläche auf Port 80 zum Handschalten, OTA-Passwort
`waveshare2026`.
