import sys
import time
import os
import json
import asyncio
import threading
import sqlite3
import math
import random
from datetime import datetime
import websockets

from hmi_link import (HmiLink, estop_enter_alarm, can_accept_decision, resolve_reset_target,
                      apply_new_batch,
                      RESET_LOG_ALARM_CLEAR, RESET_LOG_NEW_BATCH, RESET_LOG_IGNORED_RUNNING)

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

# ==================================================
# 🎲 FAULT INJECTION (จำลอง) — สวิตช์เปิด/ปิดการสุ่มโยน fault ใส่ตัวเอง
# ==================================================
# มีจุดที่ "แกล้งพัง" ตัวเองอยู่ 5 จุด (SENSOR_CHECK_CARRIER / VISION / CHECK_TEMP /
# COUNT_CHECK / VISION_QC) ไว้โชว์ว่าระบบจับ error แล้วเข้า ALARM ได้จริง
# ไฟล์นี้ไม่มีสะพานไปฮาร์ดแวร์ (ไม่มี RUST_BRIDGE) จึง **เปิดไว้เป็นค่าเริ่มต้นเหมือนเดิม**
# ปิดได้เมื่ออยากรันยาวดูว่าเดินครบ batch ไหม โดยไม่มี ALARM ปลอมมากวน:
#     FAULT_SIM=0  → ปิด
#     FAULT_SIM=1  → เปิด (เท่ากับค่าเริ่มต้น)
# หมายเหตุ: ตัวแปรชื่อเดียวกันนี้อยู่ใน gateway_fsm_upgrad.py ด้วย ต่างกันแค่ที่นั่น
# ค่าเริ่มต้นจะปิดเองเมื่อ RUST_BRIDGE=1 เพราะกำลังต่อบอร์ดจริง
_FAULT_SIM_ENV  = os.environ.get("FAULT_SIM")
FAULT_SIM       = True if _FAULT_SIM_ENV is None else (_FAULT_SIM_ENV == "1")
FAULT_SIM_SRC   = "ค่าเริ่มต้นของไฟล์นี้" if _FAULT_SIM_ENV is None else f"ถูกบังคับด้วย FAULT_SIM={_FAULT_SIM_ENV}"

# ==================================================
# 🏷️ LOG TAG — บอกที่มาของตัวเลขทุกบรรทัด (console เท่านั้น payload ไม่เปลี่ยน)
# ==================================================
# ไฟล์นี้ **ไม่มีสะพานไปฮาร์ดแวร์เลย** ทุกค่าที่เห็นเป็นค่าจำลองในโค้ดทั้งหมด
# จึงติดป้าย [SIM] ตายตัว — ถ้าต้องการค่าจากบอร์ดจริงต้องใช้ gateway_fsm_upgrad.py
# ที่ต่อกับ rust_bridge (พอร์ต 8767) แล้วดูป้าย [REAL] ที่นั่น
TAG_SIM = "[SIM] "

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

# 🔗 สะพานไปจอ TouchGFX — TCP server 127.0.0.1:8766
#    โค้ดจริงอยู่ใน hmi_link.py ใช้ร่วมกับ gateway_fsm_upgrad.py เพื่อไม่ให้สองไฟล์แยกกันเดิน
hmi = HmiLink(system_data, DB_FILE, BASE_DIR)

def record_alarm(msg, count_ng=False):
    hmi.record_alarm(msg, count_ng)

# ==================================================
# 🎮 คำสั่งจาก operator (ใช้ร่วมกันทั้งจอ TouchGFX และเว็บ 3D Twin)
# ==================================================
def apply_decision(accept):
    """ยืนยัน/ปฏิเสธผลตรวจของ operator ที่สเต็ปเช็คพอยต์ (VISION ฯลฯ)
    คืน True ถ้า FSM กำลังรอคำตัดสินอยู่จริง — ผู้เรียกเอาไปตอบ ACK ต่อได้
    ข้อ 6.3 — ต้อง block 2 ชั้นอิสระ (state guard + flag guard) ไม่พึ่ง step_allowed ตัวเดียว"""
    global trigger_reset_timer, last_state_before_alarm

    if not can_accept_decision(system_data):
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
        # จำสเต็ปที่พังไว้ด้วย ไม่งั้นกด RESET แล้วจะเด้งกลับไปสเต็ปเก่าค้างของ alarm ครั้งก่อน
        # ใช้ตัวช่วยร่วมจาก hmi_link.py ตัวเดียวกับที่ ESTOP ใช้ (ข้อ 6.2)
        last_state_before_alarm = estop_enter_alarm(
            system_data, record_alarm, last_state_before_alarm,
            "OPERATOR REJECTION (SEMI-AUTO NG)", count_ng=True)
        print("🕹️ [DECISION]: Operator Clicked NG")
    return True


def trigger_estop(reason, tag="COMMAND"):
    """ข้อ 6.2 — ESTOP: global handler เข้าได้จากทุก state เรียกใช้ร่วมกันทั้ง TCP
    (handle_gui_action) และ WS (ws_handler) เป็นจุดเดียวที่แก้แล้วได้ผลทั้งคู่
    (กฎเหล็ก: logic ร่วมของ DECISION/RESET ต้องมีที่เดียว)"""
    global trigger_reset_timer, last_state_before_alarm
    system_data["running"] = False
    last_state_before_alarm = estop_enter_alarm(system_data, record_alarm, last_state_before_alarm, reason)
    system_data["op0"] = 0x08
    system_data["predictive_warning"] = "🚨 EMERGENCY STOP ENGAGED"
    trigger_reset_timer = True
    print(f"🚨 [{tag}]: EMERGENCY STOP! Saved break step: {last_state_before_alarm}")


def apply_reset(tag="RESET"):
    """ข้อ 6.4 — RESET: logic เดียว ใช้ร่วมกันทั้ง TCP และ WS แตกเป็น 2 กิ่งที่แยกกันขาดด้วย
    `current_state == ALARM` — **กิ่งเดียวเท่านั้นที่ทำงานต่อ 1 ครั้งที่กดปุ่ม**

      กิ่งที่ 1 (ข้อ 6.4.1) current_state == ALARM      → ปลด ALARM กลับ last_state_before_alarm
                                                          counter คงเดิม 🔴 safety-critical ห้ามแก้
      กิ่งที่ 2 (ข้อ 6.4.2) current_state != ALARM
                            AND running == false        → เริ่ม batch ใหม่ กลับ LOAD_CARRIER counter = 0
      ไม่เข้ากิ่งไหนเลย (ข้อ 6.4.4)                      → ปฏิเสธ ไม่เปลี่ยนอะไรสักตัว

    คืน True เมื่อกิ่งใดกิ่งหนึ่งทำงานสำเร็จ / False เมื่อถูกปฏิเสธ (ข้อ 6.4.4 — ให้ชั้นบนเอาไปทำ ACK
    ต่อได้โดยไม่ต้องแก้ logic ซ้ำ) · ทุกทางออกต้องมี log 1 บรรทัดเสมอ ห้าม ignore เงียบ"""
    global trigger_reset_timer, last_state_before_alarm

    # ==== ข้อ 6.4.3 ชั้นที่ 1 — เช็ค ALARM ก่อนเป็นอันดับแรกสุด แล้ว return ทันที ====
    # 🔴 ห้ามให้โค้ดไหลต่อลงไปถึงกิ่งที่ 2 ในการกดครั้งเดียวกันเด็ดขาด ไม่งั้นกิ่งที่ 2 จะกลายเป็น
    #    ช่องปลด ALARM ทางอ้อม (= บั๊ก safety ตัวเดียวกับที่เพิ่งปิดไป)
    if system_data["current_state"] == "ALARM":
        # ---- กิ่งที่ 1 (ข้อ 6.4.1) ห้ามแก้แม้แต่ขั้นตอนเดียว · ห้ามแตะ counter ----
        target = resolve_reset_target(system_data, last_state_before_alarm)
        last_state_before_alarm = None
        system_data["running"] = False
        system_data["predictive_warning"] = ""
        system_data["current_state"] = target
        system_data["op0"] = 0x00
        trigger_reset_timer = True
        print(f"🔄 [{tag}] {RESET_LOG_ALARM_CLEAR}: Alarm cleared! Restored to state: [{target}]. "
              f"Retained count: {system_data['pieces_count']}/{system_data['target_pieces']} pcs.")
        return True

    # ==== กิ่งที่ 2 (ข้อ 6.4.2) — เริ่ม batch ใหม่ ====
    # apply_new_batch() มี guard `current_state != ALARM` เขียนอยู่ในตัวเองอีกชั้น (ข้อ 6.4.3 ชั้นที่ 2)
    # พร้อมกับ guard `running == false` — คืน False แล้วไม่แตะ system_data เลยถ้าไม่ผ่าน
    if apply_new_batch(system_data):
        last_state_before_alarm = None      # ตาราง 6.4.2 ข้อ 6 (global ของไฟล์นี้ ไม่ได้อยู่ใน system_data)
        trigger_reset_timer = True
        print(f"🔄 [{tag}] {RESET_LOG_NEW_BATCH}: เริ่ม batch ใหม่ — counter = 0 "
              f"(pieces/cycles/camera1/encoder) กลับสู่ [{system_data['current_state']}] · "
              f"ค่าตั้งเครื่องคงเดิม target={system_data['target_pieces']} pcs, "
              f"pitch={system_data['pitch']} mm · running ยังเป็น false (กด START เองอีกครั้ง)")
        return True

    # ==== ไม่เข้ากิ่งไหนเลย (ข้อ 6.4.4 แถว IGNORED-RUNNING) — ห้ามเปลี่ยนอะไรสักตัว ====
    print(f"⚠️ [{tag}] {RESET_LOG_IGNORED_RUNNING}: เครื่องกำลังเดินอยู่ (running=true) "
          f"จึงยังเริ่ม batch ใหม่ไม่ได้ — **กด STOP ก่อน แล้วค่อยกด RESET** "
          f"(ถ้าจะปลด ALARM ต้องอยู่ใน ALARM เท่านั้น ตอนนี้อยู่ที่ [{system_data['current_state']}]) "
          f"ตาม fsm_spec.md ข้อ 6.4.4")
    return False

def handle_gui_action(cmd_json):
    """คำสั่งที่จอ TouchGFX ยิงเข้ามาทาง TCP 8766 (hmi_link แกะ JSON ให้แล้ว)
    รองรับชุดเดียวกับฝั่งเว็บ เพื่อให้คุมเครื่องจากจอล้วนๆ ได้โดยไม่ต้องเปิดเบราว์เซอร์"""
    global trigger_reset_timer
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
        # ข้อ 6.4 — logic เดียวกับทาง WS ทุกตัวอักษร เรียกผ่าน apply_reset() ที่เดียว
        apply_reset(tag="TOUCHGFX RESET")
    elif act == "ESTOP":
        # ข้อ 6.2 — logic เดียวกับทาง WS ทุกตัวอักษร เรียกผ่าน trigger_estop() ที่เดียว
        trigger_estop("EMERGENCY STOP PRESSED (HMI)", tag="TOUCHGFX CMD")
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

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS machine_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            state_name TEXT NOT NULL,
            duration_sec REAL NOT NULL,
            control_mode TEXT NOT NULL,
            current_cycle INTEGER NOT NULL,
            status TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS production_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            end_timestamp TEXT NOT NULL,
            cycle_number INTEGER NOT NULL,
            total_duration_sec REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def log_state_transition_to_sql(state_name, duration_sec, mode, cycles, status="NORMAL"):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        cursor.execute("""
            INSERT INTO machine_logs (timestamp, state_name, duration_sec, control_mode, current_cycle, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (now_str, state_name, round(duration_sec, 3), mode, cycles, status))
        conn.commit()
        conn.close()
    except Exception: pass

def log_cycle_complete_to_sql(cycle_number, total_duration_sec):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO production_summary (end_timestamp, cycle_number, total_duration_sec)
            VALUES (?, ?, ?)
        """, (now_str, cycle_number, round(total_duration_sec, 2)))
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
                    print(f"{TAG_SIM} [{datetime.now().strftime('%H:%M:%S')}] FSM State: {curr} ({system_data['current_temp']}°C) | Status: {status_indicator} | Mode: {system_data['mode'].upper()} | Count: {system_data['pieces_count']}/{system_data['target_pieces']}")
                else:
                    print(f"{TAG_SIM} [{datetime.now().strftime('%H:%M:%S')}] FSM State: {curr} | Status: {status_indicator} | Mode: {system_data['mode'].upper()} | Count: {system_data['pieces_count']}/{system_data['target_pieces']}")
                
                last_printed_state = curr
                last_printed_temp = system_data["current_temp"]

            if system_data["running"] and curr != 'ALARM':
                simulated_delay = 0.0
                if curr in ["FEED_CARRIER", "SEAL_PROCESS"] and system_data["cycles"] in [3, 4]:
                    simulated_delay = 0.55  

                target_dur = (durations.get(curr, 0.5) + simulated_delay) / system_data["speed_mul"]
                
                if system_data["mode"] == "auto":
                    if curr == 'SENSOR_CHECK_CARRIER' and (now - last_transition_time >= target_dur):
                        if FAULT_SIM and random.random() < 0.015:
                            system_data["predictive_warning"] = "⚠️ ERROR: CARRIER TAPE JAMMED"
                            record_alarm("CARRIER TAPE JAMMED")
                            print(f"{TAG_SIM} 🚨 [FAULT (จำลอง)]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue
                            
                    # ทอยความน่าจะเป็นของงานเสียแค่ "ครั้งเดียว" ตอนกล้องตรวจเสร็จ
                    # (not step_allowed = ยังไม่ได้เปิดให้ operator ตัดสิน) ถ้าไม่กันไว้
                    # ลูปจะทอยใหม่ทุก 20 ms ระหว่างรอคนกด → เด้ง ALARM แทบทุกครั้ง
                    elif curr == 'VISION' and (now - last_transition_time >= target_dur) and not system_data["step_allowed"]:
                        if FAULT_SIM and random.random() < 0.02:
                            system_data["predictive_warning"] = "⚠️ ERROR: PART MISSING OR WRONG SIDE"
                            record_alarm("PART MISSING OR WRONG SIDE", count_ng=True)
                            print(f"{TAG_SIM} 🚨 [FAULT (จำลอง)]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue

                    elif curr == 'CHECK_TEMP':
                        rand_roll = random.random()
                        # ช่วงบนสุด (>= 0.98 ราว 2% ของรอบ) คือช่วงที่จงใจดันอุณหภูมิให้หลุดไป
                        # 201-215°C แล้วเด้ง ALARM — เป็น fault injection อีกรูปแบบหนึ่ง
                        # ปิดโหมดจำลองเมื่อไหร่ ให้บีบการทอยกลับมาอยู่ช่วงปกติแทน
                        if not FAULT_SIM and rand_roll >= 0.98:
                            rand_roll = 0.5
                        if rand_roll < 0.85:   system_data["current_temp"] = random.choice([189, 190, 191])
                        elif rand_roll < 0.98: system_data["current_temp"] = random.randint(170, 188)
                        else:                  system_data["current_temp"] = random.randint(201, 215)

                        temp = system_data["current_temp"]
                        if 189 <= temp <= 191:
                            pass 
                        elif temp > 200:
                            system_data["predictive_warning"] = "🚨 CRITICAL: HEATER OVERHEATED (OVER 200°C)"
                            record_alarm(f"HEATER OVERHEATED ({temp} C)")
                            print(f"{TAG_SIM} 🚨 [CRITICAL (อุณหภูมิจำลอง)]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue
                        else:
                            last_transition_time = now - target_dur + 0.02
                            time.sleep(0.1)
                            continue

                    elif curr == 'COUNT_CHECK' and (now - last_transition_time >= target_dur):
                        if FAULT_SIM and random.random() < 0.01:
                            system_data["predictive_warning"] = "⚠️ ERROR: COUNT MISMATCH (ENCODER VS CAMERA)"
                            record_alarm("COUNT MISMATCH (ENCODER VS CAMERA)", count_ng=True)
                            print(f"{TAG_SIM} 🚨 [FAULT (จำลอง)]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue

                    elif curr == 'VISION_QC' and (now - last_transition_time >= target_dur):
                        if FAULT_SIM and random.random() < 0.015:
                            system_data["predictive_warning"] = "⚠️ ERROR: BAD SEALING DETECTED"
                            record_alarm("BAD SEALING DETECTED", count_ng=True)
                            print(f"{TAG_SIM} 🚨 [FAULT (จำลอง)]: {system_data['predictive_warning']}")
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
                        if system_data["camera1_count"] == system_data["encoder_count"]:
                            state_index = STATES.index('COUNT_ACCUMULATE')
                        else:
                            system_data["predictive_warning"] = "⚠️ ERROR: COUNT MISMATCH"
                            record_alarm("COUNT MISMATCH", count_ng=True)
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                    elif curr == 'COUNT_ACCUMULATE':
                        system_data["pieces_count"] += 1
                        
                        if system_data["pieces_count"] >= system_data["target_pieces"]:
                            system_data["predictive_warning"] = "🎉 SUCCESS: PRODUCTION BATCH COMPLETED!"
                            print(f"\n{TAG_SIM} 🏁 [STATUS]: {system_data['predictive_warning']}\n")
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
            else:
                system_data["op0"] = 0x08 

            # ปั๊มข้อมูลไปจอ TouchGFX + รับปุ่มกดจากจอกลับมา (TCP 8766)
            hmi.poll()
            time.sleep(LOOP_DELAY)
        except Exception as e:
            time.sleep(0.5)

# ==================================================
# 🌐 WEBSOCKET BRIDGE SERVER
# ==================================================
async def ws_handler(websocket):
    global system_data, trigger_reset_timer, last_state_before_alarm, last_get_state_log
    connected_clients.add(websocket)
    print(f"🔌 [WS CONNECT] New client attached | active={len(connected_clients)}")
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
                print("🎮 [COMMAND]: Start Machine")
            elif action == "STOP":
                system_data["running"] = False
                trigger_reset_timer = True
                print("🎮 [COMMAND]: Stop Machine")
            elif action == "ESTOP":
                # ข้อ 6.2 — logic เดียวกับทาง TCP ทุกตัวอักษร เรียกผ่าน trigger_estop() ที่เดียว
                trigger_estop("EMERGENCY STOP PRESSED", tag="COMMAND")
            elif action == "RESET":
                # ข้อ 6.4 — logic เดียวกับทาง TCP ทุกตัวอักษร เรียกผ่าน apply_reset() ที่เดียว
                # (ห้ามมี path FULL RESET ของเดิมหลงเหลืออยู่ในคำสั่งนี้)
                apply_reset(tag="RESET")
            elif action == "MODE":
                system_data["mode"] = data.get("mode", "auto")
                print(f"🔄 [COMMAND]: Switched Mode to {system_data['mode'].upper()}")
            elif action == "SPEED":
                system_data["speed_mul"] = float(data.get("value", 1.0))
            elif action == "SET_PARAMS":
                system_data["target_pieces"] = max(1, int(data.get("target_pieces", system_data["target_pieces"])))
                system_data["pitch"] = max(1, int(data.get("pitch", system_data["pitch"])))
                print(f"⚙️ [PARAM UPDATE]: target={system_data['target_pieces']} pcs, pitch={system_data['pitch']} mm")
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
                except: pass
            elif action == "GET_STATE":
                try:
                    now = time.time()
                    if now - last_get_state_log > 1.0:
                        print(f"🔄 [WS SYNC] Sending LIVE_SYNC to client | active={len(connected_clients)}")
                        last_get_state_log = now
                    await websocket.send(json.dumps({"type": "LIVE_SYNC", "system": system_data}))
                except: pass
            elif action == "DECISION":
                recv_val = data.get("value", True)
                recv_meta = data.get("meta", None)
                print(f"[RECV DECISION] value={recv_val} meta={recv_meta} | step_allowed={system_data.get('step_allowed', False)}")
                accepted = apply_decision(bool(recv_val))
                try:
                    ack = {"type": "DECISION_ACK", "accepted": accepted}
                    if not accepted:
                        ack["reason"] = "not_allowed"
                    await websocket.send(json.dumps(ack))
                except Exception:
                    pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)
        print(f"🔴 [WS DISCONNECT] Client detached | active={len(connected_clients)}")

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
    
    print("\n" + "╔" + "═"*58 + "╗")
    print(f"║ 🔥 [CENTRAL GATEWAY] : CONTROL MATRIX SERVER IS ACTIVE   ║")
    print(f"║ ➔ Host Core : ws://localhost:8765                        ║")
    print(f"║ ➔ GUI Core  : tcp://127.0.0.1:8766                      ║")
    print(f"╚" + "═"*58 + "╝")
    # สรุปที่มาของตัวเลขให้ชัดตั้งแต่บรรทัดแรก — ไฟล์นี้ไม่มีสะพานไปฮาร์ดแวร์เลย
    print("  " + "-"*58)
    print(f"  {TAG_SIM} I/O MODE : SIMULATED ทั้งหมด (ไฟล์นี้ไม่มีสะพานไปฮาร์ดแวร์)")
    print(f"  {TAG_SIM}            ค่า ip0/ip1/op0/op1, อุณหภูมิ, ลำดับสเต็ป = จำลองในโค้ดทั้งหมด")
    print(f"  {TAG_SIM}            ต้องการต่อบอร์ดจริง: ใช้ gateway_fsm_upgrad.py + RUST_BRIDGE=1")
    # บอกให้ชัดว่า ALARM ที่จะเห็นต่อจากนี้ "อาจเป็นของปลอม" หรือ "ไม่มีของปลอมเลย"
    if FAULT_SIM:
        print(f"  {TAG_SIM} FAULT SIM: ON  ({FAULT_SIM_SRC})")
        print(f"  {TAG_SIM}            โค้ดจะสุ่มโยน fault ใส่ตัวเอง → ALARM ที่เห็นอาจเป็นของปลอม")
        print(f"  {TAG_SIM}            อยากรันยาวโดยไม่มี ALARM ปลอมมากวน: FAULT_SIM=0")
    else:
        print(f"  {TAG_SIM} FAULT SIM: OFF ({FAULT_SIM_SRC})")
        print(f"  {TAG_SIM}            ไม่มีการสุ่มโยน fault → ALARM ที่เห็นมาจากคนกด/เหตุการณ์จริงเท่านั้น")
        print(f"  {TAG_SIM}            อยากได้ fault จำลองไว้เดโม: FAULT_SIM=1")
    print("  " + "-"*58 + "\n")
    
    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        await asyncio.Event().wait() 

if __name__ == "__main__":
    asyncio.run(main_async())