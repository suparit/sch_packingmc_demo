import sys
import time
import os
import json
import asyncio
import threading
import sqlite3
import math
import random
import socket
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
IO_MONITOR_ENABLED = os.environ.get("IO_MONITOR", "0") == "1"
IO_BRIDGE_HOST = os.environ.get("IO_BRIDGE_HOST", "127.0.0.1")
IO_BRIDGE_PORT = int(os.environ.get("IO_BRIDGE_PORT", "8767"))
# 🔩 มอเตอร์ feed จริง (25 ก.ย. 2569) — FEED_CARRIER ส่ง feed_cmd ให้ Rust ของเพื่อน (dt-taping-dev/rust_bridge)
#    แล้วรอผล done · error/หมดเวลา/สายหลุด → ALARM · สัญญา dt-taping-dev/docs/specs/protocol.md ข้อ 9
FEED_MOTOR_ENABLED = os.environ.get("FEED_MOTOR", "0") == "1"
FEED_PULSES = int(os.environ.get("FEED_PULSES", "156"))      # วัดจริง 25 ก.ย.: เฉลี่ย 156.1 พัลส์/หลุม
FEED_HALF_MS = float(os.environ.get("FEED_HALF_MS", "5"))     # ครึ่งคาบพัลส์ 5 ms ≈ 91 พัลส์/วิ
FEED_TIMEOUT_S = float(os.environ.get("FEED_TIMEOUT_S", "10"))
# ALARM สุ่มจำลอง (เทปติด/อุณหภูมิ/นับไม่ตรง/ซีลเสีย) — ปิดตอนรันกับเครื่องจริง ให้ ALARM มาจากของจริงเท่านั้น
SIM_FAULTS_ENABLED = os.environ.get("SIM_FAULTS", "1") == "1"
# หลุมว่างหัว-ท้ายของ batch (ข้อกำหนดการโหลดชิ้นงานจริง — เจ้าของงาน 25 ก.ย. 2569):
# งาน N ชิ้น = หลุมว่างหน้า 3 + ชิ้นงาน N (target_pieces) + หลุมว่างหลัง 4 · หลุมว่างไม่วาง/ไม่ตรวจ/ไม่นับ แต่ feed + ซีลตามปกติ
# หลุมปัจจุบัน = cycles + 1 (cycles นับรอบที่จบ · RESET ตอน ALARM แค่เคลียร์ alarm ไม่รีเซ็ต · RESET ตอนไม่ ALARM = batch ใหม่)
LEADER_POCKETS = int(os.environ.get("LEADER_POCKETS", os.environ.get("EMPTY_POCKETS", "3")))
TRAILER_POCKETS = int(os.environ.get("TRAILER_POCKETS", "4"))
# ⏱️ เร่งรอบ (25 ก.ย. 2569): รอบละ 8.7 s มี ~6 s เป็นสเต็ปจำลองที่รอตามเวลาเฉย ๆ
# SIM_STEP_S = เวลาของทุกสเต็ปที่ไม่ใช่ SEAL_PROCESS (launcher ตั้ง 0.15 ตอนต่อเครื่องจริง · ไม่ตั้ง = ใช้ durations เดิม)
# FEED_CARRIER รอ Rust ตอบ done · VISION รอกล้อง อยู่แล้ว ค่านี้เป็นแค่เวลาขั้นต่ำ
_sim_step = os.environ.get("SIM_STEP_S", "").strip()
SIM_STEP_S = float(_sim_step) if _sim_step else None
# ซีลคือเวลากดค้างจริงของกระบอก — ทดสอบกับลมแล้ว 1 s พอให้ลงสุด (ยังไม่มี heater จึงยังไม่รู้เวลาซีลติดจริง)
# เครื่องจริงห้ามสั้นกว่านี้ แม้เลื่อน SPEED บนจอ/เว็บ (speed_mul หารทุกสเต็ป)
SEAL_HOLD_S = float(os.environ.get("SEAL_HOLD_S", "1.0"))
# 🔗 Sync บอร์ด (27 ก.ย. 2569): เปิดระบบด้วยปุ่มเดียว (START.bat) แล้วเลือกต่อ/ไม่ต่อบอร์ดจากปุ่ม Sync บนเว็บ
#    ไม่ Sync (ค่าเริ่มต้น) = จำลองบนเว็บ เอาต์พุตบอร์ดเป็น 0 · Sync = สั่งเครื่องจริง (มอเตอร์/โซลินอยด์/C/กล้อง)
#    ค่า IO_MONITOR / FEED_MOTOR / SIM_FAULTS / SIM_STEP_S / VISION_INPUT จาก launcher = "สิ่งที่มีให้ใช้"
#    มีผลจริงเฉพาะตอน Sync ผ่าน hw_active() — เดิมเป็นค่าตายตัวตั้งแต่เปิดโปรแกรม
VISION_INPUT_HW = os.environ.get("VISION_INPUT", "simulated").lower()   # ตอน Sync: camera = รอผลกล้องจริง
HW_SYNC_AT_START = os.environ.get("HW_SYNC", "0") == "1" and IO_MONITOR_ENABLED

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
    # simulated = Web-only demo uses the built-in random VISION result.
    # camera = Full hardware run waits for OpenMV's DECISION at VISION.
    # 27 ก.ย. 2569: เปลี่ยนตามปุ่ม Sync — ไม่ Sync = simulated เสมอ (ดู set_hw_sync)
    "vision_input": VISION_INPUT_HW if HW_SYNC_AT_START else "simulated",
    "hw_sync": HW_SYNC_AT_START,      # ปุ่ม Sync บนเว็บ — True = สั่งบอร์ดจริง
    "hw_available": False,            # launcher เปิด Rust ไว้ + บอร์ดตอบ (Sync ได้ไหม) — อัปเดตใน io_monitor_loop
    "step_allowed": False,     
    "cycles": 0,
    "speed_mul": 1.0,
    "ip0": 0, "ip1": 0,
    "op0": 0, "op1": 0,
    "cyl_c": "OFF",            # ปุ่ม INIT บนจอ -> Cylinder C ค้าง (OP1 bit 2)
    "manual_seal": "UP",       # ปุ่ม UP/DOWN หน้า Maintenance -> โซลินอยด์ A+B (OP1 bit 0/1)
    "io_connected": False,
    "io_mode": "disabled",
    "io_error": "",
    "io_op0": 0,
    "io_op1": 0,
    "io_feed": None,           # ผล feed ล่าสุดจาก Rust ของเพื่อน {id,state,sent,total,err} · None = ไม่รองรับ
    # คีย์แบบแบนสำหรับเว็บ web_next ของเพื่อน (อ่านชื่อพวกนี้ ไม่ได้อ่าน io_feed) — อัปเดตใน io_monitor_loop
    "feed_src": "SIM", "feed_state": "idle", "feed_sent": 0, "feed_total": 0,
    "feed_index": 0, "feed_pulses": 0,   # จำนวนหลุมที่ feed ครบ / พัลส์สะสม ใน batch นี้ (นับทั้ง FSM และปุ่ม STEP)
    "feed_half_ms": FEED_HALF_MS,
    "step_wait": False,        # web_next อ่านคีย์นี้ · gateway เราไม่มีโหมด step จึงเป็น False เสมอ
    "camera1_count": 0,
    "encoder_count": 0,
    "pieces_count": 0,
    "target_pieces": 200,
    # เลขหลุมใน batch (27 ก.ย. 2569) — เว็บ web_next แสดง "หลุม x / ทั้งหมด" + ช่วง หน้า/ชิ้นงาน/ท้าย
    "pocket": 1, "pocket_empty": True, "leader_pockets": LEADER_POCKETS, "trailer_pockets": TRAILER_POCKETS,
    "batch_pockets": LEADER_POCKETS + 200 + TRAILER_POCKETS,
    "pitch": 24,
    "current_temp": 190,
    "predictive_warning": ""
}

step_history_cache = {"FEED_CARRIER": [], "SEAL_PROCESS": []}
connected_clients = set()
trigger_reset_timer = False
last_get_state_log = 0.0
last_state_before_alarm = "LOAD_CARRIER"
# เวลาที่ VISION เริ่มรอผลกล้อง (step_allowed = True) · ใช้นับช่วงผ่อนผัน "ไม่พบชิ้นงาน"
vision_ready_at = 0.0
NO_PART_WAIT_S = float(os.environ.get("NO_PART_WAIT_S", "10"))
# งาน feed ที่ส่งให้ Rust อยู่ {id, abort, issued, lost} · None = ไม่มี · id ใหม่ออกได้เมื่องานเดิมจบแล้วเท่านั้น
feed_job = None
feed_seq = 0

# 🔗 สะพานไปจอ TouchGFX — TCP server 127.0.0.1:8766
#    โค้ดจริงอยู่ใน hmi_link.py ใช้ร่วมกับ gateway_fsm_upgrad.py เพื่อไม่ให้สองไฟล์แยกกันเดิน
hmi = HmiLink(system_data, DB_FILE, BASE_DIR)

def record_alarm(msg, count_ng=False):
    hmi.record_alarm(msg, count_ng)
    log_alarm_to_sql(msg)


ALARM_HISTORY_LIMIT = 100


def log_alarm_to_sql(msg):
    """ประวัติ ALARM ถาวรใน SQLite (27 ก.ย. 2569) — เดิมข้อความสาเหตุอยู่แค่ใน hmi.alarm_logs (หน่วยความจำ)
    หายเมื่อปิด gateway และดูได้แค่ที่จอ HMI · machine_logs มีแค่แถว ALARM ไม่มีสาเหตุ
    state = สเต็ปที่เกิดเหตุ (ESTOP ตั้ง current_state เป็น ALARM ก่อนเรียก จึงใช้ last_state_before_alarm แทน)"""
    try:
        state = system_data["current_state"]
        if state == "ALARM":
            state = last_state_before_alarm
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "INSERT INTO alarm_logs (timestamp, message, state_name, current_cycle, pocket, hw_sync, control_mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(msg), state, int(system_data["cycles"]),
             int(system_data["cycles"]) + 1, 1 if system_data.get("hw_sync") else 0, system_data["mode"]))
        conn.commit()
        conn.close()
    except Exception as error:
        print(f"⚠️ [ALARM LOG] บันทึกลง SQLite ไม่ได้: {error}")


def read_alarm_history(limit=ALARM_HISTORY_LIMIT):
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT timestamp, message, state_name, current_cycle, pocket, hw_sync, control_mode "
        "FROM alarm_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [{"time": r[0], "message": r[1], "state": r[2], "cycle": r[3], "pocket": r[4],
             "real": bool(r[5]), "mode": r[6]} for r in rows]


def hw_active():
    """กำลังสั่งบอร์ดจริงไหม = launcher เปิดสาย Rust ไว้ + ผู้ใช้กด Sync แล้ว"""
    return IO_MONITOR_ENABLED and system_data["hw_sync"]


def feed_motor_active():
    return FEED_MOTOR_ENABLED and hw_active()


def sim_faults_active():
    """ALARM สุ่มจำลอง — ปิดเสมอตอน Sync (ALARM ต้องมาจากของจริง)"""
    return SIM_FAULTS_ENABLED and not hw_active()


def set_hw_sync(want, source):
    """ปุ่ม Sync บอร์ด — คืน (รับไหม, เหตุผล) · กติกา (ตกลงกับเจ้าของงาน 27 ก.ย. 2569):
    สลับได้เฉพาะตอนเครื่องหยุด + ไม่มี feed ค้าง · เปิดได้เมื่อบอร์ดตอบจริง ·
    สลับทุกครั้ง ปล่อย Cylinder C + ยกโซลินอยด์ (INIT ที่กดตอนจำลองต้องไม่กลายเป็นการกดจริงทันทีที่ Sync) ·
    ตัวนับหลุม/ชิ้นไม่รีเซ็ต"""
    global trigger_reset_timer
    want = bool(want)
    if want == system_data["hw_sync"]:
        return True, ""
    if system_data["running"]:
        return False, "หยุดเครื่อง (STOP) ก่อนสลับ Sync"
    if feed_job is not None:
        return False, "รอให้มอเตอร์ feed หยุดก่อน"
    if want:
        if not IO_MONITOR_ENABLED:
            return False, "ระบบเปิดแบบไม่ต่อบอร์ด (START_WEB) — ใช้ START.bat"
        if not system_data.get("io_connected"):
            return False, "บอร์ด I/O ไม่ตอบ — เช็กสาย LAN / ไฟบอร์ด"
    system_data["hw_sync"] = want
    system_data["cyl_c"] = "OFF"
    system_data["manual_seal"] = "UP"
    system_data["vision_input"] = VISION_INPUT_HW if want else "simulated"
    system_data["step_allowed"] = False
    system_data["predictive_warning"] = ""
    trigger_reset_timer = True
    print(f"🔗 [{source} SYNC]: {'ต่อบอร์ดแล้ว — สั่งเครื่องจริง' if want else 'ตัดบอร์ด — จำลองบนเว็บ เอาต์พุต 0'} "
          f"(vision={system_data['vision_input']}, feed motor={'ON' if feed_motor_active() else 'OFF'})")
    return True, ""


def publish_feed_keys(feed, board):
    """แปลง io_feed เป็นคีย์แบบแบนที่ web_next อ่าน (protocol ของเพื่อน fsm_spec 8.4)
    feed_src: REAL = มอเตอร์หมุนจริง (เว็บขึ้นแถบแดงเตือน) · SIM = ไม่ได้ต่อมอเตอร์"""
    real = bool(board) and feed_motor_active() and isinstance(feed, dict)
    system_data["feed_src"] = "REAL" if real else "SIM"
    if isinstance(feed, dict):
        system_data["feed_state"] = str(feed.get("state", "idle"))
        system_data["feed_sent"] = int(feed.get("sent", 0) or 0)
        system_data["feed_total"] = int(feed.get("total", 0) or 0)
    else:
        system_data.update(feed_state="idle", feed_sent=0, feed_total=0)


def io_monitor_loop():
    """คุยกับ Rust bridge ทาง 8767 — รองรับ 2 ตัว (ดูจากคีย์ในคำตอบ):
    - ตัวเดิม `01_DigitalTwin/rust_bridge` ตอบ {ip0, ip1, op0, op1, io_connected, io_mode, io_error}
      เขียนเอาต์พุตเมื่อ IO_OUTPUT_MODE=display
    - ตัวของเพื่อน `dt-taping-dev/rust_bridge` ตอบ {ip0, board, feed} เขียนเอาต์พุตเสมอ + ส่งพัลส์ feed
      (สัญญา dt-taping-dev/docs/specs/protocol.md ข้อ 9) · บังคับคีย์ ip0/cycles ถ้าขาดจะทิ้งทั้งบรรทัด"""
    bridge = None
    rx_buffer = b""
    while True:
        try:
            if bridge is None:
                bridge = socket.create_connection((IO_BRIDGE_HOST, IO_BRIDGE_PORT), timeout=1.0)
                bridge.settimeout(1.0)
                system_data["io_mode"] = "monitor"
                print(f"[I/O] Connected to Rust bridge at {IO_BRIDGE_HOST}:{IO_BRIDGE_PORT}")

            # ไม่ Sync = ไม่สั่งบอร์ด: เอาต์พุต 0 ทั้งหมด (ไฟ/โซลินอยด์/C) — เว็บยังเห็นไฟจำลองจาก system_data op0/op1
            sent_op0 = system_data["op0"] & 0xFF if hw_active() else 0
            sent_op1 = system_data["op1"] & 0xEF if hw_active() else 0   # bit 4 (PUL) เป็นของ Rust — protocol.md 9.6
            msg = {
                "op0": sent_op0,
                "op1": sent_op1,
                "running": system_data["running"],
                "current_state": system_data["current_state"],
                "ip0": system_data["ip0"],
                "cycles": system_data["cycles"],
            }
            # ส่งคำสั่ง feed ของ id ปัจจุบันซ้ำทุกบรรทัดจนได้สถานะจบ (Rust ไม่ feed ซ้ำถ้า id เดิม — protocol.md 9.3)
            job = feed_job
            if job is not None and not job["lost"]:
                msg["feed_cmd"] = {"id": job["id"], "pulses": FEED_PULSES,
                                   "half_ms": FEED_HALF_MS, "abort": job["abort"]}
            payload = json.dumps(msg).encode("utf-8") + b"\n"
            bridge.sendall(payload)
            while b"\n" not in rx_buffer:
                chunk = bridge.recv(1024)
                if not chunk:
                    raise ConnectionError("Rust bridge closed the connection")
                rx_buffer += chunk
            line, rx_buffer = rx_buffer.split(b"\n", 1)
            snapshot = json.loads(line.decode("utf-8"))
            system_data["ip0"] = int(snapshot.get("ip0", 0)) & 0xFF
            system_data["ip1"] = int(snapshot.get("ip1", 0)) & 0xFF
            if "board" in snapshot:
                # ตัวของเพื่อน: ไม่อ่านเอาต์พุตกลับ (บอร์ดอ่านกลับไม่ได้อยู่แล้ว) → โชว์ค่าที่ส่งไป
                board = bool(snapshot["board"])
                system_data["io_connected"] = board
                system_data["hw_available"] = board
                system_data["io_mode"] = "display"
                system_data["io_error"] = "" if board else "board not connected (Rust SIM mode)"
                system_data["io_op0"] = sent_op0
                system_data["io_op1"] = sent_op1
                system_data["io_feed"] = snapshot.get("feed")   # None = Rust ไม่รองรับ feed
                publish_feed_keys(system_data["io_feed"], board)
            else:
                system_data["io_connected"] = bool(snapshot.get("io_connected", False))
                system_data["hw_available"] = system_data["io_connected"]
                system_data["io_mode"] = str(snapshot.get("io_mode", "monitor"))
                system_data["io_error"] = str(snapshot.get("io_error", ""))
                system_data["io_op0"] = int(snapshot.get("op0", 0)) & 0xFF
                system_data["io_op1"] = int(snapshot.get("op1", 0)) & 0xFF
                system_data["io_feed"] = None
                publish_feed_keys(None, False)
            time.sleep(0.05)
        except Exception as error:
            system_data["io_connected"] = False
            system_data["hw_available"] = False
            system_data["io_mode"] = "monitor"
            system_data["io_error"] = str(error)
            system_data["io_feed"] = None
            publish_feed_keys(None, False)
            # 🔴 สายหลุด = Rust สายใหม่จำ id ไม่ได้ ห้ามส่ง id เดิมซ้ำ (จะหมุนซ้ำ) → ถือว่างาน feed นี้เสีย
            if feed_job is not None:
                feed_job["lost"] = True
            if bridge:
                try:
                    bridge.close()
                except Exception:
                    pass
                bridge = None
            time.sleep(2.0)

# ==================================================
# 🎮 คำสั่งจาก operator (ใช้ร่วมกันทั้งจอ TouchGFX และเว็บ 3D Twin)
# ==================================================
# 🎥 25 ก.ย. 2569: ตอนรันโหมดกล้อง (VISION_INPUT=camera) สเต็ป VISION รับ PASS/NG จากกล้องเท่านั้น
# เคยเจอ: เฟิร์มแวร์จอเด้ง popup PASS/NG ทุกครั้งที่ FSM รอที่ VISION -> คนแตะ NG ก่อนกล้องตัดสิน (1.6 วิ)
# FSM เข้า ALARM "OPERATOR REJECTION" ทั้งที่ชิ้นงานผ่าน · กล้อง OCR ส่ง meta.source = "hikrobot-ocr"
# (ถ้าเปลี่ยนตัวกล้อง ให้ใส่ชื่อ source ของตัวใหม่ในชุดนี้) · checkpoint อื่นในโหมด semi ยังกดจากจอ/เว็บได้
CAMERA_DECISION_SOURCES = {"hikrobot-ocr"}


def vision_needs_camera(meta):
    """True = คำตัดสินนี้ต้องทิ้ง เพราะ FSM รอผลกล้องที่ VISION แต่ไม่ได้มาจากกล้อง"""
    if system_data["current_state"] != "VISION" or system_data["vision_input"] != "camera":
        return False
    src = meta.get("source") if isinstance(meta, dict) else None
    return src not in CAMERA_DECISION_SOURCES


def batch_pockets():
    """จำนวนหลุมทั้ง batch = หน้า + ชิ้นงาน + หลัง"""
    return LEADER_POCKETS + system_data["target_pieces"] + TRAILER_POCKETS


def pocket_is_empty():
    """หลุมที่กำลังทำอยู่เป็นหลุมว่างหัว/ท้าย batch ไหม (ข้าม LOAD_PART/VISION · ไม่นับชิ้น)"""
    pocket = system_data["cycles"] + 1
    return pocket <= LEADER_POCKETS or pocket > LEADER_POCKETS + system_data["target_pieces"]


def batch_done():
    return system_data["cycles"] >= batch_pockets()


VALID_MODES = ("auto", "semi")


def set_mode(mode, source):
    """เปลี่ยนโหมดทำงาน — รับเฉพาะ auto/semi · คืน (รับไหม, เหตุผล)
    27 ก.ย. 2569: เว็บ web_next ของเพื่อนมีปุ่ม "Step" (หยุดทุกสเต็ปรอ NEXT) ซึ่ง gateway เราไม่มี
    เดิมรับค่าอะไรก็ได้ → mode = "step" แล้ว FSM เดินต่อเนื่องเหมือน auto ทั้งที่คนกดคาดว่าเครื่องจะหยุดรอ"""
    mode = str(mode).lower()
    if mode not in VALID_MODES:
        print(f"⛔ [{source} MODE]: ปฏิเสธโหมด {mode!r} — gateway นี้รับแค่ {'/'.join(VALID_MODES)}")
        return False, "gateway นี้ไม่มีโหมด Step (รับแค่ Auto / Semi)" if mode == "step" else "invalid_mode"
    system_data["mode"] = mode
    print(f"🔄 [{source} MODE]: Switched Mode to {mode.upper()}")
    return True, ""


def set_target_pieces(value, source):
    """ตั้งเป้าชิ้นงานต่อ batch — เฉพาะตอนเครื่องหยุด (เดินอยู่ = ช่วงหลุมว่างท้ายจะเลื่อนกลาง batch)"""
    try:
        target = int(value)
    except (TypeError, ValueError):
        return False
    if system_data["running"]:
        system_data["predictive_warning"] = "TARGET LOCKED: STOP MACHINE FIRST"
        print(f"⛔ [{source} PARAM]: ไม่รับเป้า {target} — เครื่องกำลังเดิน")
        return False
    system_data["target_pieces"] = max(1, min(10000, target))
    system_data["batch_pockets"] = batch_pockets()
    if system_data["predictive_warning"] == "TARGET LOCKED: STOP MACHINE FIRST":
        system_data["predictive_warning"] = ""
    return True


def reset_command(source):
    """RESET จากจอ/เว็บ — ตอน ALARM: เคลียร์ alarm อย่างเดียว กลับสเต็ปที่ค้าง เก็บตัวนับไว้ (เจ้าของงาน 25 ก.ย. 2569)
    ตอนไม่ ALARM: เริ่ม batch ใหม่ (ล้างตัวนับ · หลุมว่างหน้าเริ่มใหม่)"""
    global trigger_reset_timer
    trigger_reset_timer = True
    system_data["running"] = False
    system_data["predictive_warning"] = ""
    system_data["step_allowed"] = False
    if system_data["current_state"] == "ALARM":
        system_data["current_state"] = last_state_before_alarm
        system_data["op0"] = 0x00
        print(f"🔄 [{source} RESET]: Alarm cleared → กลับ [{last_state_before_alarm}] · หลุม {system_data['cycles'] + 1} · "
              f"{system_data['pieces_count']}/{system_data['target_pieces']} ชิ้น (ตัวนับเดิม)")
    else:
        system_data["current_state"] = "LOAD_CARRIER"
        system_data["cycles"] = 0
        system_data["camera1_count"] = 0
        system_data["encoder_count"] = 0
        system_data["pieces_count"] = 0
        system_data.update(feed_index=0, feed_pulses=0)
        hmi.reset_ng()
        print(f"🧹 [{source} RESET]: batch ใหม่ — ตัวนับเป็น 0")


def start_blocked():
    """เครื่องจริง: START ได้เมื่อ Cylinder C กด carrier แล้ว (ปุ่ม INIT) — ไม่งั้นมอเตอร์หมุนแต่เทปไม่เดิน"""
    if batch_done():
        system_data["predictive_warning"] = "CANNOT START: BATCH DONE - PRESS RESET FIRST"
        print("⛔ [START BLOCKED]: batch ครบแล้ว กด RESET เริ่ม batch ใหม่")
        return True
    if hw_active() and system_data.get("cyl_c") != "ON":
        system_data["predictive_warning"] = "START BLOCKED: PRESS INIT FIRST"
        print("⛔ [START BLOCKED]: Cylinder C ยังไม่กด (กด INIT ก่อน)")
        return True
    if feed_job is not None and feed_job.get("manual"):
        system_data["predictive_warning"] = "START BLOCKED: STEP FEED RUNNING"
        print("⛔ [START BLOCKED]: ปุ่ม STEP กำลัง feed อยู่")
        return True
    return False


# กล้องส่ง reason ภาษาไทย "ไม่ผ่าน: 1 มีชิ้นงาน, 2 ..." แต่จอ HMI แสดงได้แค่ ASCII (ไทยถูกตัดทิ้ง)
# → แปลงเงื่อนไขแรกที่ไม่ผ่านเป็นรหัสอังกฤษสั้น ๆ (เลขข้อตาม app_vision_ocr.py)
CAMERA_NG_CODES = {"1": "NO PART", "2": "WRONG POSITION", "3": "TEXT NOT FOUND", "4": "TEXT UNREADABLE"}


def decision_ng_message(meta):
    """ข้อความ ALARM ตอน NG — แยกกล้องตัดสิน กับคนกด NG (โหมด semi)"""
    if not isinstance(meta, dict) or meta.get("source") not in CAMERA_DECISION_SOURCES:
        return "OPERATOR REJECTION (SEMI-AUTO NG)"
    reason = str(meta.get("reason", ""))
    first = reason.split("ไม่ผ่าน:", 1)[1].strip()[:1] if "ไม่ผ่าน:" in reason else ""
    return f"VISION NG: {CAMERA_NG_CODES.get(first, 'CAMERA FAIL')}"


def apply_decision(accept, meta=None):
    """ยืนยัน/ปฏิเสธผลตรวจของ operator ที่สเต็ปเช็คพอยต์ (VISION ฯลฯ)
    คืน True ถ้า FSM กำลังรอคำตัดสินอยู่จริง — ผู้เรียกเอาไปตอบ ACK ต่อได้"""
    global trigger_reset_timer, last_state_before_alarm

    if not system_data["step_allowed"]:
        print("⚠️ [DECISION IGNORED] FSM not accepting decisions now.")
        return False

    # กล้องบอก "ไม่พบชิ้นงาน" ช่วงแรกของ VISION = คนยังวางไม่ทัน (รอบเร็วขึ้น เหลือเวลาวาง ~2.4 s) → รอต่อ ไม่ ALARM
    # กล้องจะตัดสินใหม่จากภาพชุดใหม่เอง · เกิน NO_PART_WAIT_S แล้วยังไม่มีชิ้นงาน → ALARM ตามปกติ · เหตุ NG อื่น ALARM ทันที
    if (not accept and system_data["current_state"] == "VISION"
            and decision_ng_message(meta) == "VISION NG: NO PART"):
        waited = time.time() - vision_ready_at
        if waited < NO_PART_WAIT_S:
            system_data["predictive_warning"] = f"WAITING FOR PART ({NO_PART_WAIT_S - waited:.0f}s)"
            print(f"⏳ [VISION] ยังไม่พบชิ้นงาน — รอต่อ ({waited:.1f}/{NO_PART_WAIT_S:.0f} s)")
            return False

    system_data["step_allowed"] = False
    trigger_reset_timer = True
    if system_data["predictive_warning"].startswith("WAITING FOR PART"):
        system_data["predictive_warning"] = ""

    if accept:
        state_idx = STATES.index(system_data["current_state"])
        system_data["current_state"] = STATES[(state_idx + 1) % len(STATES)]
        print("🕹️ [DECISION]: Operator Clicked OK")
    else:
        ng_msg = decision_ng_message(meta)
        system_data["predictive_warning"] = f"⚠️ ERROR: {ng_msg}"
        record_alarm(ng_msg, count_ng=True)
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
        if start_blocked():
            return
        system_data["running"] = True
        system_data["predictive_warning"] = ""
        trigger_reset_timer = True
        print("🎮 [TOUCHGFX CMD]: START MACHINE")
    elif act == "STOP":
        system_data["running"] = False
        trigger_reset_timer = True
        print("🎮 [TOUCHGFX CMD]: STOP MACHINE")
    elif act == "SINGLE_CYCLE":   # ปุ่ม STEP บนจอ → feed 1 หลุม
        manual_feed_command()
    elif act == "RESET":
        # เดิมจอล้าง batch ทุกครั้ง แม้กดแค่เคลียร์ ALARM (หลุมว่างหน้าเริ่มใหม่ผิด) — ตอนนี้ตรงกับเว็บ
        reset_command("TOUCHGFX")
    elif act == "ESTOP":
        system_data["running"] = False
        if system_data["current_state"] != "ALARM":
            last_state_before_alarm = system_data["current_state"]
        system_data["current_state"] = "ALARM"
        system_data["op0"] = 0x08
        system_data["op1"] = 0x00
        system_data["predictive_warning"] = "🚨 EMERGENCY STOP ENGAGED"
        system_data["cyl_c"] = "OFF"   # E-STOP ปลด Cylinder C (ALARM อื่นไม่ปลด)
        record_alarm("EMERGENCY STOP PRESSED (HMI)")
        trigger_reset_timer = True
        print("🚨 [TOUCHGFX CMD]: EMERGENCY STOP")
    elif act == "MODE":
        set_mode(cmd_json.get("mode", "auto"), "TOUCHGFX")
    elif act == "SPEED":
        system_data["speed_mul"] = float(cmd_json.get("value", 1.0))
    elif act == "CYL_C":
        # 🔩 ปุ่ม INIT (เฟิร์มแวร์จอของเพื่อน) — จอส่ง ON/OFF ตรงข้ามกับคีย์ cyl_c ที่ได้รับล่าสุด
        # สเปกเดียวกับ repo เพื่อน protocol.md ข้อ 4.3 · 28 ก.ย. 2569: รับ ON/OFF ตลอด รวมตอน ALARM (INIT คุม C คนเดียว)
        want = str(cmd_json.get("value", "")).upper()
        if want not in ("ON", "OFF"):
            print(f"⚠️ [CYL_C] ไม่รู้จักค่า {want!r} — ต้องเป็น ON หรือ OFF")
        else:
            system_data["cyl_c"] = want
            print(f"🔩 [TOUCHGFX CMD]: Cylinder C → {want} (OP1 bit 2)")
    elif act == "MANUAL_SEAL":
        # 🔧 ปุ่ม ▲UP/▼DOWN แถว Welding Mechanism หน้า Maintenance (เฟิร์มแวร์จอของเพื่อน protocol.md ข้อ 4.1)
        # DOWN = โซลินอยด์ A+B ค้างลง · UP = ปล่อยขึ้น · DOWN รับเฉพาะตอนเครื่องหยุดและไม่อยู่ใน ALARM
        # (กันชนกับ FSM ที่สั่ง OP1 ตอน SEAL_PROCESS) · UP รับเสมอ
        want = str(cmd_json.get("value", "")).upper()
        if want not in ("DOWN", "UP"):
            print(f"⚠️ [MANUAL_SEAL] ไม่รู้จักค่า {want!r} — ต้องเป็น DOWN หรือ UP")
        elif want == "DOWN" and system_data["running"]:
            print("⚠️ [MANUAL_SEAL] ปฏิเสธ DOWN: เครื่องกำลังเดิน — กด STOP ก่อน")
        elif want == "DOWN" and system_data["current_state"] == "ALARM":
            print("⚠️ [MANUAL_SEAL] ปฏิเสธ DOWN: อยู่ใน ALARM — กด RESET ก่อน")
        else:
            system_data["manual_seal"] = want
            print(f"🔧 [TOUCHGFX CMD]: Seal cylinders A+B → {want} (OP1 bit 0/1)")
    elif act == "DECISION":
        # 🎥 ปุ่ม PASS/NG ของสเต็ป VISION บนจอ — จำเป็นต้องมี ไม่งั้นเครื่องค้างที่ VISION
        # เมื่อสั่งงานจากจออย่างเดียวโดยไม่เปิดหน้าเว็บ
        if vision_needs_camera(cmd_json.get("meta")):
            print("⚠️ [DECISION IGNORED] จอส่ง PASS/NG ที่ VISION — โหมดกล้องรับผลจากกล้องเท่านั้น")
        else:
            apply_decision(bool(cmd_json.get("value", True)), cmd_json.get("meta"))
    elif act == "SET_PARAMS":
        # ตั้งค่าจากแป้นพิมพ์บนจอ HMI — ค่าใหม่จะ broadcast กลับไปทั้ง HMI และเว็บ 3D Twin ทันที
        if "target_pieces" in cmd_json:
            set_target_pieces(cmd_json["target_pieces"], "TOUCHGFX")
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
        CREATE TABLE IF NOT EXISTS alarm_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            message TEXT NOT NULL,
            state_name TEXT NOT NULL,
            current_cycle INTEGER NOT NULL,
            pocket INTEGER NOT NULL,
            hw_sync INTEGER NOT NULL,
            control_mode TEXT NOT NULL
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
FEED_FINAL = ("done", "aborted", "error")


def count_feed_done(rep):
    """นับหลุม/พัลส์สะสมให้เว็บ web_next (การ์ด Feed motor: PITCH # / Σ PULSES)"""
    system_data["feed_index"] += 1
    system_data["feed_pulses"] += int(rep.get("sent", 0) or 0)


def manual_feed_command():
    """ปุ่ม STEP บนจอ (จอส่ง SINGLE_CYCLE) → feed 1 หลุมตอนเครื่องหยุด ใช้เลื่อน carrier เข้าตำแหน่ง index
    (ความหมายของเราเอง 25 ก.ย. 2569 — repo เพื่อนใช้ SINGLE_CYCLE = เดินครบ 1 รอบ)"""
    global feed_job, feed_seq
    reason = None
    if not FEED_MOTOR_ENABLED:
        reason = "STEP REJECTED: NO FEED MOTOR"
    elif not hw_active():
        reason = "STEP REJECTED: SYNC BOARD FIRST"
    elif system_data["running"]:
        reason = "STEP REJECTED: MACHINE RUNNING"
    elif system_data["current_state"] == "ALARM":
        reason = "STEP REJECTED: PRESS RESET FIRST"
    elif system_data.get("cyl_c") != "ON":
        reason = "STEP REJECTED: PRESS INIT FIRST"
    elif feed_job is not None:
        reason = "STEP REJECTED: FEED BUSY"
    elif system_data.get("io_feed") is None:
        reason = "STEP REJECTED: FEED BRIDGE NOT READY"
    if reason:
        system_data["predictive_warning"] = reason
        print(f"⛔ [STEP] {reason}")
        return
    feed_seq += 1
    feed_job = {"id": feed_seq, "abort": False, "issued": time.time(), "lost": False, "manual": True}
    system_data["predictive_warning"] = ""
    print(f"🔩 [STEP] feed 1 หลุม id={feed_seq} ({FEED_PULSES} พัลส์)")


def feed_motor_housekeeping(curr, now):
    """ทุกรอบลูป: ออกจาก FEED_CARRIER / หยุดเครื่อง / ALARM ระหว่าง feed → สั่ง abort แล้วรอ Rust ยืนยันจบก่อนล้างงาน"""
    global feed_job
    job = feed_job
    if job is None:
        return
    if job.get("manual"):
        # feed จากปุ่ม STEP: หยุดเมื่อเข้า ALARM (E-STOP) หรือหมดเวลา · จบแล้วล้างงาน + รายงาน
        if curr == "ALARM" or now - job["issued"] > FEED_TIMEOUT_S:
            job["abort"] = True
        rep = system_data.get("io_feed") or {}
        finished = rep.get("id") == job["id"] and rep.get("state") in FEED_FINAL
        if job["lost"] or finished or now - job["issued"] > FEED_TIMEOUT_S + 2.0:
            feed_job = None
            state = "lost" if job["lost"] else rep.get("state", "timeout")
            if state == "done":
                print(f"✅ [STEP] id={job['id']} ครบ {rep.get('sent')}/{rep.get('total')} พัลส์")
                count_feed_done(rep)
                # ข้อความที่เกิดเพราะ feed นี้ยังไม่จบ หมดความหมายแล้ว — ล้างทิ้งไม่ให้ค้างบนจอ
                if system_data["predictive_warning"] in ("START BLOCKED: STEP FEED RUNNING", "STEP REJECTED: FEED BUSY"):
                    system_data["predictive_warning"] = ""
            elif curr != "ALARM":
                system_data["predictive_warning"] = f"STEP FEED {rep.get('err') or state} {rep.get('sent')}/{rep.get('total')}"
                print(f"⚠️ [STEP] {system_data['predictive_warning']}")
        return
    if curr != "FEED_CARRIER" or not system_data["running"]:
        if not job["abort"]:
            print(f"🛑 [FEED] abort id={job['id']} (state={curr}, running={system_data['running']})")
        job["abort"] = True
    if job["abort"]:
        rep = system_data.get("io_feed") or {}
        finished = rep.get("id") == job["id"] and rep.get("state") in FEED_FINAL
        # Rust ไม่ตอบสถานะจบของ id นี้ภายในเวลา (เช่นถูกปฏิเสธ) → ล้างทิ้ง ไม่ให้ค้างบล็อก feed ครั้งหน้า
        if job["lost"] or finished or now - job["issued"] > FEED_TIMEOUT_S + 2.0:
            feed_job = None


def feed_motor_step(now):
    """เรียกทุกรอบขณะอยู่ FEED_CARRIER + เครื่องเดิน · คืน (feed ครบแล้ว?, ข้อความ ALARM หรือ None)"""
    global feed_job, feed_seq
    job = feed_job
    if job is None:
        if system_data.get("io_feed") is None:
            return False, "FEED BRIDGE NOT READY"
        feed_seq += 1
        feed_job = {"id": feed_seq, "abort": False, "issued": now, "lost": False}
        print(f"🔩 [FEED] id={feed_seq} ส่ง {FEED_PULSES} พัลส์ (half_ms={FEED_HALF_MS})")
        return False, None
    if job["abort"]:
        return False, None   # งานเก่ากำลังยกเลิก รอ housekeeping ล้างก่อนค่อยออก id ใหม่
    if job["lost"]:
        feed_job = None
        return False, "FEED BRIDGE LINK LOST"
    rep = system_data.get("io_feed") or {}
    if rep.get("id") == job["id"]:
        state = rep.get("state")
        if state == "done":
            feed_job = None
            print(f"✅ [FEED] id={job['id']} ครบ {rep.get('sent')}/{rep.get('total')} พัลส์ ใน {now - job['issued']:.2f} s")
            count_feed_done(rep)
            return True, None
        if state in ("aborted", "error"):
            feed_job = None
            return False, f"FEED BRIDGE {rep.get('err') or state} {rep.get('sent')}/{rep.get('total')}"
    if now - job["issued"] > FEED_TIMEOUT_S:
        job["abort"] = True   # housekeeping จะล้างเมื่อ Rust ยืนยันหยุด
        return False, f"FEED TIMEOUT {FEED_TIMEOUT_S:.0f}s"
    return False, None


def fsm_brain_loop():
    global system_data, trigger_reset_timer, last_state_before_alarm, vision_ready_at
    state_index = STATES.index("LOAD_CARRIER")
    last_transition_time = time.time()
    cycle_start_time = time.time()
    
    last_printed_state = ""
    last_printed_temp = 0
    # จำสถานะของรอบก่อน ใช้จับ "ขอบขาขึ้น" ตอนเข้า ALARM (ดูเหตุผลในลูป)
    last_loop_state = ""

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

            # 🚨 บันทึกแถว ALARM ลง SQL — ต้องดักตรงนี้ที่เดียว
            # บล็อกที่เขียน log ปกติอยู่ใต้ `if running and curr != 'ALARM'` จึงถูกข้ามทั้งก้อน
            # เมื่อเข้า ALARM และทุกทางที่กระโดดเข้า ALARM ก็ `continue` ข้ามบรรทัด log ไปด้วย
            # ผลคือ machine_logs ไม่เคยมีแถว ALARM เลยสักแถว (0 จาก 1,283 แถว ณ 5 ส.ค. 2026)
            # ทำให้ build_ledger_text() กับหน้า Analytics แสดง TRIPPED ไม่ได้ ทั้งที่รองรับไว้แล้ว
            # ดักที่ขอบขาขึ้นครอบคลุมทุกต้นทาง (ESTOP, DECISION NG, สุ่ม 4 แบบ) ในที่เดียว
            # duration = 0 โดยตั้งใจ เพราะ ALARM ค้างจนกว่าจะกด RESET ระยะเวลาจึงไม่มีความหมาย
            if curr == "ALARM" and last_loop_state != "ALARM":
                log_state_transition_to_sql(
                    "ALARM", 0.0, system_data["mode"], system_data["cycles"], status="TRIPPED"
                )
            last_loop_state = curr

            if feed_job is not None:
                feed_motor_housekeeping(curr, now)

            system_data["pocket"] = system_data["cycles"] + 1
            system_data["batch_pockets"] = batch_pockets()
            system_data["pocket_empty"] = pocket_is_empty()
            # หลุมเว้นว่างต้นม้วน: LOAD_PART/VISION เดินผ่านตามเวลา ไม่รอกล้อง/คน (DECISION ที่มาช่วงนี้ถูกทิ้งเพราะ step_allowed = False)
            skip_part = curr in ("LOAD_PART", "VISION") and system_data["pocket_empty"]
            if skip_part and curr != last_printed_state:
                print(f"⏭️ [POCKET {system_data['pocket']}] หลุมเว้นว่าง — ข้าม {curr}")

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
                if sim_faults_active() and curr in ["FEED_CARRIER", "SEAL_PROCESS"] and system_data["cycles"] in [3, 4]:
                    simulated_delay = 0.55

                base_dur = durations.get(curr, 0.5)
                if SIM_STEP_S is not None and hw_active() and curr != "SEAL_PROCESS":
                    base_dur = SIM_STEP_S
                target_dur = (base_dur + simulated_delay) / system_data["speed_mul"]
                if hw_active() and curr == "SEAL_PROCESS":
                    target_dur = max(target_dur, SEAL_HOLD_S)

                # FEED_CARRIER กับมอเตอร์จริง: ออกจากสเต็ปได้เมื่อ Rust ตอบ done เท่านั้น (ไม่ใช่ตามเวลา)
                feed_ok = True
                if curr == 'FEED_CARRIER' and feed_motor_active():
                    feed_ok, feed_err = feed_motor_step(now)
                    if feed_err:
                        system_data["predictive_warning"] = f"⚠️ ERROR: {feed_err}"
                        record_alarm(feed_err)
                        print(f"🚨 [FAULT]: {system_data['predictive_warning']}")
                        last_state_before_alarm = curr
                        state_index = STATES.index('ALARM')
                        last_transition_time = now
                        continue

                if system_data["mode"] == "auto" and sim_faults_active():
                    if curr == 'SENSOR_CHECK_CARRIER' and (now - last_transition_time >= target_dur):
                        if random.random() < 0.015:
                            system_data["predictive_warning"] = "⚠️ ERROR: CARRIER TAPE JAMMED"
                            record_alarm("CARRIER TAPE JAMMED")
                            print(f"🚨 [FAULT]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue
                            
                    # ทอยความน่าจะเป็นของงานเสียแค่ "ครั้งเดียว" ตอนกล้องตรวจเสร็จ
                    # (not step_allowed = ยังไม่ได้เปิดให้ operator ตัดสิน) ถ้าไม่กันไว้
                    # ลูปจะทอยใหม่ทุก 20 ms ระหว่างรอคนกด → เด้ง ALARM แทบทุกครั้ง
                    elif (curr == 'VISION' and system_data["vision_input"] != "camera"
                          and (now - last_transition_time >= target_dur)
                          and not system_data["step_allowed"]):
                        if random.random() < 0.02:
                            system_data["predictive_warning"] = "⚠️ ERROR: PART MISSING OR WRONG SIDE"
                            record_alarm("PART MISSING OR WRONG SIDE", count_ng=True)
                            print(f"🚨 [FAULT]: {system_data['predictive_warning']}")
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
                        if 189 <= temp <= 191:
                            pass 
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
                            print(f"🚨 [FAULT]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue

                    elif curr == 'VISION_QC' and (now - last_transition_time >= target_dur):
                        if random.random() < 0.015:
                            system_data["predictive_warning"] = "⚠️ ERROR: BAD SEALING DETECTED"
                            record_alarm("BAD SEALING DETECTED", count_ng=True)
                            print(f"🚨 [FAULT]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue

                # Semi-Auto stops at every checkpoint for an operator decision.
                # Full hardware runs stay automatic except VISION: that step waits
                # for the OpenMV DECISION instead of using the simulated 2% fault.
                waiting_for_camera = curr == "VISION" and system_data["vision_input"] == "camera" and not skip_part
                waiting_for_operator = curr in checkpoints and system_data["mode"] == "semi" and not skip_part
                if (waiting_for_camera or waiting_for_operator) and not system_data["step_allowed"] and (now - last_transition_time >= target_dur):
                    system_data["step_allowed"] = True
                    vision_ready_at = now
                
                elif not system_data["step_allowed"] and feed_ok and (now - last_transition_time >= target_dur):
                    actual_spent = now - last_transition_time
                    
                    # AI WARNING จำลอง — ปิดตอนรันเครื่องจริง (SIM_FAULTS=0): เวลาของสเต็ปมาจากตัวจับเวลา ไม่ได้วัดกลไก
                    # 25 ก.ย. เจอเตือนผิดที่ SEAL_PROCESS (ช้ากว่าเดิม 0.1 s จากลูปแกว่ง แต่ประวัติแทบไม่แปรปรวน → เกิน mean+1.5σ)
                    # และ feed จริง ~1.64 s เกินเกณฑ์ตายตัว 1.35 s ทุกรอบ
                    if (sim_faults_active() and curr in ["FEED_CARRIER", "SEAL_PROCESS"]
                            and not (curr == "FEED_CARRIER" and feed_motor_active())):
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
                        if not system_data["pocket_empty"]:   # หลุมว่างหัว/ท้าย batch ไม่นับชิ้น
                            system_data["pieces_count"] += 1
                        # ชิ้นที่ N ยังต้องซีล + ตามด้วยหลุมว่างท้าย — batch จบที่ TAKEUP_REEL ของหลุมสุดท้าย
                        # (เดิมหยุดตรงนี้ทันทีที่ครบ N ชิ้นนั้นยังไม่ถูกซีล)
                        state_index = STATES.index('SEAL_PROCESS')
                    elif curr == 'TAKEUP_REEL':
                        total_cycle_time = now - cycle_start_time
                        system_data["cycles"] += 1
                        log_cycle_complete_to_sql(system_data["cycles"], total_cycle_time)
                        
                        # LOAD_CARRIER/INDEX_CARRIER/POWER_ON = ตั้งเครื่องครั้งเดียวหลัง START แรก · รอบถัดไปวนที่ SET_PARAMS
                        if batch_done():
                            system_data["predictive_warning"] = "🎉 SUCCESS: PRODUCTION BATCH COMPLETED!"
                            print(f"\n🏁 [STATUS]: batch ครบ {system_data['pieces_count']} ชิ้น + หลุมว่างหน้า "
                                  f"{LEADER_POCKETS}/หลัง {TRAILER_POCKETS} = {system_data['cycles']} หลุม\n")
                            system_data["running"] = False
                            state_index = STATES.index('READY')
                        elif not system_data["running"]: state_index = STATES.index('READY')
                        else:                          state_index = STATES.index('SET_PARAMS')
                        cycle_start_time = now
                    else:
                        state_index = (state_index + 1) % len(STATES)

                    last_transition_time = now

            # OP0 = ไฟสถานะ FSM · OP1 bit 0/1 = โซลินอยด์ A/B (ย้ายสายมา OP1 24 ก.ย. 2569)
            # กดลงเฉพาะ SEAL_PROCESS ตามเวลาใน durations ไม่ได้อ่านเซนเซอร์ · ALARM/หยุดเครื่อง = ยกขึ้น
            if system_data["current_state"] != 'ALARM':
                OP0 = 0x00
                # Cylinder C ค้างตามปุ่ม INIT ทั้งตอนเดิน หยุด และ ALARM — ปลดด้วย INIT หรือ E-STOP เท่านั้น
                OP1 = 0x04 if system_data.get("cyl_c") == "ON" else 0x00
                if system_data.get("manual_seal") == "DOWN":
                    if system_data["running"]:
                        system_data["manual_seal"] = "UP"
                        print("🔧 [MANUAL_SEAL] ปลดอัตโนมัติ → UP (เครื่องเริ่มเดิน)")
                    else:
                        OP1 |= 0x03
                if feed_job is not None and feed_job.get("manual"):
                    OP0 |= 0x01   # ไฟ FEED ตอนปุ่ม STEP กำลัง feed
                if system_data["running"]:
                    if curr == 'FEED_CARRIER':     OP0 |= 0x01
                    elif curr == 'SEAL_PROCESS':   OP0 |= 0x02; OP1 |= 0x03
                    elif curr == 'TAKEUP_REEL':    OP0 |= 0x04  
                system_data["op0"] = OP0
                system_data["op1"] = OP1
            else:
                system_data["op0"] = 0x08 
                # 28 ก.ย. 2569: C ค้างตามปุ่ม INIT แม้เข้า ALARM (เจ้าของงาน: สั่ง C ด้วย INIT อย่างเดียว) — เดิมปลดเอง
                # ทำให้เทปไหล/ตำแหน่งหลุมเพี้ยนระหว่างรอ RESET · E-STOP ยังปลด C (ตั้ง cyl_c = OFF ในตัวรับ ESTOP)
                system_data["op1"] = 0x04 if system_data.get("cyl_c") == "ON" else 0x00
                if system_data.get("manual_seal") == "DOWN":
                    system_data["manual_seal"] = "UP"
                    print("🔧 [MANUAL_SEAL] ปลดอัตโนมัติ → UP (เข้า ALARM)")

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
                if start_blocked():   # รวมเช็ก batch ครบ (นับถึงหลุมว่างท้าย ไม่ใช่แค่ชิ้นที่ N)
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
                system_data["running"] = False
                if system_data["current_state"] != "ALARM":
                    last_state_before_alarm = system_data["current_state"]
                system_data["current_state"] = "ALARM"
                system_data["op0"] = 0x08
                system_data["op1"] = 0x00
                system_data["predictive_warning"] = "🚨 EMERGENCY STOP ENGAGED"
                system_data["cyl_c"] = "OFF"   # E-STOP ปลด Cylinder C (ALARM อื่นไม่ปลด)
                record_alarm("EMERGENCY STOP PRESSED")
                trigger_reset_timer = True
                print(f"🚨 [COMMAND]: EMERGENCY STOP! Saved break step: {last_state_before_alarm}")
            elif action == "RESET":
                reset_command("WEB")
            elif action == "MODE":
                ok, reason = set_mode(data.get("mode", "auto"), "WEB")
                ack = {"type": "MODE_ACK", "accepted": ok, "mode": system_data["mode"]}
                if not ok:
                    ack["reason"] = reason
                await websocket.send(json.dumps(ack, ensure_ascii=False))
            elif action == "SYNC":
                # ปุ่ม Sync บอร์ดบนเว็บ web_next — value true = ต่อบอร์ดสั่งเครื่องจริง / false = จำลองบนเว็บ
                ok, reason = set_hw_sync(bool(data.get("value", not system_data["hw_sync"])), "WEB")
                ack = {"type": "SYNC_ACK", "accepted": ok, "hw_sync": system_data["hw_sync"]}
                if not ok:
                    ack["reason"] = reason
                await websocket.send(json.dumps(ack, ensure_ascii=False))
            elif action in ("CYL_C", "SINGLE_CYCLE"):
                # ปุ่ม INIT / STEP บนเว็บ web_next (27 ก.ย. 2569) — ใช้กติกาเดียวกับปุ่มบนจอ HMI ทุกอย่าง
                # (INIT ไม่รับตอน ALARM · STEP ต้องหยุด + INIT แล้ว + ไม่มี feed ค้าง) · ผลดูจาก cyl_c / feed_state / predictive_warning
                print(f"🌐 [WEB CMD]: {action} {data.get('value', '')}".rstrip())
                handle_gui_action(data)
            elif action == "NEXT":
                # web_next ของเพื่อนมีปุ่ม NEXT (โหมด step) — gateway เราไม่มีโหมดนี้ ตอบปฏิเสธให้เว็บแสดงเหตุผล
                await websocket.send(json.dumps({"type": "NEXT_ACK", "accepted": False,
                                                 "state": system_data["current_state"], "reason": "not_step_mode"}))
            elif action == "SPEED":
                system_data["speed_mul"] = float(data.get("value", 1.0))
            elif action == "SET_PARAMS":
                if "target_pieces" in data:
                    set_target_pieces(data["target_pieces"], "WEB")
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
                        "data": [{"state": r[0], "duration": r[1], "cycle": r[2], "mode": r[3], "time": r[4]} for r in reversed(rows)],
                        # ประวัติ ALARM พร้อมสาเหตุ (ใหม่สุดก่อน) — หน้า /analytics ของ web_next แสดงเป็นตาราง · เว็บเดิมข้ามคีย์นี้
                        "alarms": read_alarm_history(),
                    }, ensure_ascii=False))
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
                if vision_needs_camera(recv_meta):
                    print("⚠️ [DECISION IGNORED] PASS/NG ที่ VISION ไม่ได้มาจากกล้อง — โหมดกล้องรับผลจากกล้องเท่านั้น")
                    accepted = False
                else:
                    accepted = apply_decision(bool(recv_val), recv_meta)
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
        connected_clients.discard(websocket)   # broadcast อาจตัดทิ้งไปก่อนแล้ว
        print(f"🔴 [WS DISCONNECT] Client detached | active={len(connected_clients)}")

# 25 ก.ย. 2569: client ที่ไม่อ่านข้อความ (สายค้างของแอปกล้องที่ไม่มีใครอ่าน / แท็บเบราว์เซอร์ที่ถูกพัก)
# ทำให้บัฟเฟอร์เต็ม → send() รอไม่จบ → gather ค้าง → เว็บ 3D ไม่อัปเดตทั้งระบบ · ตัด client ที่ส่งไม่ทันทิ้ง
BROADCAST_SEND_TIMEOUT = 1.0

async def _send_or_drop(client, msg):
    try:
        await asyncio.wait_for(client.send(msg), BROADCAST_SEND_TIMEOUT)
    except Exception as error:
        if client in connected_clients:
            connected_clients.discard(client)
            print(f"✂️ [WS DROP] client ไม่อ่านข้อความ ({type(error).__name__}) — ตัดทิ้ง | active={len(connected_clients)}")
            try:
                client.transport.abort()
            except Exception:
                pass

async def broadcast_state():
    while True:
        if connected_clients:
            try:
                msg = json.dumps({"type": "LIVE_SYNC", "system": system_data})
                await asyncio.gather(*[_send_or_drop(client, msg) for client in list(connected_clients)])
            except: pass
        await asyncio.sleep(0.05)

async def main_async():
    init_db()
    hmi.start()
    threading.Thread(target=fsm_brain_loop, daemon=True).start()
    if IO_MONITOR_ENABLED:
        threading.Thread(target=io_monitor_loop, daemon=True).start()
        print(f"[I/O] Rust bridge link enabled at {IO_BRIDGE_HOST}:{IO_BRIDGE_PORT}")
    print(f"[SYNC] board {'available' if IO_MONITOR_ENABLED else 'not started'} · "
          f"{'SYNCED at start' if system_data['hw_sync'] else 'start in SIMULATION — press Sync on the web to drive the board'}")
    print(f"[FEED] motor={'ON' if FEED_MOTOR_ENABLED else 'OFF (timed)'} pulses={FEED_PULSES} "
          f"half_ms={FEED_HALF_MS} timeout={FEED_TIMEOUT_S}s | sim faults={'ON' if SIM_FAULTS_ENABLED else 'OFF'} "
          f"| sim step={'default' if SIM_STEP_S is None else f'{SIM_STEP_S}s'} seal hold={SEAL_HOLD_S}s")
    asyncio.create_task(broadcast_state())
    
    print("\n" + "╔" + "═"*58 + "╗")
    print(f"║ 🔥 [CENTRAL GATEWAY] : CONTROL MATRIX SERVER IS ACTIVE   ║")
    print(f"║ ➔ Host Core : ws://localhost:8765                        ║")
    print(f"║ ➔ GUI Core  : tcp://127.0.0.1:8766                      ║")
    print(f"╚" + "═"*58 + "╝\n")
    
    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        await asyncio.Event().wait() 

if __name__ == "__main__":
    asyncio.run(main_async())
