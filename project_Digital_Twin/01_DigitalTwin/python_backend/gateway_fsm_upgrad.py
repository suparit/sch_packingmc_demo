# -*- coding: utf-8 -*-
"""
🔥 CENTRAL GATEWAY (UPGRAD) — เวอร์ชันที่มีสะพานไปฮาร์ดแวร์จริงผ่าน Rust Modbus Bridge

ต่างจาก `gateway_fsm.py` ตรงที่ไฟล์นี้ "ต่อออก" ไปหา Rust I/O Layer เพิ่มอีกทาง
เพื่อซิงค์สถานะกล้อง/เซนเซอร์กับบอร์ดจริง ส่วนที่เหลือ (FSM, WebSocket, จอ TouchGFX)
ทำงานเหมือนกันทุกอย่าง เพราะใช้โมดูล `hmi_link.py` ตัวเดียวกัน

⚠️ เรื่องพอร์ต — อ่านก่อนแก้:
   เดิมไฟล์นี้ต่อออกไปที่ 8766 ซึ่งเป็นพอร์ตเดียวกับที่จอ TouchGFX ต่อเข้ามา
   ทั้งสองฝ่ายเป็น client ทั้งคู่ → ต่อกันไม่ติด เปิดไฟล์นี้แล้วจอขึ้นเลข 0 หมดทุกช่อง
   ตอนนี้แยกออกจากกันแล้ว:
       8766 = TCP server รอจอ TouchGFX ต่อเข้ามา  (เหมือน gateway_fsm.py)
       8767 = TCP client ต่อออกไปหา Rust bridge   (เปิดใช้เมื่อ RUST_BRIDGE=1 เท่านั้น)
   ถ้าจะใช้ Rust bridge ต้องแก้ PYTHON_BRIDGE_ADDR ใน rust_bridge/src/main.rs เป็น 8767 แล้ว cargo build ใหม่

วิธีรัน
-------
    python gateway_fsm_upgrad.py                       # จอ + เว็บ (ไม่ต่อ Rust)
    set RUST_BRIDGE=1 && python gateway_fsm_upgrad.py  # เปิดสะพานไปบอร์ดจริงด้วย
"""

import sys
import socket
import time
import os
import json
import asyncio
import threading
import sqlite3
import math
import select
import random
from datetime import datetime
import websockets

from hmi_link import HmiLink

# console ของ Windows ไทยเป็น cp874 พอ stdout ถูก redirect (รันเป็น background/service)
# emoji ในบรรทัด print จะทำให้โปรเซสตายด้วย UnicodeEncodeError ตั้งแต่บรรทัดแรกๆ
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ==================================================
# ⚙️ CONFIGURATION
# ==================================================
LOOP_DELAY      = 0.02     # 20 ms
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DB_FILE         = os.path.join(BASE_DIR, "smd_packing_analytics.db")

# 🔌 สะพานไปฮาร์ดแวร์จริง (Rust Modbus Bridge) — ปิดไว้เป็นค่าเริ่มต้น
RUST_ENABLED    = os.environ.get("RUST_BRIDGE", "0") == "1"
RUST_HOST       = os.environ.get("RUST_HOST", "127.0.0.1")
RUST_PORT       = int(os.environ.get("RUST_PORT", "8767"))
RUST_RETRY_SEC  = 3.0      # เว้นระยะก่อน connect ใหม่ ไม่งั้นยิงทุก 20 ms ตอนบอร์ดไม่ได้เสียบ

STATES = [
    'LOAD_CARRIER', 'INDEX_CARRIER', 'POWER_ON', 'SET_PARAMS',
    'SENSOR_CHECK_CARRIER', 'READY', 'LOAD_PART', 'VISION',
    'CHECK_TEMP', 'FEED_CARRIER', 'COUNT_PROCESS', 'COUNT_CHECK',
    'COUNT_ACCUMULATE', 'SEAL_PROCESS', 'VISION_QC', 'TAKEUP_REEL', 'ALARM'
]

system_data = {
    "current_state": "LOAD_CARRIER",
    "running": False,
    "mode": "auto",
    "step_allowed": False,
    "cycles": 0,
    "speed_mul": 1.0,
    "ip0": 0, "ip1": 0,
    "op0": 0, "op1": 0,
    "camera1_count": 0,
    "encoder_count": 0,
    "pieces_count": 0,
    "target_pieces": 200,
    "pitch": 24,
    "current_temp": 190,
    "predictive_warning": ""
}

step_history_cache = {"FEED_CARRIER": [], "SEAL_PROCESS": []}
connected_clients = set()
trigger_reset_timer = False
last_get_state_log = 0.0
last_state_before_alarm = "LOAD_CARRIER"

# 🔗 สะพานไปจอ TouchGFX — TCP server 127.0.0.1:8766 (โค้ดจริงอยู่ใน hmi_link.py)
hmi = HmiLink(system_data, DB_FILE, BASE_DIR)

def record_alarm(msg, count_ng=False):
    hmi.record_alarm(msg, count_ng)

# ==================================================
# 🔌 HARDWARE LINK (Rust I/O Layer) — optional
# ==================================================
rust_socket = None
_rust_retry_at = 0.0

def connect_to_rust_layer():
    global rust_socket, _rust_retry_at
    if rust_socket is not None:
        return True
    if not RUST_ENABLED or time.time() < _rust_retry_at:
        return False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.1)
        s.connect((RUST_HOST, RUST_PORT))
        rust_socket = s
        print(f"🔌 [HARDWARE LINK] Connection established with Rust I/O Layer ({RUST_HOST}:{RUST_PORT}).")
        return True
    except Exception:
        rust_socket = None
        _rust_retry_at = time.time() + RUST_RETRY_SEC
        return False

def sync_with_rust_layer():
    """ส่งสถานะ/เอาต์พุตลงบอร์ดจริง แล้วอ่านค่าอินพุต (ip0) กลับมา
    คืนค่า ip0 ล่าสุด — ถ้าไม่ได้เปิด RUST_BRIDGE จะคืนค่าเดิมเฉยๆ"""
    global rust_socket
    if not connect_to_rust_layer():
        return system_data["ip0"]
    try:
        payload = json.dumps({
            "current_state": system_data["current_state"],
            "running": system_data["running"],
            "op0": system_data["op0"],
            "ip0": system_data["ip0"],
            "cycles": system_data["cycles"],
        }) + "\n"
        rust_socket.sendall(payload.encode('utf-8'))
        ready = select.select([rust_socket], [], [], 0.02)
        if ready[0]:
            resp = rust_socket.recv(1024).decode('utf-8')
            if not resp:
                raise ConnectionError("rust layer closed")
            return json.loads(resp.strip()).get("ip0", system_data["ip0"])
    except Exception:
        try: rust_socket.close()
        except Exception: pass
        rust_socket = None
        _reset_rust_backoff()
    return system_data["ip0"]

def _reset_rust_backoff():
    global _rust_retry_at
    _rust_retry_at = time.time() + RUST_RETRY_SEC

# ==================================================
# 🎮 คำสั่งจาก operator (ใช้ร่วมกันทั้งจอ TouchGFX และเว็บ 3D Twin)
# ==================================================
def apply_decision(accept):
    """ยืนยัน/ปฏิเสธผลตรวจของ operator ที่สเต็ปเช็คพอยต์ (VISION ฯลฯ)
    คืน True ถ้า FSM กำลังรอคำตัดสินอยู่จริง — ผู้เรียกเอาไปตอบ ACK ต่อได้"""
    global trigger_reset_timer, last_state_before_alarm

    if not system_data["step_allowed"]:
        print("⚠️ [DECISION IGNORED] FSM not accepting decisions now.")
        return False

    system_data["step_allowed"] = False
    trigger_reset_timer = True

    if accept:
        state_idx = STATES.index(system_data["current_state"])
        system_data["current_state"] = STATES[(state_idx + 1) % len(STATES)]
        print("🕹️ [DECISION]: Operator Clicked OK")
    else:
        system_data["predictive_warning"] = "⚠️ ERROR: OPERATOR REJECTION (SEMI-AUTO NG)"
        record_alarm("OPERATOR REJECTION (SEMI-AUTO NG)", count_ng=True)
        # จำสเต็ปที่พังไว้ด้วย ไม่งั้นกด RESET แล้วจะเด้งกลับไปสเต็ปเก่าค้างของ alarm ครั้งก่อน
        last_state_before_alarm = system_data["current_state"]
        system_data["current_state"] = "ALARM"
        print("🕹️ [DECISION]: Operator Clicked NG")
    return True

def handle_gui_action(cmd_json):
    """คำสั่งที่จอ TouchGFX ยิงเข้ามาทาง TCP 8766 (hmi_link แกะ JSON ให้แล้ว)
    รองรับชุดเดียวกับฝั่งเว็บ เพื่อให้คุมเครื่องจากจอล้วนๆ ได้โดยไม่ต้องเปิดเบราว์เซอร์"""
    global trigger_reset_timer, last_state_before_alarm
    act = cmd_json.get("action")

    if act == "START":
        system_data["running"] = True
        system_data["predictive_warning"] = ""
        trigger_reset_timer = True
        print("🎮 [TOUCHGFX CMD]: START MACHINE")
    elif act == "STOP":
        system_data["running"] = False
        trigger_reset_timer = True
        print("🎮 [TOUCHGFX CMD]: STOP MACHINE")
    elif act == "RESET":
        system_data["running"] = False
        system_data["pieces_count"] = 0
        system_data["cycles"] = 0
        system_data["camera1_count"] = 0
        system_data["encoder_count"] = 0
        system_data["step_allowed"] = False
        system_data["predictive_warning"] = ""
        hmi.reset_ng()
        system_data["current_state"] = "LOAD_CARRIER"
        trigger_reset_timer = True
        print("🧹 [TOUCHGFX CMD]: RESET BATCH")
    elif act == "ESTOP":
        system_data["running"] = False
        if system_data["current_state"] != "ALARM":
            last_state_before_alarm = system_data["current_state"]
        system_data["current_state"] = "ALARM"
        system_data["op0"] = 0x08
        system_data["predictive_warning"] = "🚨 EMERGENCY STOP ENGAGED"
        record_alarm("EMERGENCY STOP PRESSED (HMI)")
        trigger_reset_timer = True
        print("🚨 [TOUCHGFX CMD]: EMERGENCY STOP")
    elif act == "MODE":
        system_data["mode"] = cmd_json.get("mode", "auto")
        print(f"🔄 [TOUCHGFX CMD]: Switched Mode to {system_data['mode'].upper()}")
    elif act == "SPEED":
        system_data["speed_mul"] = float(cmd_json.get("value", 1.0))
    elif act == "DECISION":
        # 🎥 ปุ่ม PASS/NG ของสเต็ป VISION บนจอ — จำเป็นต้องมี ไม่งั้นเครื่องค้างที่ VISION
        # เมื่อสั่งงานจากจออย่างเดียวโดยไม่เปิดหน้าเว็บ
        apply_decision(bool(cmd_json.get("value", True)))
    elif act == "SET_PARAMS":
        # ตั้งค่าจากแป้นพิมพ์บนจอ HMI — ค่าใหม่จะ broadcast กลับไปทั้ง HMI และเว็บ 3D Twin ทันที
        if "target_pieces" in cmd_json:
            system_data["target_pieces"] = max(1, int(cmd_json["target_pieces"]))
        if "pitch" in cmd_json:
            system_data["pitch"] = max(1, int(cmd_json["pitch"]))
        # พารามิเตอร์ที่เหลือจากหน้า Settings (10 ช่อง) เก็บดิบไว้ให้หน้าเว็บ/รายงานเอาไปใช้ต่อ
        extra = {k: v for k, v in cmd_json.items() if k not in ("action", "target_pieces", "pitch")}
        if extra:
            system_data.setdefault("machine_params", {}).update(extra)
        print(f"⚙️ [TOUCHGFX PARAM]: target={system_data['target_pieces']} pcs, "
              f"pitch={system_data['pitch']} mm" + (f", +{len(extra)} params" if extra else ""))

hmi.set_command_handler(handle_gui_action)

# ==================================================
# 🗄️ SQLITE
# ==================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS machine_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, state_name TEXT NOT NULL, duration_sec REAL NOT NULL, control_mode TEXT NOT NULL, current_cycle INTEGER NOT NULL, status TEXT NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS production_summary (id INTEGER PRIMARY KEY AUTOINCREMENT, end_timestamp TEXT NOT NULL, cycle_number INTEGER NOT NULL, total_duration_sec REAL NOT NULL)")
    conn.commit()
    conn.close()

def log_state_transition_to_sql(state_name, duration_sec, mode, cycles, status="NORMAL"):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        cursor.execute("INSERT INTO machine_logs (timestamp, state_name, duration_sec, control_mode, current_cycle, status) VALUES (?, ?, ?, ?, ?, ?)", (now_str, state_name, round(duration_sec, 3), mode, cycles, status))
        conn.commit()
        conn.close()
    except Exception: pass

def log_cycle_complete_to_sql(cycle_number, total_duration_sec):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("INSERT INTO production_summary (end_timestamp, cycle_number, total_duration_sec) VALUES (?, ?, ?)", (now_str, cycle_number, round(total_duration_sec, 2)))
        conn.commit()
        conn.close()
    except Exception: pass

def evaluate_predictive_ai(step_name, current_duration):
    history = step_history_cache[step_name]
    if len(history) < 3:
        history.append(current_duration)
        return False
    mean_val = sum(history) / len(history)
    variance = sum((x - mean_val) ** 2 for x in history) / len(history)
    std_dev = math.sqrt(variance)
    is_anomaly = current_duration > (mean_val + 1.5 * std_dev) or current_duration > 1.35
    history.append(current_duration)
    if len(history) > 5: history.pop(0)
    return is_anomaly

# ==================================================
# 🧠 FSM MAIN BRAIN LOOP
# ==================================================
def fsm_brain_loop():
    global system_data, trigger_reset_timer, last_state_before_alarm
    state_index = STATES.index("LOAD_CARRIER")
    last_transition_time = time.time()
    cycle_start_time = time.time()

    last_printed_state = ""
    last_printed_temp = 0

    durations = {
        'LOAD_CARRIER': 0.5, 'INDEX_CARRIER': 0.8, 'POWER_ON': 0.5, 'SET_PARAMS': 0.5,
        'SENSOR_CHECK_CARRIER': 0.4, 'READY': 0.5, 'LOAD_PART': 0.8, 'VISION': 0.4,
        'CHECK_TEMP': 0.4, 'FEED_CARRIER': 1.0, 'COUNT_PROCESS': 0.5, 'COUNT_CHECK': 0.5,
        'COUNT_ACCUMULATE': 0.4, 'SEAL_PROCESS': 1.0, 'VISION_QC': 0.4, 'TAKEUP_REEL': 1.0,
        'ALARM': 0.5
    }
    checkpoints = ['SENSOR_CHECK_CARRIER', 'VISION', 'CHECK_TEMP', 'COUNT_CHECK', 'VISION_QC']

    while True:
        try:
            now = time.time()
            if trigger_reset_timer:
                state_index = STATES.index(system_data["current_state"])
                last_transition_time = now
                cycle_start_time = now
                trigger_reset_timer = False

            curr = STATES[state_index]
            system_data["current_state"] = curr

            if curr != last_printed_state or (curr == "CHECK_TEMP" and system_data["current_temp"] != last_printed_temp):
                status_indicator = "⚙️ RUNNING" if system_data["running"] else "🛑 IDLE"
                if curr == "ALARM": status_indicator = "🚨 TRIPPED"

                if curr == "CHECK_TEMP":
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] FSM State: {curr} ({system_data['current_temp']}°C) | Status: {status_indicator} | Mode: {system_data['mode'].upper()} | Count: {system_data['pieces_count']}/{system_data['target_pieces']}")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] FSM State: {curr} | Status: {status_indicator} | Mode: {system_data['mode'].upper()} | Count: {system_data['pieces_count']}/{system_data['target_pieces']}")

                last_printed_state = curr
                last_printed_temp = system_data["current_temp"]

            if system_data["running"] and curr != 'ALARM':
                simulated_delay = 0.0
                if curr in ["FEED_CARRIER", "SEAL_PROCESS"] and system_data["cycles"] in [3, 4]: simulated_delay = 0.55

                target_dur = (durations.get(curr, 0.5) + simulated_delay) / system_data["speed_mul"]

                if system_data["mode"] == "auto":
                    if curr == 'SENSOR_CHECK_CARRIER' and (now - last_transition_time >= target_dur):
                        if random.random() < 0.015:
                            system_data["predictive_warning"] = "⚠️ ERROR: CARRIER TAPE JAMMED"
                            record_alarm("CARRIER TAPE JAMMED")
                            print(f"🚨 [FAULT INJECTED]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue

                    # ทอยความน่าจะเป็นของงานเสียแค่ "ครั้งเดียว" ตอนกล้องตรวจเสร็จ
                    # (not step_allowed = ยังไม่ได้เปิดให้ operator ตัดสิน)
                    # ⚠️ เวอร์ชันเดิมของไฟล์นี้เช็ค step_allowed == True → ทอยใหม่ทุก 20 ms ระหว่างรอคนกด
                    #    ทำให้เด้ง ALARM ~78% ภายใน 2 วินาที กด PASS แทบไม่ทัน
                    elif curr == 'VISION' and (now - last_transition_time >= target_dur) and not system_data["step_allowed"]:
                        if random.random() < 0.02:
                            system_data["predictive_warning"] = "⚠️ ERROR: PART MISSING OR WRONG SIDE"
                            record_alarm("PART MISSING OR WRONG SIDE", count_ng=True)
                            print(f"🚨 [FAULT INJECTED]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue

                    elif curr == 'CHECK_TEMP':
                        rand_roll = random.random()
                        if rand_roll < 0.85:   system_data["current_temp"] = random.choice([189, 190, 191])
                        elif rand_roll < 0.98: system_data["current_temp"] = random.randint(170, 188)
                        else:                  system_data["current_temp"] = random.randint(201, 215)

                        temp = system_data["current_temp"]
                        if 189 <= temp <= 191: pass
                        elif temp > 200:
                            system_data["predictive_warning"] = "🚨 CRITICAL: HEATER OVERHEATED (OVER 200°C)"
                            record_alarm(f"HEATER OVERHEATED ({temp} C)")
                            print(f"🚨 [CRITICAL]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue
                        else:
                            last_transition_time = now - target_dur + 0.02
                            time.sleep(0.1)
                            continue

                    elif curr == 'COUNT_CHECK' and (now - last_transition_time >= target_dur):
                        if random.random() < 0.01:
                            system_data["predictive_warning"] = "⚠️ ERROR: COUNT MISMATCH (ENCODER VS CAMERA)"
                            record_alarm("COUNT MISMATCH (ENCODER VS CAMERA)", count_ng=True)
                            print(f"🚨 [FAULT INJECTED]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue

                    elif curr == 'VISION_QC' and (now - last_transition_time >= target_dur):
                        if random.random() < 0.015:
                            system_data["predictive_warning"] = "⚠️ ERROR: BAD SEALING DETECTED"
                            record_alarm("BAD SEALING DETECTED", count_ng=True)
                            print(f"🚨 [FAULT INJECTED]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue

                # สเต็ป VISION (กล้องตรวจชิ้นงาน) หยุดรอ operator กด PASS/NG เสมอ แม้อยู่โหมด auto
                # — ส่วนเช็คพอยต์อื่นยังหยุดเฉพาะโหมด semi เหมือนเดิม
                if curr in checkpoints and (system_data["mode"] == "semi" or curr == 'VISION') and not system_data["step_allowed"] and (now - last_transition_time >= target_dur):
                    system_data["step_allowed"] = True

                elif not system_data["step_allowed"] and (now - last_transition_time >= target_dur):
                    actual_spent = now - last_transition_time

                    if curr in ["FEED_CARRIER", "SEAL_PROCESS"]:
                        has_anomaly = evaluate_predictive_ai(curr, actual_spent)
                        if has_anomaly and system_data["mode"] == "auto":
                            system_data["predictive_warning"] = f"⚠️ AI WARNING: High Friction Detected at {curr}!"

                    log_state_transition_to_sql(curr, actual_spent, system_data["mode"], system_data["cycles"])

                    if curr == 'FEED_CARRIER':
                        system_data["camera1_count"] += 1
                        system_data["encoder_count"] += 1
                        state_index = STATES.index('COUNT_PROCESS')
                    elif curr == 'COUNT_CHECK':
                        if system_data["camera1_count"] == system_data["encoder_count"]: state_index = STATES.index('COUNT_ACCUMULATE')
                        else:
                            system_data["predictive_warning"] = "⚠️ ERROR: COUNT MISMATCH"
                            record_alarm("COUNT MISMATCH", count_ng=True)
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                    elif curr == 'COUNT_ACCUMULATE':
                        system_data["pieces_count"] += 1
                        if system_data["pieces_count"] >= system_data["target_pieces"]:
                            system_data["predictive_warning"] = "🎉 SUCCESS: PRODUCTION BATCH COMPLETED!"
                            print(f"\n🏁 [BATCH COMPLETE]: {system_data['predictive_warning']}\n")
                            system_data["running"] = False
                            state_index = STATES.index('READY')
                        else:
                            state_index = STATES.index('SEAL_PROCESS')
                    elif curr == 'TAKEUP_REEL':
                        total_cycle_time = now - cycle_start_time
                        system_data["cycles"] += 1
                        log_cycle_complete_to_sql(system_data["cycles"], total_cycle_time)

                        if not system_data["running"]: state_index = STATES.index('READY')
                        else:                          state_index = STATES.index('LOAD_CARRIER')
                        cycle_start_time = now
                    else:
                        state_index = (state_index + 1) % len(STATES)

                    last_transition_time = now

            if system_data["current_state"] != 'ALARM':
                OP0 = 0x00
                if system_data["running"]:
                    if curr == 'FEED_CARRIER':     OP0 |= 0x01
                    elif curr == 'SEAL_PROCESS':   OP0 |= 0x02
                    elif curr == 'TAKEUP_REEL':    OP0 |= 0x04
                system_data["op0"] = OP0
            else: system_data["op0"] = 0x08

            # 🖥️ ปั๊มข้อมูลไปจอ TouchGFX + รับปุ่มกดจากจอกลับมา (TCP 8766)
            hmi.poll()
            # 🔌 ซิงค์กับบอร์ดจริงผ่าน Rust I/O Layer (ทำงานเมื่อ RUST_BRIDGE=1)
            system_data["ip0"] = sync_with_rust_layer()

            time.sleep(LOOP_DELAY)
        except Exception as e: time.sleep(0.5)

# ==================================================
# 🌐 WEBSOCKET BRIDGE SERVER
# ==================================================
async def ws_handler(websocket):
    global system_data, trigger_reset_timer, last_state_before_alarm, last_get_state_log
    connected_clients.add(websocket)
    print(f"📡 [WS CONNECT] Client attached to server core. Active nodes = {len(connected_clients)}")
    try:
        async for message in websocket:
            data = json.loads(message)
            action = data.get("action")

            if action == "START":
                if system_data["pieces_count"] >= system_data["target_pieces"]:
                    system_data["predictive_warning"] = "⚠️ CANNOT START: BATCH ALREADY DONE! PLEASE PRESS RESET FIRST"
                    continue
                system_data["running"] = True
                system_data["predictive_warning"] = ""
                trigger_reset_timer = True
                print("🕹️ [CMD: START] Main machine sequence engaged.")
            elif action == "STOP":
                system_data["running"] = False
                trigger_reset_timer = True
                print("🕹️ [CMD: STOP] Main machine sequence paused.")
            elif action == "ESTOP":
                system_data["running"] = False
                if system_data["current_state"] != "ALARM": last_state_before_alarm = system_data["current_state"]
                system_data["current_state"] = "ALARM"
                system_data["op0"] = 0x08
                system_data["predictive_warning"] = "🚨 EMERGENCY STOP ENGAGED"
                record_alarm("EMERGENCY STOP PRESSED")
                trigger_reset_timer = True
                print(f"🚨 [EMERGENCY STOP] Interlock triggered! Saved breaking step: {last_state_before_alarm}")
            elif action == "RESET":
                trigger_reset_timer = True
                if system_data["current_state"] == "ALARM":
                    system_data["running"] = False
                    system_data["predictive_warning"] = ""
                    system_data["current_state"] = last_state_before_alarm
                    system_data["op0"] = 0x00
                    print(f"🔄 [CMD: RESET] Alarm unlatched. Resuming step -> [{last_state_before_alarm}].")
                else:
                    system_data["running"] = False
                    system_data["predictive_warning"] = ""
                    system_data["current_state"] = "LOAD_CARRIER"
                    system_data["cycles"] = 0
                    system_data["camera1_count"] = 0
                    system_data["encoder_count"] = 0
                    system_data["pieces_count"] = 0
                    system_data["step_allowed"] = False
                    hmi.reset_ng()
                    print("🧹 [CMD: FULL RESET] Lot parameters wiped to 0. Ready for new lot production.")
            elif action == "MODE":
                system_data["mode"] = data.get("mode", "auto")
                print(f"🔄 [COMMAND]: Switched Mode to {system_data['mode'].upper()}")
            elif action == "SPEED":
                system_data["speed_mul"] = float(data.get("value", 1.0))
            elif action == "SET_PARAMS":
                system_data["target_pieces"] = max(1, int(data.get("target_pieces", system_data["target_pieces"])))
                system_data["pitch"] = max(1, int(data.get("pitch", system_data["pitch"])))
                print(f"⚙️ [PARAM UPDATE]: target={system_data['target_pieces']} pcs, pitch={system_data['pitch']} mm")

            elif action == "GET_STATE":
                try:
                    now = time.time()
                    if now - last_get_state_log > 1.0:
                        print(f"🔄 [WS SYNC] Sending LIVE_SYNC to client | active={len(connected_clients)}")
                        last_get_state_log = now
                    await websocket.send(json.dumps({"type": "LIVE_SYNC", "system": system_data}))
                except: pass

            # 📊 [ท่อข้อความเชื่อมตรงความต้องการ]: แกะดักประวัติข้อมูลดิบ 100 แถวล่าสุดส่งสวนกลับเข้าหน้าเว็บ analytics.html
            elif action == "GET_HISTORY":
                try:
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("SELECT state_name, duration_sec, current_cycle, control_mode, timestamp FROM machine_logs ORDER BY id DESC LIMIT 100")
                    rows = cursor.fetchall()
                    conn.close()

                    await websocket.send(json.dumps({
                        "type": "HISTORY_RESPONSE",
                        "data": [{"state": r[0], "duration": r[1], "cycle": r[2], "mode": r[3], "time": r[4]} for r in reversed(rows)]
                    }))
                    print("📊 [ANALYTICS SYNC] Transmitted 100 recent SQL logs to Analytics Dashboard successfully.")
                except Exception as e:
                    print(f"⚠️ [ANALYTICS ERROR] Failed to query SQLite history: {e}")

            elif action == "DECISION":
                recv_val = data.get("value", True)
                accepted = apply_decision(bool(recv_val))
                try:
                    ack = {"type": "DECISION_ACK", "accepted": accepted}
                    if not accepted:
                        ack["reason"] = "not_allowed"
                    await websocket.send(json.dumps(ack))
                except Exception: pass
    except websockets.exceptions.ConnectionClosed: pass
    finally:
        connected_clients.remove(websocket)
        print(f"🔴 [WS DISCONNECT] Client node detached. Left nodes = {len(connected_clients)}")

async def broadcast_state():
    while True:
        if connected_clients:
            try:
                msg = json.dumps({"type": "LIVE_SYNC", "system": system_data})
                await asyncio.gather(*[client.send(msg) for client in connected_clients], return_exceptions=True)
            except: pass
        await asyncio.sleep(0.05)

async def main_async():
    init_db()
    hmi.start()
    threading.Thread(target=fsm_brain_loop, daemon=True).start()
    asyncio.create_task(broadcast_state())

    rust_line = (f"➔ HW Link   : tcp://{RUST_HOST}:{RUST_PORT} (Rust bridge)"
                 if RUST_ENABLED else "➔ HW Link   : disabled (set RUST_BRIDGE=1 to enable)")
    print("\n" + "╔" + "═" * 58 + "╗")
    print("║ 🔥 [CENTRAL GATEWAY - UPGRAD] : CONTROL MATRIX IS ACTIVE ║")
    print("╚" + "═" * 58 + "╝")
    print("  ➔ Host Core : ws://localhost:8765")
    print("  ➔ GUI Core  : tcp://127.0.0.1:8766")
    print(f"  {rust_line}\n")

    async with websockets.serve(ws_handler, "0.0.0.0", 8765): await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main_async())
