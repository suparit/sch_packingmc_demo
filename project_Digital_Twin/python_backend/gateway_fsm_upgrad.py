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

🎲 fault injection (จำลอง) เปิดเองเมื่อรันแบบจำลองล้วน และ **ปิดเองเมื่อ RUST_BRIDGE=1**
   บังคับด้วยมือได้: FAULT_SIM=1 เปิดแม้ต่อบอร์ดจริง / FAULT_SIM=0 ปิดแม้รันจำลอง
   ดูบรรทัด "FAULT SIM:" ตอนบูตว่าโหมดไหนอยู่
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

# 🔌 สะพานไปฮาร์ดแวร์จริง (Rust Modbus Bridge) — ปิดไว้เป็นค่าเริ่มต้น
RUST_ENABLED    = os.environ.get("RUST_BRIDGE", "0") == "1"
RUST_HOST       = os.environ.get("RUST_HOST", "127.0.0.1")
RUST_PORT       = int(os.environ.get("RUST_PORT", "8767"))
RUST_RETRY_SEC  = 3.0      # เว้นระยะก่อน connect ใหม่ ไม่งั้นยิงทุก 20 ms ตอนบอร์ดไม่ได้เสียบ

# ==================================================
# 🎲 FAULT INJECTION (จำลอง) — สวิตช์เปิด/ปิดการสุ่มโยน fault ใส่ตัวเอง
# ==================================================
# โค้ดนี้มีจุดที่ "แกล้งพัง" ตัวเองอยู่ 5 จุด (SENSOR_CHECK_CARRIER / VISION / CHECK_TEMP /
# COUNT_CHECK / VISION_QC) เพื่อโชว์ว่าระบบจับ error แล้วเข้า ALARM ได้จริง
# — ตอนรันแบบจำลองล้วนมันเป็นฟีเจอร์เดโมที่ดี
# — แต่ตอนต่อบอร์ดจริง (RUST_BRIDGE=1) error ปลอมพวกนี้ปนกับ log ของจริงจนแยกไม่ออก
#   ว่า ALARM ที่เห็นมาจากฮาร์ดแวร์หรือมาจากลูกเต๋าในโค้ด และทำให้รันยาวจนครบ batch ไม่ได้
#
# ค่าเริ่มต้น : เปิดเมื่อรันจำลองล้วน / ปิดอัตโนมัติเมื่อ RUST_BRIDGE=1
# บังคับด้วยมือ (อ่านสไตล์เดียวกับ RUST_BRIDGE ด้านบน):
#     FAULT_SIM=1  → เปิด แม้กำลังต่อบอร์ดจริง (ไว้เดโมให้พี่เลี้ยงดูตอนต่อบอร์ด)
#     FAULT_SIM=0  → ปิด แม้รันจำลองล้วน (ไว้รันยาวดูว่าเดินครบ batch ไหม)
_FAULT_SIM_ENV  = os.environ.get("FAULT_SIM")
FAULT_SIM       = (not RUST_ENABLED) if _FAULT_SIM_ENV is None else (_FAULT_SIM_ENV == "1")
FAULT_SIM_SRC   = "ค่าเริ่มต้นตาม RUST_BRIDGE" if _FAULT_SIM_ENV is None else f"ถูกบังคับด้วย FAULT_SIM={_FAULT_SIM_ENV}"

# ==================================================
# 🏷️ LOG TAG — บอกที่มาของตัวเลขทุกบรรทัด (console เท่านั้น payload ไม่เปลี่ยน)
# ==================================================
# [REAL] = ค่าที่อ่านกลับมาได้จาก rust_bridge (8767) ซึ่งเป็นฝั่งที่คุยกับบอร์ดจริง
# [SIM]  = ค่าจำลองในโค้ดนี้ ไม่ได้แตะฮาร์ดแวร์เลย
#
# ⚠️ สองเรื่องที่ต้องแยกให้ออก:
#    1. ลำดับสเต็ปของ FSM ในไฟล์นี้เดินด้วยตัวจับเวลาในโค้ดเสมอ ไม่ได้เดินตามเซนเซอร์จริง
#       บรรทัด "FSM State:" จึงเป็น [SIM] ตลอด ต่อให้สะพานไปบอร์ดจะต่อติดอยู่ก็ตาม
#       ค่าที่เป็นของจริงได้มีแค่ ip0 ที่อ่านกลับมาจากสะพานเท่านั้น
#    2. [REAL] ที่นี่แปลว่า "ได้ค่าจาก rust_bridge" — ตัว rust_bridge เองอาจกำลังเดินโหมด
#       loopback อยู่ (ต่อบอร์ด 502 ไม่ติดแล้วสะท้อนค่ากลับมา) ฝั่ง Python แยกไม่ออก
#       เพราะ payload ของ 8767 มีคีย์ ip0 คีย์เดียว → ต้องดู log [SIM]/[REAL] ของ rust_bridge ประกอบ
TAG_REAL = "[REAL]"
TAG_SIM  = "[SIM] "

io_link_real       = False   # รอบล่าสุดได้ ip0 มาจาก rust_bridge จริงหรือเปล่า
_rust_fail_streak  = 0
_last_io_log       = 0.0
_last_io_snapshot  = None

# หมายเหตุ: ป้ายทั้งสองยาวเท่ากัน (6 ตัวอักษร) เพื่อให้ log เรียงเป็นคอลัมน์อ่านง่าย
# บรรทัดไหนใช้ป้ายไหนถูกกำหนดตายตัวตามที่มาของค่า ไม่ได้เลือกจากสถานะสายตอนรัน
# (บรรทัด FSM/อุณหภูมิ = [SIM] เสมอ · บรรทัด I/O = เปลี่ยนตามว่าได้ค่าจากสะพานจริงไหม)

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

def _set_io_source(is_real, reason=""):
    """สลับที่มาของค่า I/O แล้ว log **เฉพาะตอนเปลี่ยน** ไม่งั้นลูป 20 ms จะพ่นซ้ำ 50 บรรทัด/วิ"""
    global io_link_real
    if io_link_real == is_real:
        return
    io_link_real = is_real
    if is_real:
        print(f"{TAG_REAL} [HARDWARE LINK] ต่อ Rust I/O Layer ({RUST_HOST}:{RUST_PORT}) ได้แล้ว "
              f"— ค่า ip0 ต่อจากนี้มาจากสะพานจริง")
    else:
        print(f"{TAG_SIM} [HARDWARE LINK] สายไป Rust I/O Layer หลุด ({reason}) "
              f"— กลับไปใช้ค่าจำลองในโค้ด ลองต่อใหม่ทุก {RUST_RETRY_SEC:.0f} วินาที")

def connect_to_rust_layer():
    global rust_socket, _rust_retry_at, _rust_fail_streak
    if rust_socket is not None:
        return True
    if not RUST_ENABLED or time.time() < _rust_retry_at:
        return False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.1)
        s.connect((RUST_HOST, RUST_PORT))
        rust_socket = s
        _rust_fail_streak = 0
        _set_io_source(True)
        return True
    except Exception as e:
        rust_socket = None
        _rust_retry_at = time.time() + RUST_RETRY_SEC
        _rust_fail_streak += 1
        # ครั้งแรกบอกให้ครบ หลังจากนั้นเตือนซ้ำทุก ๆ 10 ครั้ง (~30 วิ) กัน log ท่วมตอนไม่ได้เปิดสะพาน
        if _rust_fail_streak == 1:
            print(f"{TAG_SIM} [HARDWARE LINK] ต่อ rust_bridge {RUST_HOST}:{RUST_PORT} ไม่ติด ({e}) "
                  f"— เดินด้วยค่าจำลอง ลองใหม่ทุก {RUST_RETRY_SEC:.0f} วินาที")
        elif _rust_fail_streak % 10 == 0:
            print(f"{TAG_SIM} [HARDWARE LINK] ยังต่อ rust_bridge ไม่ติด (ครั้งที่ {_rust_fail_streak}) "
                  f"— ตัวเลข I/O ทุกตัวที่เห็นเป็นค่าจำลอง")
        return False

def _log_io_values(ip0, from_bridge):
    """log ค่า I/O พร้อมป้ายที่มา — พิมพ์เมื่อค่าเปลี่ยน (ไม่ถี่กว่า 1 วิ) หรือครบ 5 วิระหว่างเดินเครื่อง"""
    global _last_io_log, _last_io_snapshot
    now = time.time()
    snapshot = (ip0, system_data["op0"], from_bridge)
    changed = snapshot != _last_io_snapshot
    due = system_data["running"] and (now - _last_io_log >= 5.0)
    if not ((changed and now - _last_io_log >= 1.0) or due):
        return
    _last_io_log = now
    _last_io_snapshot = snapshot
    if from_bridge:
        print(f"{TAG_REAL} I/O  ip0=0x{ip0:02X} <- rust_bridge {RUST_HOST}:{RUST_PORT} | "
              f"op0=0x{system_data['op0']:02X} -> ส่งลงสะพานแล้ว | state={system_data['current_state']}")
    else:
        print(f"{TAG_SIM} I/O  ip0=0x{ip0:02X} (ค่าจำลองในโค้ด ไม่ได้อ่านจากบอร์ด) | "
              f"op0=0x{system_data['op0']:02X} ไม่ได้ส่งออกไปไหน | state={system_data['current_state']}")

def sync_with_rust_layer():
    """ส่งสถานะ/เอาต์พุตลงบอร์ดจริง แล้วอ่านค่าอินพุต (ip0) กลับมา
    คืนค่า ip0 ล่าสุด — ถ้าไม่ได้เปิด RUST_BRIDGE จะคืนค่าเดิมเฉยๆ"""
    global rust_socket
    if not connect_to_rust_layer():
        _set_io_source(False, "ยังไม่มีสะพาน")
        _log_io_values(system_data["ip0"], False)
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
            ip0 = json.loads(resp.strip()).get("ip0", system_data["ip0"])
            _log_io_values(ip0, True)
            return ip0
        # สะพานยังต่ออยู่แต่รอบนี้ยังไม่ตอบ — ใช้ค่าเดิมไปก่อน ไม่นับว่าได้ค่าใหม่จากของจริง
    except Exception as e:
        try: rust_socket.close()
        except Exception: pass
        rust_socket = None
        _set_io_source(False, e)
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

                # ลำดับสเต็ป + อุณหภูมิ เป็นค่าที่โค้ดนี้จำลองขึ้นเองทั้งคู่ → [SIM] เสมอ
                # ที่มาของค่า I/O ดูที่บรรทัด "I/O" ซึ่งเป็นตัวเดียวที่ขึ้น [REAL] ได้
                if curr == "CHECK_TEMP":
                    print(f"{TAG_SIM} [{datetime.now().strftime('%H:%M:%S')}] FSM State: {curr} ({system_data['current_temp']}°C) | Status: {status_indicator} | Mode: {system_data['mode'].upper()} | Count: {system_data['pieces_count']}/{system_data['target_pieces']}")
                else:
                    print(f"{TAG_SIM} [{datetime.now().strftime('%H:%M:%S')}] FSM State: {curr} | Status: {status_indicator} | Mode: {system_data['mode'].upper()} | Count: {system_data['pieces_count']}/{system_data['target_pieces']}")

                last_printed_state = curr
                last_printed_temp = system_data["current_temp"]

            if system_data["running"] and curr != 'ALARM':
                simulated_delay = 0.0
                if curr in ["FEED_CARRIER", "SEAL_PROCESS"] and system_data["cycles"] in [3, 4]: simulated_delay = 0.55

                target_dur = (durations.get(curr, 0.5) + simulated_delay) / system_data["speed_mul"]

                if system_data["mode"] == "auto":
                    if curr == 'SENSOR_CHECK_CARRIER' and (now - last_transition_time >= target_dur):
                        if FAULT_SIM and random.random() < 0.015:
                            system_data["predictive_warning"] = "⚠️ ERROR: CARRIER TAPE JAMMED"
                            record_alarm("CARRIER TAPE JAMMED")
                            print(f"{TAG_SIM} 🚨 [FAULT INJECTED (จำลอง)]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue

                    # ทอยความน่าจะเป็นของงานเสียแค่ "ครั้งเดียว" ตอนกล้องตรวจเสร็จ
                    # (not step_allowed = ยังไม่ได้เปิดให้ operator ตัดสิน)
                    # ⚠️ เวอร์ชันเดิมของไฟล์นี้เช็ค step_allowed == True → ทอยใหม่ทุก 20 ms ระหว่างรอคนกด
                    #    ทำให้เด้ง ALARM ~78% ภายใน 2 วินาที กด PASS แทบไม่ทัน
                    elif curr == 'VISION' and (now - last_transition_time >= target_dur) and not system_data["step_allowed"]:
                        if FAULT_SIM and random.random() < 0.02:
                            system_data["predictive_warning"] = "⚠️ ERROR: PART MISSING OR WRONG SIDE"
                            record_alarm("PART MISSING OR WRONG SIDE", count_ng=True)
                            print(f"{TAG_SIM} 🚨 [FAULT INJECTED (จำลอง)]: {system_data['predictive_warning']}")
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
                        if 189 <= temp <= 191: pass
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
                            print(f"{TAG_SIM} 🚨 [FAULT INJECTED (จำลอง)]: {system_data['predictive_warning']}")
                            last_state_before_alarm = curr
                            state_index = STATES.index('ALARM')
                            last_transition_time = now
                            continue

                    elif curr == 'VISION_QC' and (now - last_transition_time >= target_dur):
                        if FAULT_SIM and random.random() < 0.015:
                            system_data["predictive_warning"] = "⚠️ ERROR: BAD SEALING DETECTED"
                            record_alarm("BAD SEALING DETECTED", count_ng=True)
                            print(f"{TAG_SIM} 🚨 [FAULT INJECTED (จำลอง)]: {system_data['predictive_warning']}")
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
                # ข้อ 6.2 — logic เดียวกับทาง TCP ทุกตัวอักษร เรียกผ่าน trigger_estop() ที่เดียว
                trigger_estop("EMERGENCY STOP PRESSED", tag="EMERGENCY STOP")
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

def print_io_mode_banner():
    """สรุปให้ชัดตั้งแต่บรรทัดแรกว่ากำลังเดินโหมดไหน — เปิดมาแล้วต้องตอบได้ทันทีว่า
    ตัวเลขที่จะเห็นต่อจากนี้มาจากบอร์ดจริงหรือจากค่าจำลอง"""
    print("  " + "-" * 58)
    if not RUST_ENABLED:
        print(f"  {TAG_SIM} I/O MODE : SIMULATED ทั้งหมด (ไม่ได้ตั้ง RUST_BRIDGE=1)")
        print(f"  {TAG_SIM}            ค่า ip0/ip1/op0/op1 ทุกตัวเป็นค่าจำลองในโค้ด ไม่มีการต่อฮาร์ดแวร์")
        print(f"  {TAG_SIM}            ถ้าต้องการต่อบอร์ดจริง: RUST_BRIDGE=1 + เปิด rust_bridge ที่พอร์ต {RUST_PORT}")
    else:
        print(f"  {TAG_SIM} I/O MODE : RUST_BRIDGE=1 — จะต่อออกไปที่ tcp://{RUST_HOST}:{RUST_PORT}")
        print(f"  {TAG_SIM}            ตอนนี้ยังไม่ได้ต่อ ค่าที่เห็นยังเป็นค่าจำลองจนกว่าจะขึ้นบรรทัด {TAG_REAL} HARDWARE LINK")
        print(f"  {TAG_SIM}            ต่อไม่ติดจะลองใหม่ทุก {RUST_RETRY_SEC:.0f} วินาที (ไม่ล้ม gateway)")
        print(f"  {TAG_SIM}            ⚠️ {TAG_REAL} = ได้ค่าจาก rust_bridge เท่านั้น — ตัว rust_bridge จะบอกเองอีกที")
        print(f"  {TAG_SIM}               ว่าคุยกับบอร์ด Modbus 502 ติดหรือไม่ (ดู log ฝั่ง Rust)")
    print(f"  {TAG_SIM} ลำดับสเต็ป FSM/อุณหภูมิ เป็นค่าจำลองเสมอในทั้งสองโหมด")

    # บอกให้ชัดว่า ALARM ที่จะเห็นต่อจากนี้ "อาจเป็นของปลอม" หรือ "เป็นของจริงล้วน"
    if FAULT_SIM:
        print(f"  {TAG_SIM} FAULT SIM: ON  ({FAULT_SIM_SRC})")
        print(f"  {TAG_SIM}            โค้ดจะสุ่มโยน fault ใส่ตัวเอง → ALARM ที่เห็นอาจเป็นของปลอม")
        print(f"  {TAG_SIM}            ปิดด้วย FAULT_SIM=0 (หรือรันด้วย RUST_BRIDGE=1 จะปิดให้เอง)")
    else:
        # ไม่มีลูกเต๋าในโค้ดแล้ว ALARM ที่ขึ้นต่อจากนี้มาจากเหตุการณ์จริงเท่านั้น
        off_tag = TAG_REAL if RUST_ENABLED else TAG_SIM
        print(f"  {off_tag} FAULT SIM: OFF ({FAULT_SIM_SRC})")
        print(f"  {off_tag}            ไม่มีการสุ่มโยน fault → ALARM ทุกอันมาจากของจริง/คนกดเท่านั้น")
        print(f"  {off_tag}            อยากได้ fault จำลองไว้เดโม: FAULT_SIM=1")
    print("  " + "-" * 58 + "\n")


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
    print(f"  {rust_line}")
    print_io_mode_banner()

    async with websockets.serve(ws_handler, "0.0.0.0", 8765): await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main_async())
