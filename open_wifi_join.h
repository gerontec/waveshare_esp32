#pragma once
#include "esphome.h"
#include "esphome/components/wifi/wifi_component.h"
#include <esp_wifi.h>
#include <string>
#include <vector>

// ─────────────────────────────────────────────────────────────────────────────
//  open_wifi_join — offenes (passwortfreies) WLAN bevorzugen, f24 als Fallback
//
//  Warum als Funktions-Header und nicht als Component:
//    open_wifi_scan.h definierte eine esphome::Component, die per `includes:`
//    zwar instanziiert, aber nie mit App.register_component() registriert
//    wurde -> setup() lief nie. Hier sind es reine Funktionen, die aus
//    ESPHome-Lambdas gerufen werden; kein Registrierungsproblem.
//
//  Ablauf:
//    1. ow_scan()     blockierender Passiv-Scan (~1,3 s), bester offener AP
//    2. ow_prefer()   STA-Liste neu bauen: offener AP prio 10, f24 prio 0.
//                     Passwortloser AP -> ESPHome setzt threshold.authmode
//                     automatisch auf WIFI_AUTH_OPEN (min_auth_mode greift
//                     nur bei gesetztem Passwort).
//    3. Watchdog      Hängt das Board am offenen AP ohne MQTT-Verbindung
//                     (typisch: Geräte-Fallback-APs wie "ESP_xxxxxx",
//                     Captive Portals), wird die SSID nach Timeout auf eine
//                     Blacklist gesetzt und f24 übernimmt wieder.
//
//  Blacklist lebt nur im RAM -> nach Reboot wird alles neu probiert.
// ─────────────────────────────────────────────────────────────────────────────

struct OpenApResult {
  std::string ssid;  // bester offener AP (höchster RSSI), "" = keiner
  int rssi;          // dessen RSSI, -127 wenn keiner
  int count;         // Anzahl gefundener offener APs (ohne Blacklist)
};

// ── Zustand ──────────────────────────────────────────────────────────────────
static std::vector<std::string> ow_blacklist;  // SSIDs ohne MQTT-Durchgang
static std::string ow_preferred;               // aktuell bevorzugter offener AP
static uint32_t ow_bad_since = 0;              // millis() seit MQTT weg (0 = ok)

// Macht einen String JSON-sicher (" und \ escapen, Steuerzeichen raus).
inline std::string json_escape(const std::string &in) {
  std::string out;
  for (char c : in) {
    if (c == '"' || c == '\\') {
      out += '\\';
      out += c;
    } else if ((unsigned char) c >= 0x20) {
      out += c;
    }
  }
  return out;
}

// Espressif-Default-SoftAPs ("ESP_A1B2C3", "ESP-xxx") und ESPHome-Fallback-APs
// sind Geräte-APs ohne Uplink -> nie als Ziel brauchbar, immer überspringen.
inline bool ow_is_device_ap(const std::string &ssid) {
  static const char *PREFIXES[] = {"ESP_", "ESP-", "ESPHome", "esphome"};
  for (const char *p : PREFIXES) {
    const size_t n = strlen(p);
    if (ssid.size() >= n && ssid.compare(0, n, p) == 0)
      return true;
  }
  return false;
}

inline bool ow_is_blacklisted(const std::string &ssid) {
  for (const auto &b : ow_blacklist)
    if (b == ssid)
      return true;
  return false;
}

inline void ow_blacklist_add(const std::string &ssid) {
  if (ssid.empty() || ow_is_blacklisted(ssid))
    return;
  ow_blacklist.push_back(ssid);
  ESP_LOGW("open_wifi", "'%s' auf Blacklist (kein MQTT)", ssid.c_str());
}

// Aktuell verbundene SSID ("" wenn nicht verbunden).
inline std::string ow_current_ssid() {
  auto *wc = esphome::wifi::global_wifi_component;
  if (wc == nullptr || !wc->is_connected())
    return "";
  return wc->wifi_ssid();
}

// Gefundene offene APs dieses Durchlaufs (SSID -> bester RSSI).
static std::vector<std::pair<std::string, int>> ow_cands;

// Ein Kandidat prüfen und in die Kandidatenliste aufnehmen.
inline void ow_consider_(OpenApResult &r, const std::string &ssid, int rssi, const char *own_ap_ssid) {
  if (ssid.empty() || ssid == own_ap_ssid)
    return;
  if (ow_is_device_ap(ssid)) {
    ESP_LOGD("open_wifi", "  ignoriert (Geräte-AP): '%s' RSSI=%d", ssid.c_str(), rssi);
    return;
  }
  if (ow_is_blacklisted(ssid))
    return;

  for (auto &c : ow_cands) {  // gleiche SSID auf mehreren APs: stärksten behalten
    if (c.first == ssid) {
      if (rssi > c.second)
        c.second = rssi;
      return;
    }
  }
  ow_cands.emplace_back(json_escape(ssid), rssi);
  r.count++;
  ESP_LOGI("open_wifi", "  offen: '%s' RSSI=%d", ssid.c_str(), rssi);
}

// Auswahl: Vorzugsliste schlägt RSSI. prefs = kommagetrennte SSIDs.
//
// Warum nicht einfach der stärkste: der stärkste offene AP kann in einem
// fremden Subnetz liegen (OpenWrtDach -> 192.168.4.x), aus dem das Board
// weder per OTA noch sonst erreichbar ist. Ein etwas schwächerer AP im
// eigenen Netz (f7240 -> 192.168.178.x) ist praktisch mehr wert.
inline void ow_pick_(OpenApResult &r, const char *prefs) {
  std::string list(prefs);
  size_t pos = 0;
  while (pos <= list.size()) {
    size_t comma = list.find(',', pos);
    if (comma == std::string::npos)
      comma = list.size();
    std::string want = list.substr(pos, comma - pos);
    while (!want.empty() && want.front() == ' ')
      want.erase(want.begin());
    while (!want.empty() && want.back() == ' ')
      want.pop_back();

    if (!want.empty()) {
      for (const auto &c : ow_cands) {
        if (c.first == want) {
          r.ssid = c.first;
          r.rssi = c.second;
          ESP_LOGI("open_wifi", "Vorzug: '%s' (%d dBm)", r.ssid.c_str(), r.rssi);
          return;
        }
      }
    }
    if (comma == list.size())
      break;
    pos = comma + 1;
  }

  for (const auto &c : ow_cands) {  // sonst der stärkste
    if (c.second > r.rssi) {
      r.rssi = c.second;
      r.ssid = c.first;
    }
  }
}

// Quelle 1: ESPHomes eigene Scan-Ergebnisse (get_with_auth() == false -> offen).
// Kostet nichts und stört die WiFi-Statemachine nicht; ESPHome scannt bei jedem
// (Re-)Connect neu.
inline OpenApResult ow_from_esphome_scan(const char *own_ap_ssid) {
  OpenApResult r{"", -127, 0};
  auto *wc = esphome::wifi::global_wifi_component;
  if (wc == nullptr)
    return r;
  for (const auto &s : wc->get_scan_result()) {
    if (s.get_with_auth() || s.get_is_hidden())
      continue;
    ow_consider_(r, std::string(s.get_ssid().c_str(), s.get_ssid().size()), s.get_rssi(), own_ap_ssid);
  }
  return r;
}

// Quelle 2: eigener blockierender Passiv-Scan (~1,3 s) für frische Daten,
// während die Verbindung steht. Liefert gelegentlich 0 Treffer, wenn ESPHome
// gerade selbst scannt — dann übernimmt der Aufrufer Quelle 1.
inline OpenApResult ow_scan(const char *own_ap_ssid) {
  OpenApResult r{"", -127, 0};

  wifi_scan_config_t cfg = {};
  cfg.ssid = nullptr;
  cfg.bssid = nullptr;
  cfg.channel = 0;  // alle Kanäle
  cfg.show_hidden = false;
  cfg.scan_type = WIFI_SCAN_TYPE_PASSIVE;
  cfg.scan_time.passive = 100;  // ms pro Kanal -> ~1,3 s gesamt

  esp_err_t err = esp_wifi_scan_start(&cfg, true);
  if (err != ESP_OK) {
    ESP_LOGD("open_wifi", "Eigener Scan nicht möglich (%s)", esp_err_to_name(err));
    return r;
  }

  uint16_t n = 0;
  esp_wifi_scan_get_ap_num(&n);
  if (n == 0)
    return r;
  if (n > 30)
    n = 30;

  wifi_ap_record_t *aps = new wifi_ap_record_t[n];
  if (esp_wifi_scan_get_ap_records(&n, aps) == ESP_OK) {
    for (int i = 0; i < n; i++) {
      if (aps[i].authmode != WIFI_AUTH_OPEN)
        continue;
      ow_consider_(r, std::string((const char *) aps[i].ssid), aps[i].rssi, own_ap_ssid);
    }
  }
  delete[] aps;
  return r;
}

// Eigener Scan bevorzugt, sonst ESPHomes letzte Scan-Ergebnisse.
// prefs = kommagetrennte Wunsch-SSIDs, schlagen den RSSI-Vergleich.
inline OpenApResult ow_find_open(const char *own_ap_ssid, const char *prefs) {
  ow_cands.clear();
  OpenApResult r = ow_scan(own_ap_ssid);
  if (r.count == 0)
    r = ow_from_esphome_scan(own_ap_ssid);
  ow_pick_(r, prefs);
  ESP_LOGI("open_wifi", "%d offene APs, gewählt '%s' (%d dBm)", r.count,
           r.ssid.empty() ? "-" : r.ssid.c_str(), r.rssi);
  return r;
}

// Baut die STA-Liste neu: offener AP (Priorität 10) vor Fallback (Priorität 0).
// open_ssid == "" -> nur der Fallback bleibt.
// Weicht die aktuelle Verbindung vom Wunsch ab, wird ein Reconnect erzwungen
// (disable()/enable() -> ESPHome scannt neu und wählt nach Priorität).
inline void ow_prefer(const std::string &open_ssid, const char *fb_ssid, const char *fb_pass) {
  auto *wc = esphome::wifi::global_wifi_component;
  if (wc == nullptr)
    return;

  // Nur bei echter Änderung anfassen: clear_sta() setzt selected_sta_index_ auf
  // -1, ESPHome verwirft daraufhin die laufende Verbindung. Ohne diese Sperre
  // würde jeder Scan-Durchlauf einen Reconnect auslösen.
  static bool configured = false;
  if (configured && open_ssid == ow_preferred)
    return;
  configured = true;

  ow_preferred = open_ssid;

  wc->clear_sta();
  if (!open_ssid.empty()) {
    esphome::wifi::WiFiAP ap;
    ap.set_ssid(open_ssid);
    // kein set_password() -> passwortlos, threshold.authmode = WIFI_AUTH_OPEN
    // hidden=true: direkt verbinden statt erst auf ein Scan-Ergebnis zu warten.
    // Nach clear_sta() ist ESPHomes Scan-Liste leer ("No networks found"), der
    // Connect liefe sonst über den Hidden-Retry-Umweg.
    ap.set_hidden(true);
    ap.set_priority(10);
    wc->add_sta(ap);
  }
  esphome::wifi::WiFiAP fb;
  fb.set_ssid(fb_ssid);
  fb.set_password(fb_pass);
  fb.set_priority(0);
  wc->add_sta(fb);

  const std::string want = open_ssid.empty() ? std::string(fb_ssid) : open_ssid;
  const std::string have = ow_current_ssid();
  if (have == want)
    return;

  ESP_LOGI("open_wifi", "Wechsel '%s' -> '%s'", have.c_str(), want.c_str());
  ow_bad_since = 0;
  wc->disable();
  wc->enable();
}

// Watchdog: am offenen AP ohne MQTT -> nach timeout_ms blacklisten und zurück
// auf den Fallback. Gibt true zurück, wenn umgeschaltet wurde.
inline bool ow_watchdog(bool mqtt_connected, uint32_t timeout_ms, const char *fb_ssid,
                        const char *fb_pass) {
  if (ow_preferred.empty())
    return false;
  if (ow_current_ssid() != ow_preferred) {
    ow_bad_since = 0;
    return false;
  }
  if (mqtt_connected) {
    ow_bad_since = 0;
    return false;
  }

  const uint32_t now = millis();
  if (ow_bad_since == 0) {
    ow_bad_since = now;
    return false;
  }
  if (now - ow_bad_since < timeout_ms)
    return false;

  ow_blacklist_add(ow_preferred);
  ow_bad_since = 0;
  ow_prefer("", fb_ssid, fb_pass);
  return true;
}
