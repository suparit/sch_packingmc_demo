# -*- coding: utf-8 -*-
"""ทดสอบว่า "กล้อง OpenMV" ตัดสินสเต็ป VISION ได้ในฐานะ client ตัวที่ 3

  python test_cam_decision.py gateway_fsm.py
  python test_cam_decision.py gateway_fsm_upgrad.py

โค้ดกล้องจริงอยู่นอก repo (`Digital-Twin-Taping Machine/Cam/app_vision.py`)
**ไฟล์นี้ไม่ได้ import และไม่ได้ต่อกล้องจริง** — จำลองพฤติกรรมของมันด้วย WS client ธรรมดา
ตามที่โค้ดกล้องทำจริง 2 อย่าง:
  * `{"action": "GET_STATE"}`                       (app_vision.py:116)
  * `{"action": "DECISION", "value": <bool>, "meta": ...}` แล้วรอ `DECISION_ACK` (app_vision.py:186-226)

สิ่งที่ต้องพิสูจน์: สเต็ป VISION ตัดสินได้ **3 ทาง** (จอ 8766 / เว็บ 8765 / กล้อง 8765)
โดย client ตัวที่ต่อเข้ามาทีหลังสุดก็สั่งได้ และตอน FSM ไม่ได้รอ ต้องโดนปฏิเสธเหมือนช่องทางอื่น
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
CAM_META = {"src": "openmv", "conf": 0.97, "mode": "presence"}


async def main(mon):
    # ---------- client #1: หน้าเว็บ 3D Twin ----------
    async with websockets.connect(WS_URL) as web:
        await ws_send(web, {"action": "SPEED", "value": 4.0})
        await ws_send(web, {"action": "START"})
        s = await ws_recv_until(web, lambda p: p.get("running") is True, 5)
        ck.check("[web] client #1 (เว็บ) START ได้", s.get("running") is True)

        # ---------- client #3: กล้อง ต่อเข้ามาทีหลังสุด ----------
        async with websockets.connect(WS_URL) as cam:
            await ws_send(cam, {"action": "GET_STATE"})
            reply = await ws_wait_type(cam, "LIVE_SYNC", 3)
            camsys = (reply or {}).get("system", {})
            ck.check("[cam] กล้องต่อทีหลังแล้วยิง GET_STATE ได้ LIVE_SYNC กลับ",
                     reply is not None and "current_state" in camsys,
                     f"current_state={camsys.get('current_state')}")

            # ---------- ยิงตอน FSM ไม่ได้รอ ต้องโดนปฏิเสธ ----------
            # ทำตั้งแต่ต้นรอบ (ยังไม่ถึงสเต็ปที่มี fault injection) แล้ว STOP แช่ state ไว้
            # จะได้ตรวจได้ชัดว่า "ไม่กระโดดสเต็ป" จริง ไม่ใช่แค่เครื่องเดินตามปกติ
            await ws_send(web, {"action": "STOP"})
            frozen = await ws_recv_until(web, lambda p: p.get("running") is False, 3)
            await asyncio.sleep(0.4)
            frozen = await ws_recv_until(web, lambda p: False, 0.3)
            st_frozen = frozen.get("current_state")
            ck.check("[web] STOP แล้ว state แช่นิ่ง พร้อมทดสอบเคสปฏิเสธ",
                     frozen.get("running") is False and frozen.get("step_allowed") is False,
                     f"state={st_frozen}")
            await ws_send(cam, {"action": "DECISION", "value": True, "meta": CAM_META})
            ack = await ws_wait_type(cam, "DECISION_ACK", 3)
            ck.check("[cam] DECISION ตอน FSM ไม่ได้รอ → accepted=false",
                     ack is not None and ack.get("accepted") is False, str(ack))
            ck.check("[cam] DECISION ที่ถูกปฏิเสธต้องมี reason=not_allowed",
                     (ack or {}).get("reason") == "not_allowed", str(ack))
            await asyncio.sleep(1.0)
            after = await ws_recv_until(web, lambda p: False, 0.6)
            ck.check("[cam] DECISION ที่ถูกปฏิเสธไม่ทำให้ FSM กระโดดสเต็ป",
                     after.get("current_state") == st_frozen,
                     f"{st_frozen} -> {after.get('current_state')}")

            # ---------- ทั้ง 3 ช่องทางต้องเห็นว่าเครื่องรออยู่ที่ VISION ----------
            await ws_send(web, {"action": "START"})
            s = await ws_reach_vision_gate(web, ck)
            ck.check("[web] เครื่องหยุดรอ operator ที่ VISION", s.get("step_allowed") is True,
                     f"state={s.get('current_state')}")
            gate_state = s.get("current_state")

            cam_view = await ws_recv_until(cam, lambda p: p.get("step_allowed") is True, 5)
            ck.check("[cam] กล้องเห็น step_allowed=true ผ่าน broadcast ของตัวเอง",
                     cam_view.get("step_allowed") is True and cam_view.get("current_state") == gate_state,
                     f"state={cam_view.get('current_state')}")

            hmi_view = mon.wait_for(lambda p: p.get("step_allowed") is True, 5)
            ck.check("[จอ] จอ TouchGFX เห็น step_allowed=true พร้อมกัน (ช่องทางที่ 3 ยังปกติ)",
                     hmi_view.get("step_allowed") is True and hmi_view.get("current_state") == gate_state,
                     f"state={hmi_view.get('current_state')}")

            # ---------- กล้องยิง DECISION PASS ----------
            await ws_drain(web)
            seen_before = len(mon.states_seen)
            await ws_send(cam, {"action": "DECISION", "value": True, "meta": CAM_META})
            ack = await ws_wait_type(cam, "DECISION_ACK", 3)
            ck.check("[cam] กล้องยิง DECISION PASS แล้วได้ ACK accepted=true",
                     ack is not None and ack.get("accepted") is True, str(ack))

            ack_web = await ws_wait_type(web, "DECISION_ACK", 0.6)
            ck.check("[cam] ACK ส่งกลับเฉพาะตัวที่ยิง ไม่กระจายให้ client อื่น",
                     ack_web is None, f"เว็บได้ ACK ด้วย: {ack_web}")

            s = await ws_recv_until(web, lambda p: p.get("current_state") != gate_state
                                    and p.get("step_allowed") is False, 5)
            ck.check("[web] คำตัดสินของกล้องทำให้เครื่องเดินต่อจริง (เว็บเห็นด้วย)",
                     s.get("current_state") != gate_state and s.get("step_allowed") is False,
                     f"{gate_state} -> {s.get('current_state')}")
            hmi_after = mon.wait_for(lambda p: p.get("current_state") != gate_state, 5)
            ck.check("[จอ] จอเห็นผลของคำตัดสินจากกล้องเหมือนกัน",
                     hmi_after.get("current_state") != gate_state,
                     f"{gate_state} -> {hmi_after.get('current_state')}")

            # สเต็ปถัดไปที่จอเห็น ต้องตรงกับ state_table.csv แถว 7 (VISION next_state_ok = CHECK_TEMP)
            # ยอมรับ ALARM ด้วย เพราะ CHECK_TEMP มีสิทธิ์เจอ HEATER OVERHEATED สุ่ม 2% ทันทีที่เข้าสเต็ป
            nxt = mon.states_seen[seen_before:]
            ck.check("[จอ] หลังกล้องกด PASS สเต็ปถัดไปตรง state_table (VISION → CHECK_TEMP)",
                     bool(nxt) and nxt[0] in ("CHECK_TEMP", "ALARM"),
                     f"{gate_state} -> {' -> '.join(nxt[:3]) if nxt else '(ไม่เห็นสเต็ปใหม่)'}")
            if nxt[:1] == ["ALARM"]:
                ck.note("สเต็ปถัดไปเป็น ALARM = เจอ fault injection ที่ CHECK_TEMP (สุ่ม 2%) ไม่ใช่บั๊ก")

            # ---------- กล้องยิง NG (value=false) → ต้องเข้า ALARM ----------
            await ws_restart_clean(web)
            s = await ws_reach_vision_gate(web, ck)
            if s.get("step_allowed") is True:
                gate_state = s.get("current_state")
                await ws_send(cam, {"action": "DECISION", "value": False, "meta": CAM_META})
                ack = await ws_wait_type(cam, "DECISION_ACK", 3)
                ck.check("[cam] กล้องยิง DECISION NG ได้ ACK accepted=true",
                         ack is not None and ack.get("accepted") is True, str(ack))
                s = await ws_recv_until(web, lambda p: p.get("current_state") == "ALARM", 4)
                ck.check("[cam] NG จากกล้อง → VISION เข้า ALARM (state_table.csv แถว 7 next_state_ng)",
                         s.get("current_state") == "ALARM", f"{gate_state} -> {s.get('current_state')}")
                ck.check("[cam] NG จากกล้องบันทึกเหตุผลว่าเป็น OPERATOR REJECTION",
                         "OPERATOR REJECTION" in str(s.get("predictive_warning", "")),
                         str(s.get("predictive_warning"))[:60])
            else:
                ck.check("[cam] กล้องยิง DECISION NG แล้วเข้า ALARM", False,
                         "ไปไม่ถึง VISION gate ภายในจำนวนครั้งที่ retry")

            await ws_send(web, {"action": "RESET"})
            await asyncio.sleep(0.4)
            await ws_send(web, {"action": "STOP"})
            await ws_drain(web)


print(f"\n=== ทดสอบกล้อง OpenMV ยิง DECISION (client ตัวที่ 3) ของ {TARGET} ===")
with Gateway(TARGET) as gw:
    ck.check("gateway บูตขึ้นและยังไม่ตายหลัง 2.5 วิ", gw.alive, f"exit={gw.proc.poll()}")
    if not gw.alive:
        print("\n".join(gw.log_grep("Error", "Traceback", "error", limit=20)))
        sys.exit(1)
    mon = HmiMonitor()          # client #2 = จอ TouchGFX บน TCP 8766
    try:
        asyncio.run(main(mon))
        ck.check("[จอ] จอ TouchGFX ไม่หลุดตลอดการทดสอบ (ยังได้ stream อยู่)",
                 mon.is_alive() and mon.frames > 100, f"{mon.frames} เฟรม")
        ck.note("ลำดับ state ที่จอเห็น: " + " -> ".join(mon.states_seen[-12:]))
    finally:
        mon.close()

    print("\n  log ฝั่ง gateway ที่เกี่ยวข้อง:")
    for line in gw.log_grep("RECV DECISION", "DECISION", "WS CONNECT", limit=12):
        print("    " + line)

sys.exit(ck.finish(TARGET))
