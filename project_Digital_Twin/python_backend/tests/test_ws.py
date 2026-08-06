# -*- coding: utf-8 -*-
"""ทดสอบฝั่งเว็บ 3D Twin (WebSocket 8765) ว่ายังคุมเครื่องได้ครบหลังรีแฟกเตอร์"""
import asyncio, json, os, subprocess, sys, time
import websockets

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# อ้างจากที่อยู่ของไฟล์เทสต์เอง (tests/ อยู่ใต้ python_backend/) — ย้าย repo แล้วไม่พัง
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = sys.argv[1] if len(sys.argv) > 1 else "gateway_fsm.py"
fails = []

def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        fails.append(name)

async def recv_until(ws, pred, timeout=12):
    last = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.0))
        except asyncio.TimeoutError:
            continue
        if msg.get("type") == "LIVE_SYNC":
            last = msg["system"]
            if pred(last):
                return last
    return last

async def main():
    async with websockets.connect("ws://127.0.0.1:8765") as ws:
        await ws.send(json.dumps({"action": "SPEED", "value": 4.0}))
        await ws.send(json.dumps({"action": "START"}))
        s = await recv_until(ws, lambda p: p.get("running") is True, 5)
        check("START ผ่าน WS", s.get("running") is True)

        # เครื่องมี fault injection สุ่ม ~3.5% ต่อรอบ ถ้าเจอให้ RESET แล้วลองใหม่
        s = {}
        for _ in range(4):
            s = await recv_until(ws, lambda p: p.get("step_allowed") is True or p.get("current_state") == "ALARM", 12)
            if s.get("step_allowed") is True:
                break
            print(f"  ..    เจอ fault injection สุ่ม ({s.get('current_state')}) — RESET แล้วลองใหม่")
            await ws.send(json.dumps({"action": "RESET"}))
            await asyncio.sleep(0.5)
            await ws.send(json.dumps({"action": "RESET"}))   # ครั้งแรกแค่ปลด alarm ครั้งที่สองล้างค่า
            await asyncio.sleep(0.3)
            await ws.send(json.dumps({"action": "START"}))
        check("หยุดรอ operator ที่ VISION", s.get("step_allowed") is True, f"state={s.get('current_state')}")
        gate = s.get("current_state")

        await ws.send(json.dumps({"action": "DECISION", "value": True}))
        s = await recv_until(ws, lambda p: p.get("step_allowed") is False and p.get("current_state") != gate, 5)
        # ALARM หลังจากนี้ยังนับว่าผ่าน เพราะ CHECK_TEMP มีสิทธิ์เจอ HEATER OVERHEATED สุ่ม 2%
        # สิ่งที่ทดสอบคือ "ประตูเปิดออกแล้วเครื่องหลุดจาก VISION" ไม่ใช่ปลายทางว่าไปไหน
        check("DECISION PASS ผ่าน WS แล้วปลดล็อกเดินต่อ",
              s.get("step_allowed") is False and s.get("current_state") != gate,
              f"{gate} -> {s.get('current_state')}")

        # DECISION ตอนที่ FSM ไม่ได้รออยู่ ต้องถูกปฏิเสธ ไม่ใช่กระโดดสเต็ปมั่ว
        await ws.send(json.dumps({"action": "DECISION", "value": True}))
        ack = None
        for _ in range(40):
            m = json.loads(await ws.recv())
            if m.get("type") == "DECISION_ACK":
                ack = m
                break
        check("DECISION ตอนไม่ได้รอ ถูกปฏิเสธ (accepted=false)",
              ack is not None and ack.get("accepted") is False, str(ack))

        await ws.send(json.dumps({"action": "GET_HISTORY"}))
        hist = None
        for _ in range(60):
            m = json.loads(await ws.recv())
            if m.get("type") == "HISTORY_RESPONSE":
                hist = m
                break
        check("GET_HISTORY ตอบประวัติ SQL", hist is not None and isinstance(hist.get("data"), list),
              f"{len(hist['data']) if hist else 0} rows")

        await ws.send(json.dumps({"action": "STOP"}))

print(f"\n=== ทดสอบ WebSocket ของ {TARGET} ===")
proc = subprocess.Popen([sys.executable, TARGET], cwd=BACKEND,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(2.5)
    asyncio.run(main())
finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except Exception: proc.kill()

print(f"--- ผลรวม: {'ทั้งหมดผ่าน' if not fails else str(len(fails)) + ' ข้อไม่ผ่าน'} ---")
sys.exit(1 if fails else 0)
