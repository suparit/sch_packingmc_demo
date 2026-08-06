# -*- coding: utf-8 -*-
"""เครื่องมือร่วมของเทสต์ชุดใหม่ — ESTOP / GET_STATE / กล้อง OpenMV

ทำไมต้องมีไฟล์นี้
-----------------
เทสต์ชุดใหม่ต้องใช้ท่าเดิมซ้ำ ๆ (เปิด gateway, รอ payload, retry ตอนโดน fault injection สุ่ม)
ถ้าก๊อปโค้ดไปทุกไฟล์ พอ gateway เปลี่ยนพฤติกรรมจะต้องไล่แก้หลายที่
**ไม่ได้แตะ `test_hmi_link.py` / `test_ws.py`** — สองไฟล์นั้นยัง standalone เหมือนเดิม

กติกาสำคัญที่ฝังไว้ในไฟล์นี้
  * HmiMonitor ต้องอ่าน socket ตลอดเวลา ไม่งั้น `hmi_link._broadcast()` (hmi_link.py:319-330)
    จะ sendall ไม่ผ่านแล้ว "ตัดสายทิ้งเงียบ ๆ" → เทสต์จะ fail แบบสุ่มโดยไม่ใช่ความผิดของ gateway
  * client ที่เพิ่งต่อ 8766 ต้องเงียบ 0.25 วิก่อน (PENDING_WINDOW_SEC) ถึงจะถูกนับเป็น live monitor
  * fault injection สุ่ม SENSOR_CHECK 1.5% (gateway_fsm.py:275) / VISION 2% (:288) — ต้อง retry ได้
"""
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# tests/ อยู่ใต้ python_backend/ — อ้างจากที่อยู่ของไฟล์เอง ย้าย repo แล้วไม่พัง
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HMI_HOST, HMI_PORT = "127.0.0.1", 8766          # TCP ฝั่งจอ TouchGFX
WS_URL = "ws://127.0.0.1:8765"                  # WebSocket ฝั่งเว็บ + กล้อง
# 8767 เป็นของ Rust bridge — เทสต์ชุดนี้ไม่แตะ

# 10 คีย์ที่ protocol.md ข้อ 2 ระบุว่าจอต้องได้รับ (hmi_link.py:199-213)
HMI_PAYLOAD_KEYS = {
    "current_state", "fsm_state", "running", "pieces_count", "actual_pcs",
    "target_pieces", "pitch", "current_temp", "cycles", "step_allowed",
}
# คีย์ที่ protocol.md ข้อ 3 ระบุว่าฝั่ง WebSocket ต้องมี (gateway_fsm.py:37-53)
WS_SYSTEM_KEYS = {
    "current_state", "running", "step_allowed", "cycles", "pieces_count",
    "target_pieces", "pitch", "current_temp", "mode", "speed_mul",
    "ip0", "ip1", "op0", "op1", "camera1_count", "encoder_count", "predictive_warning",
}


def target_from_argv():
    return sys.argv[1] if len(sys.argv) > 1 else "gateway_fsm.py"


# ==================================================
# ตัวนับผลทดสอบ
# ==================================================
class Checker:
    def __init__(self):
        self.fails = []
        self.total = 0

    def check(self, name, ok, detail=""):
        self.total += 1
        print(("  PASS  " if ok else "  FAIL  ") + name + ("   " + detail if detail else ""))
        if not ok:
            self.fails.append(name)
        return bool(ok)

    def note(self, text):
        """บันทึกสิ่งที่สังเกตเห็น ไม่นับเป็นผ่าน/ไม่ผ่าน"""
        print("  ..    " + text)

    def finish(self, target):
        passed = self.total - len(self.fails)
        tail = "" if not self.fails else "\n      ข้อที่ไม่ผ่าน: " + " | ".join(self.fails)
        print(f"\n--- ผลรวม {target}: {passed}/{self.total} ผ่าน ---{tail}")
        return 1 if self.fails else 0


# ==================================================
# เปิด/ปิด gateway + เก็บ log ไว้แนบเป็นหลักฐาน
# ==================================================
class Gateway:
    """เปิด gateway เป็น subprocess เดี่ยว ๆ แล้วเก็บ stdout ลงไฟล์ temp

    ตั้ง PYTHONUNBUFFERED=1 ให้ลูกเพื่อให้ log ถึงไฟล์ทันที — ถ้าปล่อย buffer ไว้
    ตอน terminate() บน Windows จะถูก TerminateProcess ทิ้งโดยไม่ flush แล้วหลักฐานหาย
    (จงใจไม่ตั้ง PYTHONIOENCODING เพื่อคงเงื่อนไขทดสอบ encoding เดิมของ test_hmi_link.py)
    """

    def __init__(self, target, boot_wait=2.5):
        self.target = target
        self.boot_wait = boot_wait
        stamp = f"{os.path.splitext(os.path.basename(target))[0]}_{os.getpid()}"
        self.log_path = os.path.join(tempfile.gettempdir(), f"gwlog_{stamp}.log")
        self.proc = None
        self._fh = None

    def __enter__(self):
        env = dict(os.environ)
        env.pop("PYTHONIOENCODING", None)
        env["PYTHONUNBUFFERED"] = "1"
        self._fh = open(self.log_path, "w", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen([sys.executable, self.target], cwd=BACKEND, env=env,
                                     stdout=self._fh, stderr=subprocess.STDOUT)
        time.sleep(self.boot_wait)
        return self

    @property
    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def log_grep(self, *keys, limit=12):
        """ดึงบรรทัด log ของ gateway ที่มีคำที่สนใจ (อ่านได้ระหว่างที่ยังรันอยู่)"""
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as f:
                lines = [ln.rstrip() for ln in f if any(k in ln for k in keys)]
        except Exception:
            return []
        return lines[-limit:]

    def __exit__(self, *exc):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        try:
            self._fh.close()
        except Exception:
            pass
        return False


# ==================================================
# ฝั่ง WebSocket 8765
# ==================================================
async def ws_send(ws, obj):
    await ws.send(json.dumps(obj))


async def ws_recv_until(ws, pred, timeout=12):
    """อ่าน LIVE_SYNC จนกว่า pred(system) จะจริง — คืนก้อน `.system` ล่าสุดที่เห็นเสมอ
    (payload ฝั่ง WS มี wrapper ครอบ ต้องแกะ .system ก่อน — protocol.md ข้อ 3)"""
    last = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.0))
        except asyncio.TimeoutError:
            continue
        if msg.get("type") == "LIVE_SYNC":
            last = msg.get("system", {})
            if pred(last):
                return last
    return last


async def ws_wait_type(ws, mtype, timeout=3.0):
    """รอข้อความชนิดที่ระบุ (DECISION_ACK / LIVE_SYNC) โดยข้ามเฟรมอื่นที่แทรกเข้ามา"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.0))
        except asyncio.TimeoutError:
            continue
        if msg.get("type") == mtype:
            return msg
    return None


async def ws_drain(ws, quiet=0.015, max_wait=1.5):
    """ทิ้ง broadcast ที่ค้างในคิวจนเงียบ (broadcast มาทุก 50 ms จึงมีช่องว่างให้ timeout เสมอ)"""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            await asyncio.wait_for(ws.recv(), timeout=quiet)
        except asyncio.TimeoutError:
            return


async def ws_restart_clean(ws, speed=4.0):
    """ล้างสถานะให้กลับต้นรอบแล้วสั่งเดินใหม่
    RESET ครั้งแรกปลด ALARM (คืน last_state_before_alarm) ครั้งที่สองล้างตัวนับกลับ LOAD_CARRIER"""
    await ws_send(ws, {"action": "RESET"})
    await asyncio.sleep(0.4)
    await ws_send(ws, {"action": "RESET"})
    await asyncio.sleep(0.3)
    await ws_send(ws, {"action": "SPEED", "value": speed})
    await ws_send(ws, {"action": "START"})


async def ws_reach_vision_gate(ws, ck=None, attempts=4, timeout=14):
    """พาเครื่องไปหยุดรอ operator ที่เช็คพอยต์ VISION พร้อม retry เมื่อโดน fault injection สุ่ม
    ต้องสั่ง START มาก่อนแล้ว — คืน system ก้อนที่ step_allowed=True (หรือก้อนสุดท้ายถ้าไม่สำเร็จ)"""
    s = {}
    for _ in range(attempts):
        s = await ws_recv_until(
            ws, lambda p: p.get("step_allowed") is True or p.get("current_state") == "ALARM", timeout)
        if s.get("step_allowed") is True:
            return s
        if ck:
            ck.note(f"เจอ fault injection สุ่ม ({s.get('current_state')}) — RESET แล้วลองใหม่")
        await ws_restart_clean(ws)
    return s


# ==================================================
# ฝั่ง TCP 8766 (จอ TouchGFX)
# ==================================================
def hmi_oneshot(obj, expect_reply=False, timeout=3):
    """จำลองปุ่มบนจอ: ต่อ → ยิง JSON → (รอคำตอบ) → ปิด (เหมือน sendJsonToPython ใน MainScreenView.cpp)"""
    s = socket.create_connection((HMI_HOST, HMI_PORT), timeout=timeout)
    s.sendall((json.dumps(obj) + "\n").encode())
    reply = b""
    if expect_reply:
        s.settimeout(timeout)
        try:
            while b"\n" not in reply:
                chunk = s.recv(4096)
                if not chunk:
                    break
                reply += chunk
        except socket.timeout:
            pass
    s.close()
    return reply.decode("utf-8", "replace")


class HmiMonitor(threading.Thread):
    """จำลอง "จอหลัก" ที่ต่อค้างไว้เงียบ ๆ แล้วรับ stream สถานะทุก 20 ms

    อ่านในเธรดตลอดเวลา เพราะถ้าปล่อยให้ buffer เต็ม hmi_link จะตัดสายทิ้งเงียบ ๆ
    """

    def __init__(self, settle=0.5):
        super().__init__(daemon=True)
        self.sock = socket.create_connection((HMI_HOST, HMI_PORT), timeout=3)
        self.sock.settimeout(0.3)
        self.last = {}
        self.states_seen = []
        self.frames = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.start()
        time.sleep(settle)          # เงียบให้ครบ PENDING_WINDOW_SEC ก่อนถึงจะถูกนับเป็น live monitor

    def run(self):
        buf = ""
        while not self._stop.is_set():
            try:
                data = self.sock.recv(8192).decode("utf-8", "replace")
            except socket.timeout:
                continue
            except Exception:
                break
            if not data:
                break
            buf += data
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    p = json.loads(line)
                except Exception:
                    continue
                with self._lock:
                    self.last = p
                    self.frames += 1
                    st = p.get("current_state")
                    if st and (not self.states_seen or self.states_seen[-1] != st):
                        self.states_seen.append(st)

    def snapshot(self):
        with self._lock:
            return dict(self.last)

    def wait_for(self, pred, timeout=8):
        deadline = time.time() + timeout
        while time.time() < deadline:
            p = self.snapshot()
            if p and pred(p):
                return p
            time.sleep(0.02)
        return self.snapshot()

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except Exception:
            pass
