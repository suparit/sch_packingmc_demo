# -*- coding: utf-8 -*-
"""
🔗 HMI LINK — สะพาน TCP ระหว่าง Python Gateway ↔ จอ TouchGFX (STM32H7S78-DK)

โมดูลนี้ถูกแยกออกมาให้ `gateway_fsm.py` และ `gateway_fsm_upgrad.py` ใช้ร่วมกัน
เดิม `upgrad` ต่อกับจอไม่ได้เลย เพราะมันเปิด socket แบบ *client* ออกไปที่ 8766
ส่วนจอ TouchGFX ก็เป็น client ต่อเข้า 8766 เหมือนกัน → ไม่มีใครเป็น server ต่อกันไม่ติด
พอย้ายมาใช้โมดูลนี้ ทั้งสองไฟล์จะเปิด server ที่ 8766 เหมือนกันหมด และแก้บั๊กครั้งเดียวได้ผลทั้งคู่

โปรโตคอล
--------
Gateway เปิด TCP server ที่ 127.0.0.1:8766 จอ TouchGFX ต่อเข้ามา 2 แบบ:

1. **live monitor** — ต่อค้างไว้เงียบๆ ไม่ส่งอะไรมา → Gateway stream JSON สถานะให้ทุกรอบลูป (20 ms)
2. **one-shot** — ต่อเข้ามาแล้วส่งคำสั่งทันที (ปุ่มกด / ขอรายงาน) ตอบกลับแล้วปิดสาย

แยกสองแบบด้วยการ "พัก" สายที่เพิ่งต่อเข้ามาไว้ 0.25 วิ ถ้าเงียบจนครบเวลา = live monitor
(ถ้า broadcast ให้ทันที หน้า Reportscreen ที่ recv ครั้งเดียวจะได้ payload สถานะแทนข้อมูลรายงาน)

คำสั่งที่โมดูลนี้ตอบเองได้เลย (ไม่ต้องยุ่งกับ FSM):
  REQ_REPORT_DATA / CLEAR_SQL_HISTORY / CLEAR_ALARM_LOGS / EXPORT_CSV
คำสั่งอื่น (START/STOP/RESET/SET_PARAMS/DECISION/...) จะถูกโยนออกไปให้ command handler
ที่ gateway ลงทะเบียนไว้ผ่าน `set_command_handler()` เพราะแต่ละไฟล์มี global ของตัวเอง
"""

import csv
import json
import os
import select
import socket
import sqlite3
import time
from datetime import datetime

# ระยะเวลาที่ "พัก" สายใหม่ไว้ดูว่าเป็น one-shot หรือ live monitor
PENDING_WINDOW_SEC = 0.25

# จำกัดจำนวนบรรทัด alarm log กัน response ล้น buffer 2KB ของฝั่ง TouchGFX
ALARM_LOG_MAX_LINES = 12


# ==================================================
# 🛑 ALARM / E-STOP / RESET — logic ร่วมของข้อ 6 (`docs/specs/fsm_spec.md`) — safety-critical
# ==================================================
# เขียนเป็น pure function อ่าน/เขียนผ่าน system_data ที่รับเข้ามา เพื่อให้ gateway_fsm.py และ
# gateway_fsm_upgrad.py เรียกใช้ตัวเดียวกันได้ ทั้งทาง TCP (handle_gui_action) และทาง WS (ws_handler)
# ปิดบั๊กจริงจาก docs/test-reports/2026-08-04-new-coverage.md (ESTOP ไม่เคลียร์ step_allowed
# + RESET ทาง TCP/WS ทำงานคนละแบบ)
#
# ⚠️ ไม่เก็บ `last_state_before_alarm` ไว้เป็น state ในโมดูลนี้ — ผู้เรียกต้องถือตัวแปรนั้นเป็น
# global ของไฟล์ตัวเอง (ตามที่มีอยู่แล้ว) เพราะห้ามเติมคีย์ใหม่ลง `system_data`: dict นี้ถูก
# `json.dumps` ส่งตรงเป็น payload ทั้งทาง TCP (`build_state_payload`) และ WS (`LIVE_SYNC`) —
# เติมคีย์ใหม่โดยไม่ผ่าน `integration` จะทำให้จำนวนคีย์ที่ `test_get_state.py` ตรวจนับพังทันที
def estop_enter_alarm(system_data, record_alarm_fn, last_state_before_alarm, reason, count_ng=False):
    """ข้อ 6.2 — global handler ของ ESTOP (และของ DECISION-NG ที่ต้องเข้า ALARM ด้วยกติกาเดียวกัน)
    คืน last_state_before_alarm ตัวใหม่ให้ผู้เรียกไปเก็บเอง"""
    cur = system_data["current_state"]
    # ข้อ 6.2 ขั้น 2 — ถ้าอยู่ ALARM อยู่แล้ว (กด ESTOP ซ้ำ) ห้ามทับ last_state_before_alarm เดิม
    new_last = cur if cur != "ALARM" else last_state_before_alarm
    # ข้อ 6.2 ขั้น 3 — เคลียร์ step_allowed ทันที ไม่มีเงื่อนไข (จุดที่บั๊กเดิมพลาด)
    system_data["step_allowed"] = False
    system_data["current_state"] = "ALARM"
    record_alarm_fn(reason, count_ng)
    return new_last


def can_accept_decision(system_data):
    """ข้อ 6.3 — DECISION ระหว่าง ALARM ต้อง block 2 ชั้นอิสระ (defense in depth):
    ชั้นที่ 1 state guard (current_state == VISION เท่านั้น) + ชั้นที่ 2 flag guard (step_allowed == True)
    ต้องเขียนแยกกันจริงในโค้ด ห้ามลดเหลือเช็คตัวเดียวเพราะ "เช็คซ้ำ" """
    state_ok = system_data.get("current_state") == "VISION"
    flag_ok = system_data.get("step_allowed") is True
    return state_ok and flag_ok


def resolve_reset_target(system_data, last_state_before_alarm, fallback="LOAD_CARRIER"):
    """ข้อ 6.4.1 (กิ่งที่ 1) — RESET ที่ปลด ALARM ผู้เรียกต้องเช็คเองก่อนว่า current_state == ALARM
    แล้วเท่านั้นถึงเรียกฟังก์ชันนี้ คืน state ปลายทางให้ผู้เรียกไปตั้ง current_state เอง
    (ไม่มีการล้าง counter ในนี้ — ข้อ 6.4.1 "กิ่งนี้ห้ามแตะ counter เด็ดขาด") + เคลียร์ step_allowed
    ให้เสมอไม่มีเงื่อนไข"""
    target = last_state_before_alarm if last_state_before_alarm else fallback
    system_data["step_allowed"] = False
    return target


# ---------- ข้อ 6.4.4 — โทเคน log ของ RESET (สตริงคงที่ ค้นหาได้ตรง ๆ ห้ามเปลี่ยนถ้อยคำตามช่องทาง)
RESET_LOG_ALARM_CLEAR = "RESET/ALARM-CLEAR"
RESET_LOG_NEW_BATCH = "RESET/NEW-BATCH"
RESET_LOG_IGNORED_RUNNING = "RESET/IGNORED-RUNNING"

# ข้อ 6.4.2 ข้อ 7 — ต้นรอบตาม state_table.csv แถว 0 (ค่าตายตัวของกิ่งที่ 2 ไม่ใช่ fallback)
NEW_BATCH_STATE = "LOAD_CARRIER"


def can_start_new_batch(system_data):
    """ข้อ 6.4.2 — เงื่อนไขของกิ่งที่ 2 ต้องผ่านครบทั้ง 2 ข้อ เขียนแยกกันจริง ห้ามยุบเหลือข้อเดียว
    (แนวเดียวกับ can_accept_decision ของข้อ 6.3)

      branch2_allowed := (current_state != ALARM) AND (running == false)
    """
    # ข้อ 1 — เส้นแบ่ง safety ของข้อ 6.4.3 (กิ่งที่ 2 ห้ามทำงานขณะอยู่ใน ALARM เด็ดขาด)
    state_ok = system_data.get("current_state") != "ALARM"
    # ข้อ 2 — operator กด STOP มาก่อนแล้ว หรือ batch จบเองแล้ว
    idle_ok = system_data.get("running") is False
    return state_ok and idle_ok


def apply_new_batch(system_data):
    """ข้อ 6.4.2 — กิ่งที่ 2 ของ RESET: เริ่ม batch ใหม่ (ล้างสถานะ batch เก่า)
    ทำครบตามตาราง 9 รายการ ยกเว้นข้อ 6 (`last_state_before_alarm`) ที่เป็น global ของ gateway
    แต่ละไฟล์ ผู้เรียกต้องเคลียร์เป็น None เองหลังฟังก์ชันนี้คืน True

    🔴 ข้อ 6.4.3 ชั้นที่ 2 — guard `current_state != ALARM` เขียนซ้ำอยู่ในตัวฟังก์ชันนี้เอง
    ต่อให้ชั้นลำดับของผู้เรียก (ชั้นที่ 1) พังหรือถูก refactor ผิด กิ่งนี้ก็ยังไม่ทำงานใน ALARM
    คืน True เมื่อทำงานจริง / False เมื่อ guard ไม่ผ่าน (ห้ามแตะ system_data เลยกรณีนั้น)"""
    if not can_start_new_batch(system_data):
        return False

    system_data["pieces_count"] = 0        # 1 — ยอดของ batch เก่าต้องไม่ปนกับ batch ใหม่
    system_data["cycles"] = 0              # 2 — ตัวนับรอบของ batch เก่า
    system_data["camera1_count"] = 0       # 3 — คู่เทียบของ COUNT_CHECK
    system_data["encoder_count"] = 0       # 4 — ต้องล้างคู่กับข้อ 3 เสมอ ห้ามล้างตัวเดียว
    system_data["step_allowed"] = False    # 5 — ไม่มีเงื่อนไข กฎเดียวกับกิ่งที่ 1
    system_data["current_state"] = NEW_BATCH_STATE   # 7 — ค่าตายตัว
    system_data["running"] = False         # 8 — 🔴 ห้าม auto-start RESET ไม่ใช่ START
    system_data["predictive_warning"] = ""  # 9 — ล้างข้อความค้างของ batch เก่า
    # ห้ามแตะ: target_pieces / pitch / current_temp / mode / speed_mul / machine_params
    #          ประวัติ SQL + alarm ledger (มี CLEAR_SQL_HISTORY / CLEAR_ALARM_LOGS แยกอยู่แล้ว)
    #          ip0/ip1/op0/op1 (ปล่อยให้ลูปหลักขับตามปกติ) · ห้ามเรียก record_alarm()
    return True


class HmiLink:
    """TCP server ฝั่งจอ TouchGFX — สร้างตัวเดียวต่อ gateway หนึ่งโปรเซส"""

    def __init__(self, system_data, db_file, base_dir, host="127.0.0.1", port=8766):
        self.system_data = system_data
        self.db_file = db_file
        self.base_dir = base_dir
        self.host = host
        self.port = port

        self.server_socket = None
        self.clients = []           # live monitor ที่รับ broadcast อยู่
        self.pending = []           # [(socket, deadline)] รอดูว่าเป็น client แบบไหน

        # 📊 ข้อมูลหน้า Reportscreen
        self.ng_parts_count = 0
        self.alarm_logs = [f"[{datetime.now().strftime('%H:%M:%S')}] SYSTEM INITIALIZED"]

        self._command_handler = None

    # ==================================================
    # 🔧 SETUP
    # ==================================================
    def set_command_handler(self, fn):
        """fn(cmd_dict) — ถูกเรียกทุกครั้งที่จอส่งคำสั่งที่โมดูลนี้ไม่ได้จัดการเอง"""
        self._command_handler = fn

    def start(self):
        """เปิด listener ครั้งแรก เรียกซ้ำได้ (ถ้าเปิดอยู่แล้วจะไม่ทำอะไร)"""
        if self.server_socket is not None:
            return True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # บน Windows ใช้ SO_EXCLUSIVEADDRUSE กันโปรเซสอื่น (เช่น cad/gateway.py) มา bind ซ้อนแบบเงียบๆ
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(5)
            sock.setblocking(False)
            self.server_socket = sock
            print(f"\n[TCP SERVER] Listening for TouchGFX GUI on {self.host}:{self.port}")
            return True
        except Exception as e:
            # ห้ามใส่ emoji ในบรรทัดนี้ — ถ้า bind พลาดตอน stdout เป็น cp874 จะพังซ้อน
            # แล้วรายงานผิดเป็น "bind ไม่ได้" ทั้งที่ปัญหาจริงคือ encoding
            print(f"[TCP SERVER] Cannot bind {self.host}:{self.port} ({e}) "
                  f"— มีโปรเซสอื่นใช้พอร์ตนี้อยู่หรือไม่?")
            self.server_socket = None
            return False

    # ==================================================
    # 📊 ALARM LEDGER / REPORT
    # ==================================================
    def record_alarm(self, msg, count_ng=False):
        if count_ng:
            self.ng_parts_count += 1
        self.alarm_logs.insert(0, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        del self.alarm_logs[ALARM_LOG_MAX_LINES:]

    def reset_ng(self):
        self.ng_parts_count = 0

    def build_ledger_text(self, limit=10):
        """ข้อความ Live SQL Transition Ledger (10 แถวล่าสุด) แบบเดียวกับหน้า Analytics
        รูปแบบแถว: HH:MM:SS STATE 0.53s AUTO #3 NORMAL"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, state_name, duration_sec, control_mode, current_cycle
                FROM machine_logs ORDER BY id DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []

        if not rows:
            return "NO SQL DATA YET"

        lines = []
        for ts, state, dur, mode, cyc in rows:
            # ตัดสถานะตามตรรกะเดียวกับ analytics.html
            status = "NORMAL"
            if dur > 1.35:
                status = "FRICTION"
            if state == "ALARM":
                status = "TRIPPED"
            time_part = ts.split(" ")[1].split(".")[0] if " " in ts else ts
            lines.append(f"{time_part} {state} {dur:.2f}s {str(mode).upper()} #{cyc} {status}")
        return "\n".join(lines)

    def build_report_payload(self):
        ok = self.system_data.get("pieces_count", 0)
        total = ok + self.ng_parts_count
        yield_rate = round((ok / total) * 100, 1) if total > 0 else 0.0
        # separators แบบไม่มีช่องว่าง เพราะ parser ฝั่ง TouchGFX สแกนหา pattern "key":"value" ตรงตัว
        return json.dumps({
            "total": total,
            "ok": ok,
            "ng": self.ng_parts_count,
            "yield": yield_rate,
            "log_text": "\n".join(self.alarm_logs),
            "ledger_text": self.build_ledger_text(),
        }, separators=(",", ":")) + "\n"

    def clear_sql_history(self):
        """ล้างประวัติ SQL ทั้งหมด (ปุ่ม CLEAR LOGS บนจอ) = เริ่มเก็บสถิติ lot ใหม่
        หน้า Analytics บนเว็บจะว่างตามด้วยเพราะใช้ตารางเดียวกัน"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM machine_logs")
            cursor.execute("DELETE FROM production_summary")
            conn.commit()
            conn.close()
        except Exception:
            pass
        self.alarm_logs.clear()
        self.ng_parts_count = 0
        self.record_alarm("SQL HISTORY CLEARED - NEW LOT STARTED")

    def export_csv_report(self):
        """Export machine_logs + production_summary เป็น CSV (ปุ่ม SAVE DATA บนจอ)
        คืนชื่อไฟล์ที่บันทึกสำเร็จ หรือ None ถ้าพลาด"""
        try:
            export_dir = os.path.join(self.base_dir, "exports")
            os.makedirs(export_dir, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            fname = f"report_{stamp}.csv"

            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            # encoding utf-8-sig เพื่อให้ Excel เปิดแล้วอ่านหัวตารางถูกต้องทันที
            with open(os.path.join(export_dir, fname), "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["=== MACHINE STATE LOGS ==="])
                w.writerow(["timestamp", "state_name", "duration_sec", "control_mode", "current_cycle", "status"])
                for row in cursor.execute("SELECT timestamp, state_name, duration_sec, control_mode, current_cycle, status FROM machine_logs ORDER BY id"):
                    w.writerow(row)
                w.writerow([])
                w.writerow(["=== CYCLE SUMMARY ==="])
                w.writerow(["end_timestamp", "cycle_number", "total_duration_sec"])
                for row in cursor.execute("SELECT end_timestamp, cycle_number, total_duration_sec FROM production_summary ORDER BY id"):
                    w.writerow(row)
            conn.close()
            print(f"💾 [EXPORT CSV]: Saved report to exports/{fname}")
            return fname
        except Exception as e:
            print(f"❌ [EXPORT CSV]: Failed ({e})")
            return None

    # ==================================================
    # 📡 PAYLOAD ที่ stream ให้จอ
    # ==================================================
    def build_state_payload(self):
        s = self.system_data
        return json.dumps({
            "current_state": s["current_state"],
            "fsm_state": s["current_state"],
            "running": s["running"],
            "pieces_count": s["pieces_count"],
            "actual_pcs": s["pieces_count"],
            "target_pieces": s["target_pieces"],
            "pitch": s.get("pitch", 24),
            "current_temp": s["current_temp"],
            "cycles": s["cycles"],
            # จอใช้คีย์นี้ตัดสินใจว่าจะเด้ง overlay PASS/NG ของสเต็ป VISION หรือยัง
            "step_allowed": s.get("step_allowed", False),
        }) + "\n"

    # ==================================================
    # 🔁 POLL — เรียกทุกรอบลูป FSM
    # ==================================================
    def poll(self):
        if self.server_socket is None:
            if not self.start():
                return

        self._accept_new()
        self._drain_pending()
        self._drain_live()
        self._broadcast()

    def _accept_new(self):
        # ยังไม่ broadcast ให้ทันที — พักไว้ใน pending ก่อน เพื่อรอดูว่า client ส่งคำสั่งอะไรมา
        try:
            readable, _, _ = select.select([self.server_socket], [], [], 0.001)
            if readable:
                client_sock, _addr = self.server_socket.accept()
                client_sock.setblocking(False)
                self.pending.append((client_sock, time.time() + PENDING_WINDOW_SEC))
        except Exception:
            pass

    def _drain_pending(self):
        """แยกชนิด client ที่พักไว้: ส่งคำสั่งมา = one-shot, เงียบจนครบเวลา = จอหลักรอรับ broadcast"""
        still_pending = []
        for client, deadline in self.pending:
            try:
                r, _, _ = select.select([client], [], [], 0.0)
                if r:
                    cmd_raw = client.recv(4096).decode("utf-8", errors="replace")
                    if not cmd_raw:
                        client.close()
                        continue
                    self._handle_oneshot(client, cmd_raw)
                elif time.time() >= deadline:
                    self.clients.append(client)
                    print("\n🔌 [TOUCHGFX LINK] : GUI CONNECTED (live monitor)")
                else:
                    still_pending.append((client, deadline))
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass
        self.pending[:] = still_pending

    def _handle_oneshot(self, client, cmd_raw):
        """คำสั่งแบบต่อแล้วยิงทีเดียว — ตอบเสร็จปิดสายเสมอ"""
        try:
            if "REQ_REPORT_DATA" in cmd_raw:
                client.sendall(self.build_report_payload().encode("utf-8"))
                print("📊 [TOUCHGFX REPORT]: Sent report data to Reportscreen")
            elif "CLEAR_SQL_HISTORY" in cmd_raw:
                self.clear_sql_history()
                client.sendall((json.dumps({"status": "cleared"}, separators=(",", ":")) + "\n").encode("utf-8"))
                print("🧹 [TOUCHGFX REPORT]: SQL history wiped — new lot started")
            elif "CLEAR_ALARM_LOGS" in cmd_raw:
                self.alarm_logs.clear()
                self.record_alarm("ALARM LOGS CLEARED BY OPERATOR")
                client.sendall((json.dumps({"status": "cleared"}, separators=(",", ":")) + "\n").encode("utf-8"))
                print("🧹 [TOUCHGFX REPORT]: Alarm logs cleared")
            elif "EXPORT_CSV" in cmd_raw:
                fname = self.export_csv_report()
                resp = {"status": "saved", "file": fname} if fname else {"status": "error", "file": ""}
                client.sendall((json.dumps(resp, separators=(",", ":")) + "\n").encode("utf-8"))
            else:
                self.dispatch(cmd_raw)
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _drain_live(self):
        """เผื่อ client ที่ค้างสายยาวส่งคำสั่งตามมาทีหลัง (เช่นจอบอร์ดจริงที่ใช้สายเดียวสองทาง)"""
        for client in list(self.clients):
            try:
                r, _, _ = select.select([client], [], [], 0.0)
                if r:
                    cmd_raw = client.recv(4096).decode("utf-8", errors="replace")
                    if cmd_raw:
                        self.dispatch(cmd_raw)
            except Exception:
                pass

    def dispatch(self, cmd_raw):
        """แกะ JSON ทีละบรรทัดแล้วส่งต่อให้ handler ของ gateway
        (public เพราะ serial_bridge / โค้ดทดสอบ อาจเรียกตรงได้)"""
        for line in cmd_raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                cmd_json = json.loads(line)
            except Exception:
                continue
            if self._command_handler is not None:
                try:
                    self._command_handler(cmd_json)
                except Exception as e:
                    print(f"⚠️ [TOUCHGFX CMD] handler error: {e}")

    def _broadcast(self):
        if not self.clients:
            return
        payload = self.build_state_payload().encode("utf-8")
        disconnected = []
        for client in self.clients:
            try:
                client.sendall(payload)
            except Exception:
                disconnected.append(client)
        for dead in disconnected:
            self.clients.remove(dead)
            try:
                dead.close()
            except Exception:
                pass
