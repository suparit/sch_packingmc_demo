"""feed เทปโดยให้ Cylinder C (OP1 bit 2) กด carrier แนบ roller ค้างไว้ตลอด
ใช้ Board/FeedPlan ของ dt-taping-dev/tools/feed_pulse_test.py (TID 00 00 · ตรวจ ack · keepalive)
op1 = 0x04 (C กด) | 0x10 (PUL) ตอนขอบขึ้น · 0x04 ตอนขอบลง · โซลินอยด์ซีล bit 0/1 = 0 ตลอด"""
import importlib.util, sys, time

TOOL = r"D:\Work\สหกิจ\Wab\dt-taping-dev\tools\feed_pulse_test.py"
spec = importlib.util.spec_from_file_location("fpt", TOOL)
fpt = importlib.util.module_from_spec(spec); spec.loader.exec_module(fpt)

PITCHES = int(sys.argv[1]) if len(sys.argv) > 1 else 10
HALF_S = 0.020          # เท่าค่าเริ่มต้นของเครื่องมือเพื่อน (--half-ms 20)
CYL_C, PUL = 0x04, 0x10
PRESS_WAIT = 1.0        # รอให้ Cylinder C กดแนบก่อนเริ่มหมุน

assert not fpt.rust_bridge_running(), "rust_bridge ยังเปิดอยู่ — ปิดระบบหลักก่อน"
b = fpt.Board(fpt.BOARD_IP, fpt.BOARD_PORT); b.connect()
plan = fpt.FeedPlan(800, 40.0, 18.0)
total = 0
try:
    b.write_bank(64, 0x00)
    b.write_bank(72, CYL_C)
    print("Cylinder C กดลง (OP1 = 0x04) รอ 1 วินาที", flush=True)
    t = time.time()
    while time.time() - t < PRESS_WAIT:
        b.write_bank(72, CYL_C); time.sleep(0.05)
    t0 = time.time()
    for k in range(1, PITCHES + 1):
        n = plan.next_pitch()
        for _ in range(n):
            b.write_bank(72, CYL_C | PUL); time.sleep(HALF_S)
            b.write_bank(72, CYL_C);       time.sleep(HALF_S)
        total += n
        print(f"pitch {k:2d}: {n} พัลส์  สะสม {total}", flush=True)
    dt = time.time() - t0
    mm = total * plan.mm_per_pulse
    print(f"รวม {total} พัลส์ = {mm:.2f} mm ตามทฤษฎี (D 40 mm) ใช้ {dt:.1f} วิ", flush=True)
finally:
    try:
        t = time.time()                             # ให้มอเตอร์หยุดนิ่งก่อนปล่อย C
        while time.time() - t < 0.3:                # เงียบเกิน ~0.2 s บอร์ดตัดสาย ต้องเขียนคั่นตลอด
            b.write_bank(72, CYL_C); time.sleep(0.05)
        b.write_bank(72, 0x00); b.write_bank(64, 0x00)
        print("ปล่อย Cylinder C + ปิดเอาต์พุตแล้ว (OP1 = 0x00)", flush=True)
    finally:
        b.close()
