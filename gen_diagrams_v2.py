#!/usr/bin/env python3
# ════════════════════════════════════════════════════════════════════════════
#  Diagram generator — Waveshare version only (fox2db v3.3.34, ESP32-S3 6CH)
#  Source: waveshare/fox2db_logic.h + waveshare/waveshare_6ch_esp32s3.md
#  Multi-page PDF, minimum font size 10.
# ════════════════════════════════════════════════════════════════════════════
import subprocess
from pathlib import Path

OUT = Path(__file__).parent

# ── Page 1: Architecture / layers ────────────────────────────────────────────
PAGE1 = """
digraph WaveshareArch {
    graph [
        label="fox2db v3.3.34 — Waveshare ESP32-S3 6CH — Architecture (fox2db_logic.h, autonomous on the ESP)"
        labelloc=t fontsize=14 fontname="Helvetica-Bold"
        rankdir=TB splines=ortho nodesep=0.6 ranksep=0.8
        bgcolor="#f8f9fa" size="11,17" ratio=fill
    ]
    node [fontname="Helvetica" fontsize=10 margin="0.2,0.08" style="filled,rounded"]
    edge [fontname="Helvetica" fontsize=10 penwidth=1.2]

    subgraph cluster_extern {
        label="External systems (MQTT 192.168.178.218:1883)" style="dashed,filled" fillcolor="#eeeeee"
        fontname="Helvetica-Bold" fontsize=10 color="#aaaaaa"

        MQTT_PCC [shape=cylinder fillcolor="#dddddd" label="Inverter data (MQTT)\\npcc, bat1, soc1"]
        MQTT_EBOX [shape=cylinder fillcolor="#dddddd" label="ebox/pwr\\nsoc2, power_w (signed!),\\ncurrent_a, packs"]
        MQTT_RATIO [shape=cylinder fillcolor="#dddddd" label="sofar/ratio\\nratio_th (default 0.5)\\nsofar/bat1_factor (default 0.5)\\nsofar/ladesperre, sofar/auto"]
        MQTT_OUT [shape=cylinder fillcolor="#dddddd" label="sofar/state · sofar/waveshare/status\\nsoyo/calc · soyo/sent (retain)"]
        Relays123 [shape=component fillcolor="#dddddd" label="CH1-CH3 (GPIO1/2/41)\\nEBox state 0..7 binary"]
        Relay4 [shape=component fillcolor="#fce8e8" label="CH4 (GPIO42)\\nDO4 -> curtail inverter 2\\n3s pulse"]
        Soyo [shape=component fillcolor="#dddddd" label="Soyo inverter (max 900W)\\nRS485 GPIO17 TX / GPIO18 RX\\nkeepalive every 3s"]
    }

    subgraph cluster_input {
        label="INPUT (Inputs struct)" style="filled" fillcolor="#d4edda"
        fontname="Helvetica-Bold" fontsize=10 color="#28a745"

        in_struct [shape=box fillcolor="#b8dfc4" label="Inputs{pcc, bat1, soc1, soc2, ebox_w}\\nsoc2 < 0 = unknown"]
        state_ram [shape=box fillcolor="#b8dfc4" label="State (RAM, across cycles)\\nrelay_st, stable, last_excess, prot,\\npeak_today, ladesperre_latched, pcc_buf[10]\\n(reset at midnight, lost on reboot)"]
    }

    subgraph cluster_forecast {
        label="DC FORECAST (Meinel clear-sky)" style="filled" fillcolor="#fff3cd"
        fontname="Helvetica-Bold" fontsize=10 color="#b8860b"

        dc_now [shape=box fillcolor="#ffe69c" label="dc_now()  South+East arrays\\nNOAA sun position, kt_month\\n47.6811N 11.5732E\\n-> dc_expected"]
        peakwin [shape=box fillcolor="#ffe69c" label="Peak window (hour 5..20)\\nbest_w, peak_h, win_end_h\\nratio_ist via pcc_buf average"]
    }

    subgraph cluster_decision {
        label="DECISION PIPELINE (step())" style="filled" fillcolor="#e2d9f3"
        fontname="Helvetica-Bold" fontsize=10 color="#6f42c1"

        ladesperre [shape=box fillcolor="#d4c5f0" label="Charge-block latch (hysteresis)\\nLOCK: ratio_ist <= ratio_th\\nRELEASE: ratio_ist >= ratio_th+0.15\\n(only on confirmed good weather)"]
        decide_fn [shape=box fillcolor="#c9b8f0" label="decide()  priority-ordered\\nSOC_UNKNOWN / PCC_OVER_20KW /\\nEMERGENCY / INSUFFICIENT /\\nPOWER_MATCHING + RAMP_LIMITED"]
        guards [shape=box fillcolor="#f8d7da" label="apply_guards() — HARD\\ncharge-block / battery-full /\\ncritical-soc (fires -> skip blocking)"]
        blocking [shape=box fillcolor="#d4c5f0" label="apply_blocking()\\nUP: SWEET_SPOT/TREND/BAT_GUARD\\nDOWN: STABILIZING/HYSTERESIS\\nEMERGENCY_FORCE bypass"]
    }

    subgraph cluster_output {
        label="OUTPUT (Result struct)" style="filled" fillcolor="#cce5ff"
        fontname="Helvetica-Bold" fontsize=10 color="#004085"

        set_relays [shape=box fillcolor="#a8d0f5" label="set CH1-CH3\\nfinal_state as bitmask"]
        do4_out [shape=box fillcolor="#f8d7da" label="DO4 pulse (CH4)\\npcc>22kW unconditional OR\\npcc>20kW no state+ / charge-block"]
        soyo_calc [shape=box fillcolor="#a8d0f5" label="Soyo calculation\\ndischarge when State==0\\nRS485 frame every 3s"]
        publish [shape=box fillcolor="#a8d0f5" label="MQTT publish\\nsofar/state, status, soyo/*"]
    }

    MQTT_PCC -> in_struct [color="#28a745"]
    MQTT_EBOX -> in_struct [color="#28a745"]
    MQTT_RATIO -> ladesperre [color="#28a745" label="ratio_th"]

    in_struct -> dc_now [color="#b8860b"]
    state_ram -> peakwin [color="#b8860b" label="pcc_buf"]
    dc_now -> peakwin [color="#b8860b"]

    peakwin -> ladesperre [color="#6f42c1" label="ratio_ist\\npeak_h"]
    in_struct -> decide_fn [color="#6f42c1"]
    state_ram -> decide_fn [color="#6f42c1" label="relay_st, prot"]
    ladesperre -> guards [color="#c0392b" label="charge-block"]
    decide_fn -> guards [color="#6f42c1"]
    guards -> blocking [color="#6f42c1" label="no guard"]
    guards -> set_relays [color="#c0392b" style=dashed label="guard fires"]

    blocking -> set_relays [color="#004085"]
    blocking -> do4_out [color="#c0392b" style=dashed]
    blocking -> publish [color="#004085"]
    in_struct -> soyo_calc [color="#004085" style=dotted]

    set_relays -> Relays123 [color="#004085"]
    do4_out -> Relay4 [color="#c0392b"]
    soyo_calc -> Soyo [color="#004085" label="3s keepalive"]
    publish -> MQTT_OUT [color="#004085"]
}
"""

# ── Page 2: step() — full flow ───────────────────────────────────────────────
PAGE2 = """
digraph WaveshareStep {
    graph [
        label="fox2db v3.3.34 — step() full flow (every 60s, fox2db_logic.h)"
        labelloc=t fontsize=14 fontname="Helvetica-Bold"
        rankdir=TB splines=polyline nodesep=0.4 ranksep=0.5
        bgcolor="#f8f9fa" size="11,17" ratio=fill
    ]
    node [fontname="Helvetica" fontsize=10 margin="0.18,0.08" style="filled,rounded"]
    edge [fontname="Helvetica" fontsize=10 penwidth=1.2]

    Start [shape=oval fillcolor="#cce5ff" label="step(in, st, now_utc, ...)\\nESPHome interval 60s"]
    End [shape=oval fillcolor="#cce5ff" label="return Result"]

    s1 [shape=diamond fillcolor="#fff3cd" label="local_yday != last_yday?\\n(midnight)"]
    s1r [shape=box fillcolor="#d4edda" label="pcc_buf reset, peak_today=false\\nlast_yday = local_yday"]
    s2 [shape=box fillcolor="#fff3cd" label="dc_expected = dc_now(now_utc, month)\\nMeinel clear-sky"]
    s3 [shape=box fillcolor="#d4edda" label="pcc_buf[i]=pcc (ring buffer 10)\\npcc_avg if n>=3"]
    s4 [shape=box fillcolor="#fff3cd" label="Peak window h=5..20\\nbest_w, peak_h_loc, win_end_loc\\npeak_h / win_end_h -> Result"]
    s5 [shape=box fillcolor="#fce8e8" label="if pcc>20kW: peak_today=true"]
    s6 [shape=box fillcolor="#fff3cd" label="ratio_ist = (dc_exp - (pcc_avg+ebox+bat1)) / dc_exp\\nonly if pcc_avg valid and dc_exp>5000\\nelse -1"]

    d_en [shape=diamond fillcolor="#fce8e8" label="ladesperre_enable?"]
    d_win [shape=diamond fillcolor="#fce8e8" label="in_window?\\nhas_peak && win_end>=0\\n&& !peak_today\\n&& local_hour<=peak_h"]
    d_rat [shape=diamond fillcolor="#fce8e8" label="Latch (hysteresis):\\nLOCK ratio_ist<=ratio_th\\nRELEASE ratio_ist>=ratio_th+0.15"]
    r_lock [shape=box fillcolor="#f8d7da" label="charge-block = latched"]
    r_free [shape=box fillcolor="#d4edda" label="charge-block = false\\n(outside window)"]

    s7 [shape=box fillcolor="#e2d9f3" label="best = decide(in, relay_st, prot, bat1_factor, ...)\\n-> best, trace, excess"]
    s8 [shape=box fillcolor="#f8d7da" label="best = apply_guards(best, soc2, charge-block)\\n-> guard_fired"]
    s9 [shape=box fillcolor="#e2d9f3" label="drop_rate = (excess - last_excess)/30\\nlast_excess = excess"]
    d_g [shape=diamond fillcolor="#fce8e8" label="guard_fired?"]
    s_byp [shape=box fillcolor="#f8d7da" label="final = best\\nchanged = (best != relay_st)\\n(blocking skipped)"]
    s10 [shape=box fillcolor="#e2d9f3" label="final = apply_blocking(best, relay_st,\\n  pcc, bat1, stable, drop_rate)\\n-> final, changed"]
    s11 [shape=box fillcolor="#d4edda" label="stable = changed ? 0 : stable+1"]
    s12 [shape=box fillcolor="#e2d9f3" label="Deep-discharge hysteresis\\nsoc2<6 -> prot=true\\nsoc2>=8 -> prot=false"]
    d_do4 [shape=diamond fillcolor="#fce8e8" label="need_down?\\npcc>22kW OR\\n(pcc>20kW &&\\n(no PCC_OVER_20KW\\nin trace || charge-block))"]
    s_do4 [shape=box fillcolor="#f8d7da" label="do4_pulse = true\\n(CH4 3s pulse)"]
    s13 [shape=box fillcolor="#cce5ff" label="relay_st = final\\nfill Result: final_state, changed,\\nexcess, dc_delta, ratio, peak_h, trace"]

    Start -> s1
    s1 -> s1r [label="YES" color="green"]
    s1 -> s2 [label="NO" color="#888888"]
    s1r -> s2
    s2 -> s3 -> s4 -> s5 -> s6 -> d_en
    d_en -> d_win [label="YES" color="green"]
    d_en -> r_free [label="NO" color="#888888"]
    d_win -> d_rat [label="YES" color="orange"]
    d_win -> r_free [label="NO" color="#888888"]
    d_rat -> r_lock [label="YES" color="red"]
    d_rat -> r_free [label="NO" color="green"]
    r_lock -> s7
    r_free -> s7
    s7 -> s8 -> s9 -> d_g
    d_g -> s_byp [label="YES" color="red"]
    d_g -> s10 [label="NO" color="green"]
    s_byp -> s11
    s10 -> s11 -> s12 -> d_do4
    d_do4 -> s_do4 [label="YES" color="red"]
    d_do4 -> s13 [label="NO" color="green"]
    s_do4 -> s13 -> End
}
"""

# ── Page 3: decide / apply_guards / apply_blocking in detail ──────────────────
PAGE3 = """
digraph WaveshareDecision {
    graph [
        label="fox2db v3.3.34 — decide() / apply_guards() / apply_blocking() in detail"
        labelloc=t fontsize=14 fontname="Helvetica-Bold"
        rankdir=TB splines=polyline nodesep=0.4 ranksep=0.5
        bgcolor="#f8f9fa" size="11,17" ratio=fill
    ]
    node [fontname="Helvetica" fontsize=10 margin="0.18,0.08" style="filled,rounded"]
    edge [fontname="Helvetica" fontsize=10 penwidth=1.2]

    Start [shape=oval fillcolor="#e2d9f3" label="decide()"]
    End [shape=oval fillcolor="#e2d9f3" label="-> (best, trace, excess)"]

    excess_calc [shape=box fillcolor="#c9b8f0" label="ebox_eff = relay_st>0 ? max(ebox_w, state_power(relay_st)) : 0\\nbat1_eff = bat1<0 ? bat1 : bat1*bat1_factor\\nexcess = pcc + ebox_eff + bat1_eff"]
    d_unk [shape=diamond fillcolor="#fce8e8" label="soc2 < 0?\\n(unknown)"]
    r_unk [shape=box fillcolor="#fce8e8" label="return relay_st\\nEBOX_SOC_UNKNOWN_HOLD"]
    d_pcc [shape=diamond fillcolor="#f8d7da" label="pcc>20kW &&\\nsoc2<100?"]
    r_pcc [shape=box fillcolor="#f8d7da" label="return min(relay_st+1,7)\\nPCC_OVER_20KW"]
    d_prot [shape=diamond fillcolor="#fce8e8" label="prot active?"]
    d_prot2 [shape=diamond fillcolor="#fce8e8" label="soc2 < 7%?"]
    r_emerg [shape=box fillcolor="#fce8e8" label="return 1\\nEMERGENCY_CHARGE_TO_7%"]
    r_target [shape=box fillcolor="#fce8e8" label="return 0\\nCHARGE_TARGET_REACHED"]
    d_excess [shape=diamond fillcolor="#fce8e8" label="excess < 2500W?\\n(MIN_EXCESS)"]
    r_insuf [shape=box fillcolor="#fce8e8" label="return 0\\nINSUFFICIENT_EXCESS"]
    pm [shape=box fillcolor="#c9b8f0" label="POWER_MATCHING\\nbudget = excess + 900W (MAX_GRID_DRAW)\\nbest = highest state_power <= budget"]
    d_ramp [shape=diamond fillcolor="#fff3cd" label="best > relay_st &&\\nbest > next_up\\n(SORTED_STATES)?"]
    r_ramp [shape=box fillcolor="#fff3cd" label="best = next_state_up\\nRAMP_LIMITED"]

    StartG [shape=oval fillcolor="#f8d7da" label="apply_guards(best, soc2, charge-block)"]
    GEnd [shape=oval fillcolor="#f8d7da" label="-> best, guard_fired\\nfired=true -> skip blocking"]
    g0 [shape=diamond fillcolor="#fce8e8" label="charge-block?"]
    g0r [shape=box fillcolor="#f8d7da" label="best=0\\nGUARD: charge-block until pcc>20kW"]
    g1 [shape=diamond fillcolor="#fce8e8" label="soc2 >= 100?"]
    g1r [shape=box fillcolor="#f8d7da" label="best=0\\nGUARD:BATTERY_FULL_STOP"]
    g2 [shape=diamond fillcolor="#fce8e8" label="0 <= soc2 < 6?"]
    g2r [shape=box fillcolor="#f8d7da" label="best=1\\nGUARD:CRITICAL_SOC_PROTECTION"]

    StartB [shape=oval fillcolor="#d4c5f0" label="apply_blocking()\\n(only if !guard_fired)"]
    BEnd [shape=oval fillcolor="#d4c5f0" label="-> final, changed"]
    b_same [shape=diamond fillcolor="#d4c5f0" label="best == relay_st?"]
    b_same_r [shape=box fillcolor="#d4c5f0" label="return relay_st\\nchanged=false"]
    b_dir [shape=box fillcolor="#d4c5f0" label="up = power(best) > power(relay_st)\\npwr_diff = |power(best)-power(relay_st)|"]
    b_emf [shape=diamond fillcolor="#fce8e8" label="pcc<-1020W (=-(G+120))\\n&& !up?"]
    b_emf_r [shape=box fillcolor="#f8d7da" label="EMERGENCY_FORCE\\nreturn best, changed=true"]
    b_rules [shape=box fillcolor="#d4c5f0" label="UP:   SWEET_SPOT_HOLD (|pcc|<160)\\n      TREND_BLOCK (drop_rate<-20)\\n      BAT_GUARD_BLOCK (bat1<-110)\\nDOWN: STABILIZING (stable<2)\\n      HYSTERESIS (pwr_diff<505)"]
    b_blk [shape=diamond fillcolor="#d4c5f0" label="rule applies?"]
    b_yes [shape=box fillcolor="#d4c5f0" label="return relay_st\\nchanged=false"]
    b_no [shape=box fillcolor="#d4c5f0" label="return best\\nchanged=true"]

    Start -> excess_calc -> d_unk
    d_unk -> r_unk [label="YES" color="red"]
    d_unk -> d_pcc [label="NO" color="green"]
    r_unk -> End
    d_pcc -> r_pcc [label="YES" color="red"]
    d_pcc -> d_prot [label="NO" color="green"]
    r_pcc -> End
    d_prot -> d_prot2 [label="YES" color="orange"]
    d_prot -> d_excess [label="NO" color="green"]
    d_prot2 -> r_emerg [label="YES" color="red"]
    d_prot2 -> r_target [label="NO" color="green"]
    r_emerg -> End
    r_target -> End
    d_excess -> r_insuf [label="YES" color="red"]
    d_excess -> pm [label="NO" color="green"]
    r_insuf -> End
    pm -> d_ramp
    d_ramp -> r_ramp [label="YES" color="orange"]
    d_ramp -> End [label="NO" color="green"]
    r_ramp -> End

    StartG -> g0
    g0 -> g0r [label="YES" color="red"]
    g0 -> g1 [label="NO" color="green"]
    g0r -> GEnd
    g1 -> g1r [label="YES" color="red"]
    g1 -> g2 [label="NO" color="green"]
    g1r -> GEnd
    g2 -> g2r [label="YES" color="red"]
    g2 -> GEnd [label="NO" color="green"]
    g2r -> GEnd

    StartB -> b_same
    b_same -> b_same_r [label="YES" color="#888888"]
    b_same -> b_dir [label="NO" color="green"]
    b_same_r -> BEnd
    b_dir -> b_emf
    b_emf -> b_emf_r [label="YES" color="red"]
    b_emf -> b_rules [label="NO" color="green"]
    b_emf_r -> BEnd
    b_rules -> b_blk
    b_blk -> b_yes [label="YES" color="orange"]
    b_blk -> b_no [label="NO" color="green"]
    b_yes -> BEnd
    b_no -> BEnd
}
"""

# ── Page 4: Charge-block state machine + Soyo discharge ───────────────────────
PAGE4 = """
digraph WaveshareSoyo {
    graph [
        label="fox2db v3.3.34 — Charge-block logic + Soyo discharge (RS485)"
        labelloc=t fontsize=14 fontname="Helvetica-Bold"
        rankdir=TB splines=polyline nodesep=0.4 ranksep=0.5
        bgcolor="#f8f9fa" size="11,17" ratio=fill
    ]
    node [fontname="Helvetica" fontsize=10 margin="0.18,0.08" style="filled,rounded"]
    edge [fontname="Helvetica" fontsize=10 penwidth=1.2]

    subgraph cluster_lade {
        label="CHARGE-BLOCK — keep battery empty in the morning for the >20kW midday peak" style="filled" fillcolor="#fff3cd"
        fontname="Helvetica-Bold" fontsize=10 color="#b8860b"

        L0 [shape=oval fillcolor="#ffe69c" label="step() — re-evaluated each cycle\\n(stateless, no DB event)"]
        L1 [shape=diamond fillcolor="#fce8e8" label="has_peak?\\nbest_w > 20kW today"]
        L2 [shape=diamond fillcolor="#fce8e8" label="local_hour <= peak_h?"]
        L3 [shape=diamond fillcolor="#fce8e8" label="!peak_today?\\n(pcc has not\\nreached 20kW yet)"]
        L4 [shape=diamond fillcolor="#fff3cd" label="ratio_ist valid\\n(>= 0)?"]
        L5 [shape=diamond fillcolor="#fff3cd" label="Latch (hysteresis):\\nLOCK ratio_ist<=ratio_th\\nRELEASE ratio_ist>=ratio_th+0.15\\n(default 0.5, MQTT sofar/ratio)"]
        LON [shape=box fillcolor="#f8d7da" label="CHARGE-BLOCK ACTIVE (latched)\\n-> guard -> state 0\\nconfirmed good weather"]
        LOFF [shape=box fillcolor="#d4edda" label="CHARGE-BLOCK OFF (default)\\nbad weather / undecidable /\\npeak seen / hour passed"]

        L0 -> L1
        L1 -> L2 [label="YES" color="green"]
        L1 -> LOFF [label="NO" color="#888888"]
        L2 -> L3 [label="YES" color="green"]
        L2 -> LOFF [label="NO\\npeak_h passed" color="#888888"]
        L3 -> L4 [label="YES" color="green"]
        L3 -> LOFF [label="NO\\npeak_today" color="#888888"]
        L4 -> L5 [label="YES" color="green"]
        L4 -> LOFF [label="NO\\nratio<0 undecidable" color="#888888"]
        L5 -> LON [label="latched" color="red"]
        L5 -> LOFF [label="released\\nratio>=th+0.15 bad weather" color="orange"]
    }

    subgraph cluster_soyo {
        label="Soyo discharge (max 900W, soyo/calc every 60s, RS485-TX every 3s)" style="filled" fillcolor="#d4edda"
        fontname="Helvetica-Bold" fontsize=10 color="#28a745"

        S0 [shape=oval fillcolor="#b8dfc4" label="soyo/calc"]
        Sd1 [shape=diamond fillcolor="#fce8e8" label="State != 0?\\n(EBox charging)"]
        Sd2 [shape=diamond fillcolor="#fce8e8" label="soc2 < 9%?\\n(discharge protection)"]
        Sd3 [shape=diamond fillcolor="#fce8e8" label="ebox > 200W?\\n(bat2 charging)"]
        Sd4 [shape=diamond fillcolor="#fce8e8" label="pcc > 200W?\\n(PV surplus)"]
        Sd5 [shape=diamond fillcolor="#fff3cd" label="pcc < -100W?\\n(grid import)"]
        Sw0 [shape=box fillcolor="#dddddd" label="w = 0"]
        Swc [shape=box fillcolor="#b8dfc4" label="w = |pcc| * 1.01\\n(+ night: +468W)"]
        Sws [shape=box fillcolor="#b8dfc4" label="w = 468W (night)\\nor 10W (day, standby)"]
        SNight [shape=note fillcolor="#fff9c4" label="Night = sun below horizon\\nfox::sun_pos() NOAA clear-sky, elev <= 0°\\nv3.3.34: dynamic instead of fixed 06:00/20:00"]
        Stx [shape=box fillcolor="#a8d0f5" label="RS485 frame\\n[24 56 00 21 PH PL 80 CRC]\\nCRC=(264-PH-PL)&0xFF\\nalways every 3s (keepalive 4s)"]

        S0 -> Sd1
        Sd1 -> Sw0 [label="YES" color="#888888"]
        Sd1 -> Sd2 [label="NO" color="green"]
        Sd2 -> Sw0 [label="YES" color="#888888"]
        Sd2 -> Sd3 [label="NO" color="green"]
        Sd3 -> Sw0 [label="YES" color="#888888"]
        Sd3 -> Sd4 [label="NO" color="green"]
        Sd4 -> Sw0 [label="YES" color="#888888"]
        Sd4 -> Sd5 [label="NO" color="green"]
        Sd5 -> Swc [label="YES" color="orange"]
        Sd5 -> Sws [label="NO" color="green"]
        Sw0 -> Stx
        Swc -> Stx
        Sws -> Stx
        Sws -> SNight [style=dashed color="#888888" arrowhead=none]
    }
}
"""

PAGES = [PAGE1, PAGE2, PAGE3, PAGE4]


def render(dot_src: str, out_path: Path) -> Path:
    dot_file = out_path.with_suffix(".dot")
    dot_file.write_text(dot_src)
    result = subprocess.run(
        ["dot", "-Tpdf", str(dot_file), "-o", str(out_path)],
        capture_output=True, text=True
    )
    # keep .dot (checked in)
    if result.returncode != 0:
        print(f"ERROR {out_path.name}: {result.stderr[:200]}")
        return None
    print(f"OK  -> {out_path}")
    return out_path


def main():
    pages = []
    for i, src in enumerate(PAGES, 1):
        p = render(src, OUT / f"waveshare_v3_page{i}.pdf")
        if p:
            pages.append(str(p))

    if len(pages) == len(PAGES):
        out = OUT / "waveshare_v3_flowchart.pdf"
        result = subprocess.run(["pdfunite"] + pages + [str(out)],
                                capture_output=True, text=True)
        if result.returncode == 0:
            print(f"\nCombined -> {out}")
            # single pages kept (checked in)
        else:
            print(f"pdfunite error: {result.stderr}")


if __name__ == "__main__":
    main()
