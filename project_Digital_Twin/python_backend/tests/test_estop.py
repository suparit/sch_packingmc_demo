# -*- coding: utf-8 -*-
"""ทดสอบ safety interlock `ESTOP` ทั้งสองช่องทาง

  python test_estop.py gateway_fsm.py
  python test_estop.py gateway_fsm_upgrad.py

สิ่งที่ต้องพิสูจน์ (machine_spec.md ข้อ 6: "E-STOP กด → ตัดกำลังขับทันที → เข้า ALARM")
  A. ทาง WebSocket 8765 (gateway_fsm.py:429)
  B. ทาง TCP 8766 ฝั่งจอ  (gateway_fsm.py:123)
  C. เคสหนัก: กด ESTOP ตอนเครื่องค้างรอ operator ที่ VISION แล้ว RESET / ยิง DECISION ต่อ

ข้อที่ขึ้นต้นด้วย [spec] = เทียบกับข้อความใน protocol.md ข้อ 4 ตรง ๆ
ถ้า fail แปลว่าโค้ดกับเอกสารไม่ตรงกัน ไม่ใช่เทสต์เขียนผิด — ดู test report ประกอบ
"""
import asyncio
import sys
import time

import websockets

from testkit import (Checker, Gateway, HmiMonitor, WS_URL, hmi_oneshot,
                     target_from_argv, ws_drain, ws_reach_vision_gate,
                     ws_recv_until, ws_restart_clean, ws_send, ws_wait_type)

TARGET = target_from_argv()
ck = Checker()


# ==================================================
# A + C — ฝั่ง WebSocket 8765
# ==================================================
async def ws_part():
    async with websockets.connect(WS_URL) as ws:
        # เดินช้า ๆ (speed 0.5) เพื่อให้จับ state ตอนกด ESTOP ได้แน่นอน ไม่แข่งกับลูป 20 ms
        await ws_send(ws, {"action": "SPEED", "value": 0.5})
        await ws_send(ws, {"action": "START"})
        s = await ws_recv_until(ws, lambda p: p.get("running") is True, 5)
        ck.check("[WS] START แล้วเครื่องเดิน (running=true)", s.get("running") is True)

        # รอให้พ้น LOAD_CARRIER ไปก่อน — จะได้แยกออกว่า RESET "คืนสเต็ปที่ค้าง" หรือ "ล้างกลับต้นรอบ"
        s = await ws_recv_until(ws, lambda p: p.get("current_state") == "INDEX_CARRIER", 8)
        state_before = s.get("current_state")
        ck.check("[WS] เครื่องกำลังเดินอยู่จริงก่อนกด ESTOP",
                 s.get("running") is True and state_before not in ("ALARM", None),
                 f"state={state_before}")

        # ---------- A. ESTOP ตอนเครื่องกำลังเดิน ----------
        t0 = time.time()
        await ws_send(ws, {"action": "ESTOP"})
        s = await ws_recv_until(ws, lambda p: p.get("current_state") == "ALARM", 3)
        dt = time.time() - t0
        ck.check("[WS] ESTOP → เข้า ALARM", s.get("current_state") == "ALARM",
                 f"{state_before} -> {s.get('current_state')} ใน {dt*1000:.0f} ms")
        ck.check("[WS] ESTOP → running=false (หยุดเดิน)", s.get("running") is False,
                 f"running={s.get('running')}")
        ck.check("[WS] ESTOP → ตัดกำลังขับ op0=0x08", s.get("op0") == 0x08,
                 f"op0={s.get('op0')}")
        ck.check("[WS] ESTOP → predictive_warning บอก EMERGENCY STOP",
                 "EMERGENCY STOP" in str(s.get("predictive_warning", "")),
                 str(s.get("predictive_warning"))[:60])

        # ต้อง latch ค้างไว้ ปลดเองไม่ได้
        await asyncio.sleep(2.0)
        s = await ws_recv_until(ws, lambda p: p.get("current_state") != "ALARM", 1.5)
        ck.check("[WS] ESTOP ค้างจริง 2 วิ ไม่ปลดเอง ไม่เดินต่อเอง",
                 s.get("current_state") == "ALARM" and s.get("running") is False,
                 f"state={s.get('current_state')} running={s.get('running')}")

        # ---------- RESET แล้วต้องกลับมาเดินได้ ----------
        await ws_send(ws, {"action": "RESET"})
        s = await ws_recv_until(ws, lambda p: p.get("current_state") != "ALARM", 3)
        ck.check("[WS] RESET ปลด ALARM ได้", s.get("current_state") != "ALARM",
                 f"state={s.get('current_state')}")
        ck.check("[WS] RESET คืนกำลังขับ op0=0x00", s.get("op0") == 0, f"op0={s.get('op0')}")
        ck.check("[spec] protocol.md ข้อ4: RESET ทาง WS กลับ state ที่ค้าง",
                 s.get("current_state") == state_before,
                 f"ก่อน ESTOP={state_before} หลัง RESET={s.get('current_state')}")

        st_after_reset = s.get("current_state")
        await ws_send(ws, {"action": "SPEED", "value": 4.0})
        await ws_send(ws, {"action": "START"})
        s = await ws_recv_until(ws, lambda p: p.get("running") is True, 4)
        ck.check("[WS] หลัง ESTOP+RESET แล้ว START ใหม่ได้", s.get("running") is True)
        s = await ws_recv_until(ws, lambda p: p.get("current_state") != st_after_reset, 10)
        ck.check("[WS] เครื่องเดินต่อได้จริงหลัง ESTOP+RESET (state ขยับ)",
                 s.get("current_state") != st_after_reset,
                 f"{st_after_reset} -> {s.get('current_state')}")

        # ---------- C1. ESTOP ตอนค้างรอ operator ที่ VISION ----------
        await ws_restart_clean(ws)
        s = await ws_reach_vision_gate(ws, ck)
        ck.check("[WS] ถึงเช็คพอยต์ VISION รอ operator (step_allowed=true)",
                 s.get("step_allowed") is True, f"state={s.get('current_state')}")
        gate_state = s.get("current_state")

        await ws_send(ws, {"action": "ESTOP"})
        s = await ws_recv_until(ws, lambda p: p.get("current_state") == "ALARM", 3)
        ck.check("[WS] ESTOP ตอนค้างรอที่ VISION → เข้า ALARM เหมือนกัน",
                 s.get("current_state") == "ALARM" and s.get("running") is False,
                 f"{gate_state} -> {s.get('current_state')} running={s.get('running')}")
        ck.note(f"หลัง ESTOP ที่ VISION: step_allowed={s.get('step_allowed')} "
                f"(ESTOP ไม่ได้เคลียร์ธงนี้ในโค้ด)")

        # ---------- C2. ยิง DECISION ตอน E-STOP ค้างอยู่ ----------
        # E-STOP เป็น interlock: ต้องปลดด้วย RESET เท่านั้น ห้ามมีคำสั่งอื่นพาหลุดจาก ALARM
        await ws_send(ws, {"action": "DECISION", "value": True})
        ack = await ws_wait_type(ws, "DECISION_ACK", 3)
        s = await ws_recv_until(ws, lambda p: p.get("current_state") != "ALARM", 2)
        ck.check("[safety] ยิง DECISION ตอน E-STOP ค้าง ต้องไม่พาเครื่องหลุดจาก ALARM",
                 s.get("current_state") == "ALARM",
                 f"ack={ack} state หลังยิง={s.get('current_state')}")

        # ---------- C3. RESET ตอนที่ธง step_allowed ยังค้าง ----------
        await ws_restart_clean(ws)
        s = await ws_reach_vision_gate(ws, ck)
        if s.get("step_allowed") is True:
            await ws_send(ws, {"action": "ESTOP"})
            await ws_recv_until(ws, lambda p: p.get("current_state") == "ALARM", 3)
            await ws_send(ws, {"action": "RESET"})
            s = await ws_recv_until(ws, lambda p: p.get("current_state") != "ALARM", 3)
            ck.check("[spec] protocol.md ข้อ4: RESET เคลียร์ step_allowed (ทาง WS หลัง ESTOP ที่ VISION)",
                     s.get("step_allowed") is False,
                     f"state={s.get('current_state')} step_allowed={s.get('step_allowed')}")
        else:
            ck.check("[spec] protocol.md ข้อ4: RESET เคลียร์ step_allowed (ทาง WS หลัง ESTOP ที่ VISION)",
                     False, "ไปไม่ถึง VISION gate ภายในจำนวนครั้งที่ retry")

        await ws_send(ws, {"action": "STOP"})
        await ws_drain(ws)


# ==================================================
# B — ฝั่งจอ TouchGFX (TCP 8766)
# ==================================================
def tcp_part():
    mon = HmiMonitor()
    try:
        first = mon.wait_for(lambda p: "current_state" in p, 5)
        ck.check("[TCP] จอต่อ 8766 แล้วได้ stream สถานะ", "current_state" in first, str(first)[:70])

        hmi_oneshot({"action": "RESET"})
        hmi_oneshot({"action": "SPEED", "value": 0.5})
        hmi_oneshot({"action": "START"})
        got = mon.wait_for(lambda p: p.get("running") is True, 4)
        ck.check("[TCP] START จากจอ → running=true", got.get("running") is True)

        got = mon.wait_for(lambda p: p.get("current_state") == "INDEX_CARRIER", 8)
        state_before = got.get("current_state")
        ck.check("[TCP] เครื่องกำลังเดินอยู่จริงก่อนกด ESTOP",
                 got.get("running") is True and state_before not in ("ALARM", None),
                 f"state={state_before}")

        t0 = time.time()
        hmi_oneshot({"action": "ESTOP"})
        got = mon.wait_for(lambda p: p.get("current_state") == "ALARM", 3)
        dt = time.time() - t0
        ck.check("[TCP] ESTOP จากจอ → เข้า ALARM", got.get("current_state") == "ALARM",
                 f"{state_before} -> {got.get('current_state')} ใน {dt*1000:.0f} ms")
        ck.check("[TCP] ESTOP จากจอ → running=false", got.get("running") is False,
                 f"running={got.get('running')}")

        time.sleep(2.0)
        still = mon.snapshot()
        ck.check("[TCP] ESTOP ค้างจริง 2 วิ ไม่ปลดเอง",
                 still.get("current_state") == "ALARM" and still.get("running") is False,
                 f"state={still.get('current_state')} running={still.get('running')}")

        hmi_oneshot({"action": "RESET"})
        got = mon.wait_for(lambda p: p.get("current_state") != "ALARM", 3)
        ck.check("[TCP] RESET จากจอ ปลด ALARM ได้", got.get("current_state") != "ALARM",
                 f"state={got.get('current_state')}")
        ck.check("[spec] protocol.md ข้อ4: RESET ทาง TCP กลับ state ที่ค้าง",
                 got.get("current_state") == state_before,
                 f"ก่อน ESTOP={state_before} หลัง RESET={got.get('current_state')}")

        st_after_reset = got.get("current_state")
        hmi_oneshot({"action": "SPEED", "value": 4.0})
        hmi_oneshot({"action": "START"})
        got = mon.wait_for(lambda p: p.get("running") is True, 4)
        ck.check("[TCP] หลัง ESTOP+RESET แล้ว START จากจอได้อีก", got.get("running") is True)
        got = mon.wait_for(lambda p: p.get("current_state") != st_after_reset, 10)
        ck.check("[TCP] เครื่องเดินต่อได้จริงหลัง ESTOP+RESET (state ขยับ)",
                 got.get("current_state") != st_after_reset,
                 f"{st_after_reset} -> {got.get('current_state')}")

        hmi_oneshot({"action": "STOP"})
    finally:
        mon.close()


print(f"\n=== ทดสอบ ESTOP (safety interlock) ของ {TARGET} ===")
with Gateway(TARGET) as gw:
    ck.check("gateway บูตขึ้นและยังไม่ตายหลัง 2.5 วิ", gw.alive, f"exit={gw.proc.poll()}")
    if not gw.alive:
        print("\n".join(gw.log_grep("Error", "Traceback", "error", limit=20)))
        sys.exit(1)
    asyncio.run(ws_part())
    tcp_part()

    print("\n  log ฝั่ง gateway ที่เกี่ยวข้อง:")
    for line in gw.log_grep("EMERGENCY", "RESUME", "RESET", "DECISION", limit=14):
        print("    " + line)

sys.exit(ck.finish(TARGET))
