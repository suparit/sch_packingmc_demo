# -*- coding: utf-8 -*-
"""ทดสอบว่า gateway ที่ระบุคุยกับจอ TouchGFX ได้จริง (จำลองจอด้วย TCP client)

  python test_hmi_link.py gateway_fsm.py
  python test_hmi_link.py gateway_fsm_upgrad.py
"""
import json
import os
import socket
import subprocess
import sys
import time

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

def oneshot(obj, expect_reply=False):
    """จำลองปุ่มกดบนจอ: ต่อ → ยิง JSON → ปิด (แบบเดียวกับ sendJsonToPython ใน MainScreenView.cpp)"""
    s = socket.create_connection(("127.0.0.1", 8766), timeout=3)
    s.sendall((json.dumps(obj) + "\n").encode())
    reply = b""
    if expect_reply:
        s.settimeout(3)
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

def wait_for(monitor, pred, timeout=12):
    """อ่าน stream จากจอ live-monitor จนกว่า pred(payload) จะเป็นจริง"""
    buf = ""
    deadline = time.time() + timeout
    last = {}
    monitor.settimeout(0.5)
    while time.time() < deadline:
        try:
            buf += monitor.recv(4096).decode("utf-8", "replace")
        except socket.timeout:
            continue
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            if not line.strip():
                continue
            try:
                last = json.loads(line)
            except Exception:
                continue
            if pred(last):
                return last
    return last

print(f"\n=== ทดสอบ {TARGET} ===")
env = dict(os.environ)
env.pop("PYTHONIOENCODING", None)     # จงใจไม่ตั้ง เพื่อทดสอบว่า sys.stdout.reconfigure ในไฟล์เอาอยู่จริง
proc = subprocess.Popen([sys.executable, TARGET], cwd=BACKEND, env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
try:
    time.sleep(2.5)
    check("gateway ยังไม่ตายหลังผ่าน 2.5 วิ (encoding fix)", proc.poll() is None,
          f"exit={proc.poll()}")
    if proc.poll() is not None:
        print(proc.stdout.read().decode("utf-8", "replace")[-1500:])
        raise SystemExit(1)

    # 1) จอต่อเข้ามาเป็น live monitor แล้วต้องได้ stream สถานะ
    mon = socket.create_connection(("127.0.0.1", 8766), timeout=3)
    first = wait_for(mon, lambda p: "current_state" in p, timeout=5)
    check("จอต่อ TCP 8766 แล้วได้ payload สถานะ", "current_state" in first, str(first)[:90])
    check("payload มีคีย์ step_allowed (ใช้เด้งปุ่ม PASS/NG)", "step_allowed" in first)
    check("payload มีคีย์ pitch", "pitch" in first)

    # 2) ปุ่มบนจอสั่งเครื่องได้
    oneshot({"action": "SPEED", "value": 4.0})       # เร่งให้ถึง VISION เร็วขึ้น
    oneshot({"action": "SET_PARAMS", "target_pieces": 77, "pitch": 12})
    got = wait_for(mon, lambda p: p.get("target_pieces") == 77 and p.get("pitch") == 12, timeout=4)
    check("SET_PARAMS จากจอมีผลและ broadcast กลับ",
          got.get("target_pieces") == 77 and got.get("pitch") == 12,
          f"target={got.get('target_pieces')} pitch={got.get('pitch')}")

    oneshot({"action": "START"})
    got = wait_for(mon, lambda p: p.get("running") is True, timeout=4)
    check("START จากจอ → running=true", got.get("running") is True)

    # 3) VISION ต้องหยุดรอ operator (step_allowed=true) ไม่ใช่วิ่งผ่านไปเอง
    #    เครื่องมี fault injection สุ่มระหว่างทาง (SENSOR_CHECK 1.5% / VISION 2%) ~3.5% ต่อรอบ
    #    ถ้าเจอให้ RESET แล้วลองใหม่ ไม่ใช่ความผิดของ HMI link
    got = {}
    for attempt in range(4):
        got = wait_for(mon, lambda p: p.get("step_allowed") is True or p.get("current_state") == "ALARM",
                       timeout=12)
        if got.get("step_allowed") is True:
            break
        print(f"  ..    เจอ fault injection สุ่ม ({got.get('current_state')}) — RESET แล้วลองใหม่")
        oneshot({"action": "RESET"})
        time.sleep(0.5)
        oneshot({"action": "START"})
    check("เครื่องหยุดรอที่เช็คพอยต์ (step_allowed=true)",
          got.get("step_allowed") is True, f"state={got.get('current_state')}")
    state_at_gate = got.get("current_state")

    # ต้องค้างอยู่จริง ไม่เดินต่อเอง
    time.sleep(2.0)
    still = wait_for(mon, lambda p: p.get("step_allowed") is not True, timeout=1.5)
    check("ค้างรอ operator จริง ไม่หลุดไปเอง/ไม่เด้ง ALARM",
          still.get("step_allowed") is True and still.get("current_state") == state_at_gate,
          f"state={still.get('current_state')} allowed={still.get('step_allowed')}")

    # 4) กด PASS บนจอ → ต้องเดินต่อ
    oneshot({"action": "DECISION", "value": True})
    got = wait_for(mon, lambda p: p.get("step_allowed") is False and p.get("current_state") != state_at_gate, timeout=5)
    check("กด PASS บนจอแล้วเครื่องเดินต่อ",
          got.get("step_allowed") is False and got.get("current_state") != state_at_gate,
          f"{state_at_gate} -> {got.get('current_state')}")

    # 5) หน้า Report ขอข้อมูลได้
    rep = oneshot({"action": "REQ_REPORT_DATA"}, expect_reply=True)
    ok = False
    try:
        rj = json.loads(rep.strip().split("\n")[0])
        ok = all(k in rj for k in ("total", "ok", "ng", "yield", "log_text", "ledger_text"))
    except Exception:
        pass
    check("REQ_REPORT_DATA ตอบข้อมูลหน้า Report ครบ", ok, rep.strip()[:80])

    # 6) SAVE DATA -> CSV
    rep = oneshot({"action": "EXPORT_CSV"}, expect_reply=True)
    ok = '"status":"saved"' in rep
    check("EXPORT_CSV เขียนไฟล์ CSV สำเร็จ", ok, rep.strip()[:80])

    oneshot({"action": "STOP"})
    mon.close()
finally:
    proc.terminate()
    try:
        out = proc.communicate(timeout=5)[0].decode("utf-8", "replace")
    except Exception:
        proc.kill()
        out = ""

print(f"\n--- ผลรวม {TARGET}: {'ทั้งหมดผ่าน' if not fails else str(len(fails)) + ' ข้อไม่ผ่าน -> ' + ', '.join(fails)} ---")
if "UnicodeEncodeError" in out:
    print("!! ยังเจอ UnicodeEncodeError ใน log ของ gateway")
sys.exit(1 if fails else 0)
