# -*- coding: utf-8 -*-
"""ทดสอบคำสั่ง `GET_STATE` (gateway_fsm.py:481) — คำสั่งที่กล้อง OpenMV ใช้ sync สถานะ

  python test_get_state.py gateway_fsm.py
  python test_get_state.py gateway_fsm_upgrad.py

สิ่งที่ต้องพิสูจน์
  1. ยิงแล้วได้ `type == "LIVE_SYNC"` และใน `.system` มี `current_state` จริง
  2. ตอบ "ทันที 1 ครั้ง" ต่อ 1 คำสั่ง — ไม่ใช่แค่ broadcast รอบ 50 ms ที่มาอยู่แล้ว
     (พิสูจน์ด้วยการเทียบกับ client อีกตัวที่นั่งเงียบ ๆ ในหน้าต่างเวลาเดียวกัน)
  3. payload ฝั่ง WS **มี wrapper ครอบ** ส่วนฝั่ง TCP 8766 **แบน** — protocol.md ข้อ 2 vs ข้อ 3
  4. GET_STATE ไม่มีในช่องทางจอ (protocol.md ข้อ 4 ทำเครื่องหมาย ❌) ยิงไปแล้วต้องไม่พังไม่ตอบ

ทดสอบตอนเครื่อง "ไม่เดิน" เป็นหลัก เพื่อไม่ให้ fault injection สุ่มมารบกวนการเทียบค่า
"""
import asyncio
import json
import sys
import time

import websockets

from testkit import (Checker, Gateway, HMI_PAYLOAD_KEYS, HmiMonitor, WS_SYSTEM_KEYS,
                     WS_URL, hmi_oneshot, target_from_argv, ws_drain, ws_send,
                     ws_wait_type)

TARGET = target_from_argv()
ck = Checker()


async def count_live_sync(ws, window):
    """นับเฟรม LIVE_SYNC ที่เข้ามาในหน้าต่างเวลาที่กำหนด"""
    n = 0
    deadline = time.time() + window
    while True:
        remain = deadline - time.time()
        if remain <= 0:
            break
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=remain))
        except asyncio.TimeoutError:
            break
        if msg.get("type") == "LIVE_SYNC":
            n += 1
    return n


async def ws_part(mon):
    # cam = client ที่ยิง GET_STATE  |  idle = client ที่นั่งเงียบ ๆ ไว้เทียบ
    async with websockets.connect(WS_URL) as cam, websockets.connect(WS_URL) as idle:
        # ---------- 1. รูปทรงของคำตอบ ----------
        await ws_drain(cam)
        await ws_send(cam, {"action": "GET_STATE"})
        reply = await ws_wait_type(cam, "LIVE_SYNC", 3)
        ck.check("[WS] GET_STATE ได้คำตอบ type == LIVE_SYNC", reply is not None and reply.get("type") == "LIVE_SYNC",
                 str(reply)[:70] if reply else "ไม่ได้คำตอบเลย")
        sysd = (reply or {}).get("system", {})
        ck.check("[WS] คำตอบมี wrapper `.system` ครอบ (ไม่ใช่ JSON แบน)",
                 isinstance((reply or {}).get("system"), dict) and "current_state" not in (reply or {}),
                 f"คีย์ชั้นบนสุด = {sorted((reply or {}).keys())}")
        ck.check("[WS] ใน .system มีคีย์ current_state จริง",
                 "current_state" in sysd, f"current_state={sysd.get('current_state')}")

        missing = sorted(WS_SYSTEM_KEYS - set(sysd.keys()))
        ck.check("[WS] .system มีคีย์ครบตาม protocol.md ข้อ 3", not missing,
                 f"ขาด {missing}" if missing else f"{len(sysd)} คีย์")
        ck.check("[WS] ไม่มีคีย์ชื่อ `state` ตามที่ protocol.md ข้อ 3 ระบุ",
                 "state" not in sysd, f"เจอ state={sysd.get('state')!r}" if "state" in sysd else "")
        ck.check("[WS] ตอนบูตยังไม่มี machine_params (โผล่หลัง SET_PARAMS เท่านั้น)",
                 "machine_params" not in sysd,
                 f"เจอ machine_params={sysd.get('machine_params')}" if "machine_params" in sysd else "")

        # ---------- 2. ตอบทันที 1 ครั้งต่อ 1 คำสั่ง (ไม่ใช่แค่ broadcast) ----------
        # broadcast มาทุก 50 ms → ใน 0.25 วิ client ที่นั่งเฉย ๆ ควรได้ราว 5 เฟรม
        # ถ้ายิง GET_STATE 12 ครั้ง ตัวที่ยิงต้องได้มากกว่าตัวที่เงียบอย่างน้อย 10 เฟรม
        await ws_drain(cam)
        await ws_drain(idle)
        for _ in range(12):
            await ws_send(cam, {"action": "GET_STATE"})
        n_cam, n_idle = await asyncio.gather(count_live_sync(cam, 0.25), count_live_sync(idle, 0.25))
        ck.check("[WS] GET_STATE ตอบทันทีรายตัว (ยิง 12 → ได้เกิน client ที่เงียบ ≥10 เฟรม)",
                 n_cam - n_idle >= 10 and n_cam >= 12,
                 f"ตัวที่ยิงได้ {n_cam} เฟรม / ตัวที่เงียบได้ {n_idle} เฟรม ใน 0.25 วิ")

        # ---------- 3. คืนค่าสด ไม่ใช่ snapshot ค้าง ----------
        hmi_oneshot({"action": "SET_PARAMS", "target_pieces": 55, "pitch": 15, "motor_speed": 3})
        time.sleep(0.3)
        await ws_drain(cam)
        await ws_send(cam, {"action": "GET_STATE"})
        reply = await ws_wait_type(cam, "LIVE_SYNC", 3)
        sysd = (reply or {}).get("system", {})
        ck.check("[WS] GET_STATE คืนค่าสด (เห็นค่าที่จอเพิ่งตั้งผ่าน 8766)",
                 sysd.get("target_pieces") == 55 and sysd.get("pitch") == 15,
                 f"target={sysd.get('target_pieces')} pitch={sysd.get('pitch')}")
        ck.check("[WS] machine_params โผล่หลังจอส่ง SET_PARAMS (protocol.md ข้อ 3)",
                 isinstance(sysd.get("machine_params"), dict) and "motor_speed" in sysd.get("machine_params", {}),
                 str(sysd.get("machine_params"))[:60])

        # ---------- 4. เทียบสองช่องทางตอนเครื่องนิ่ง ----------
        tcp_payload = mon.wait_for(lambda p: "current_state" in p, 5)
        await ws_drain(cam)
        await ws_send(cam, {"action": "GET_STATE"})
        reply = await ws_wait_type(cam, "LIVE_SYNC", 3)
        sysd = (reply or {}).get("system", {})
        ck.check("[WS↔TCP] ตอนเครื่องนิ่ง current_state ของสองช่องทางตรงกัน",
                 sysd.get("current_state") == tcp_payload.get("current_state"),
                 f"WS={sysd.get('current_state')} TCP={tcp_payload.get('current_state')}")
        return sysd


def tcp_part(mon):
    payload = mon.wait_for(lambda p: "current_state" in p, 5)
    ck.check("[TCP] payload ฝั่งจอเป็น JSON แบน ไม่มี wrapper `system`",
             "current_state" in payload and "system" not in payload,
             f"คีย์ชั้นบนสุด = {len(payload)} คีย์")
    diff_missing = sorted(HMI_PAYLOAD_KEYS - set(payload.keys()))
    diff_extra = sorted(set(payload.keys()) - HMI_PAYLOAD_KEYS)
    ck.check("[TCP] payload มีครบ 10 คีย์ตาม protocol.md ข้อ 2 ไม่ขาดไม่เกิน",
             not diff_missing and not diff_extra,
             f"ขาด={diff_missing} เกิน={diff_extra}")

    # protocol.md ข้อ 4 ระบุว่า GET_STATE ไม่มีในช่องทางจอ (❌) — ยิงไปต้องไม่ตอบและไม่ทำอะไรพัง
    before = mon.snapshot()
    reply = hmi_oneshot({"action": "GET_STATE"}, expect_reply=True)
    time.sleep(0.3)
    after = mon.wait_for(lambda p: True, 2)
    ck.check("[TCP] GET_STATE ทาง 8766 ไม่มีคำตอบ (ตรงกับ ❌ ใน protocol.md ข้อ 4)",
             reply.strip() == "", f"ตอบกลับ={reply.strip()[:60]!r}")
    ck.check("[TCP] GET_STATE ที่ไม่รู้จักไม่ทำให้ stream จอหลุดหรือ state เพี้ยน",
             after.get("current_state") == before.get("current_state") and mon.frames > 0,
             f"{before.get('current_state')} -> {after.get('current_state')}, {mon.frames} เฟรม")


print(f"\n=== ทดสอบ GET_STATE ของ {TARGET} ===")
with Gateway(TARGET) as gw:
    ck.check("gateway บูตขึ้นและยังไม่ตายหลัง 2.5 วิ", gw.alive, f"exit={gw.proc.poll()}")
    if not gw.alive:
        print("\n".join(gw.log_grep("Error", "Traceback", "error", limit=20)))
        sys.exit(1)
    mon = HmiMonitor()
    try:
        tcp_part(mon)
        asyncio.run(ws_part(mon))
    finally:
        mon.close()

    print("\n  log ฝั่ง gateway ที่เกี่ยวข้อง:")
    for line in gw.log_grep("WS SYNC", "PARAM", limit=8):
        print("    " + line)

sys.exit(ck.finish(TARGET))
