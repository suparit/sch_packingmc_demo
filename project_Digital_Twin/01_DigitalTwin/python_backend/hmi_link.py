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
        # TouchGFX parses this field directly. Keep it ASCII so the UART JSON
        # payload does not contain escaped emoji/degree symbols that the simple
        # firmware parser would render literally.
        alarm_message = str(s.get("predictive_warning", "")).encode("ascii", "ignore").decode("ascii").strip()
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
            "alarm_message": alarm_message,
            # จอใช้คีย์นี้ตัดสินใจว่าจะเด้ง overlay PASS/NG ของสเต็ป VISION หรือยัง
            "step_allowed": s.get("step_allowed", False),
            # สถานะ Cylinder C (ปุ่ม INIT) "ON"/"OFF" — เฟิร์มแวร์จอของเพื่อนใช้คีย์นี้ตัดสินว่า
            # กด INIT ครั้งถัดไปจะส่ง ON หรือ OFF ถ้าไม่มีคีย์ จอจะส่ง ON ตลอดจนปิดไม่ได้
            "cyl_c": s.get("cyl_c", "OFF"),
            # สถานะกระบอกซีล A+B ที่ gateway รับคำสั่งแล้ว "DOWN"/"UP" — จอไฮไลต์ปุ่ม UP/DOWN หน้า Maintenance ตามคีย์นี้
            "manual_seal": s.get("manual_seal", "UP"),
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
