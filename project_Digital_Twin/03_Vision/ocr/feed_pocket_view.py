"""ดูกล้องสด + สั่ง feed ทีละหลุม + วัดระยะ feed จากภาพ — หน้าเว็บ http://127.0.0.1:5050

สถานะ 25 ก.ย. 2569: ⚠️ ยังไม่ผ่านการทดสอบกับเทปจริงครบ — บริษัทหยุดจ่ายลมกลางคัน (Cylinder C กดเทปไม่ได้)
    · A+B (template matching + รูสเตอร์) ทดสอบกับภาพจริงที่เลื่อนแบบจำลองแล้ว คลาด < 0.1 px
    · ตัวเลขพัลส์ต่อหลุม/roller D ที่วัดวันนั้นใช้ไม่ได้ (ตัววัดเวอร์ชันก่อนจับผิดเส้น) — ต้องวัดใหม่

ทำไมต้องมีตัวนี้: ระยะ feed ต่อหลุมยังไม่เคยวัดกับของจริง (เครื่องมือ feed เดิมตั้ง 18 mm แต่หลุมจริงห่าง 24 mm)
วัดด้วยกล้องแม่นกว่าไม้บรรทัด และเห็นผลทุกหลุม ไม่ใช่แค่ผลรวม

หลักการวัด (หลุมว่าง ไม่ต้องมีชิ้นงาน)
    - ขอบหลุม = แถวที่ความสว่างเปลี่ยนแรงที่สุดตามแนวเทป ในแถบกลางภาพที่หลุมอยู่
    - ไม้บรรทัด = รูสเตอร์ (ห่างกัน 4 mm) วัดระยะเป็น px จากภาพเองทุกครั้ง -> px/mm
    - Calibrate: ส่งพัลส์จำนวนน้อย (เทปเลื่อนไม่เกินครึ่งหลุม) แล้วดูว่าขอบหลุมเลื่อนกี่ px -> mm/พัลส์จริง
    - Feed 1 หลุม: หลังเดินครบหลุม ขอบหลุมถัดไปต้องกลับมาอยู่ที่จุดอ้างอิงเดิม ส่วนที่เยื้อง = ความคลาด

บอร์ด I/O: ต่อเฉพาะตอนสั่งงาน (ใช้ Board ของ dt-taping-dev/tools/feed_pulse_test.py — TID 00 00 · ตรวจ ack)
    OP1 bit 2 = Cylinder C กด carrier แนบ roller ค้างไว้ตลอดช่วง feed + วัด แล้วค่อยปล่อย
    OP1 bit 4 = PUL มอเตอร์ feed · โซลินอยด์ซีล (bit 0/1) = 0 ตลอด
    ⚠️ ต้องปิดระบบหลัก (STOP.bat) ก่อน — บอร์ดรับได้ทีละการเชื่อมต่อ

วิธีรัน (ปิดโปรแกรม MVS ก่อน · ปิดด้วยปุ่ม "ปิดโปรแกรม" บนหน้าเว็บ หรือ Ctrl+C · ห้ามกด X — กล้องจะค้างจนต้องถอดสาย)
    cd 03_Vision
    .venv-ocr\\Scripts\\python.exe ocr\\feed_pocket_view.py [--exposure-us 100000]
"""
import argparse
import importlib.util
import json
import math
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hik_camera import HikCamera  # noqa: E402
from pocket_measure import (  # noqa: E402
    HOLE_COLS, POCKET_X, TPL_H, hole_pitch_px, locate, make_template, mid_edge, pocket_edge)

_tool = os.path.join(HERE, "..", "..", "dt-taping-dev", "tools", "feed_pulse_test.py")
_spec = importlib.util.spec_from_file_location("feed_pulse_test", _tool)
fpt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fpt)

HOST, PORT = "127.0.0.1", 5050
OP1, OP0 = 72, 64
CYL_C, PUL = 0x04, 0x10
HALF_S = 0.020                 # ครึ่งคาบพัลส์ เท่าค่าเริ่มต้นของเครื่องมือเพื่อน (~25 พัลส์/วิ)
PRESS_S, SETTLE_S = 1.0, 0.6   # รอ Cylinder C กดแนบ · รอเทปนิ่งหลังหยุดหมุนก่อนถ่ายวัด
POCKET_MM, HOLE_MM = 24.0, 4.0
ROLLER_D, PPR = 40.0, 800

state = {
    "edge_y": None, "ref_y": None, "hole_px": None, "busy": False, "msg": "พร้อม",
    "mm_per_pulse": math.pi * ROLLER_D / PPR, "mm_per_pulse_src": "ทฤษฎี (D 40 mm)",
    "direction": None, "carry": 0.0, "results": [],
}
lock = threading.Lock()
latest = {"img": None, "t": 0.0}
stop_evt = threading.Event()
SERVER = {"srv": None}


# ---------------- วิเคราะห์ภาพ ----------------
# ฟังก์ชันวัดย้ายไป pocket_measure.py (25 ก.ย. 2569) ให้แอปกล้อง :5000 ใช้ร่วมกัน — วิธีวัดเดิมทุกอย่าง
TPL = {"main": None}


def fresh_avg(n=3, after=None):
    """เฉลี่ย n ภาพที่ถ่าย 'หลัง' เวลา after — กันใช้ภาพเก่าตอนเทปยังเลื่อน"""
    after = after or time.time()
    got, last_t = [], 0.0
    deadline = time.time() + 10
    while len(got) < n and time.time() < deadline:
        with lock:
            img, t = latest["img"], latest["t"]
        if img is not None and t > after and t != last_t:
            got.append(img.astype(np.float32)); last_t = t
        time.sleep(0.02)
    if not got:
        raise RuntimeError("ไม่ได้ภาพใหม่จากกล้อง")
    return np.mean(got, axis=0)


# ---------------- บอร์ด ----------------
class Rig:
    """ถือสายบอร์ดค้าง + กด Cylinder C ค้างข้ามหลุม (ไม่กด/ปล่อยทุกหลุม — เร็วขึ้น ~1 วิ และเทปไม่ขยับตอนกด/ปล่อย)
    เธรด keepalive เขียน OP1 = C ทุก 50 ms ตอนว่าง (บอร์ดตัดสายถ้าเงียบ ~0.2 วิ)
    ปล่อยเองเมื่อว่างเกิน HOLD_IDLE_S · กดปุ่ม 'ปล่อย Cylinder C' · งานพัง · ปิดโปรแกรม"""

    def __init__(self):
        self.b = None
        self.blk = threading.RLock()
        self.last_use = 0.0
        threading.Thread(target=self._keepalive, daemon=True).start()

    @property
    def engaged(self):
        return self.b is not None

    # ใช้กับ with: เข้า = ต่อ/กด C (ถ้ายังไม่ได้กด) · ออกปกติ = กดค้างต่อ · ออกเพราะงานพัง = ปล่อยทันที
    def __enter__(self):
        return self.engage()

    def __exit__(self, exc_type, *_):
        if exc_type is not None:
            self.release("งานพัง")
        else:
            self.last_use = time.time()

    def engage(self):
        with self.blk:
            self.last_use = time.time()
            if self.b is not None:
                return self
            if fpt.rust_bridge_running():
                raise RuntimeError("ระบบหลักยังเปิดอยู่ (rust_bridge) — กด STOP.bat ก่อน")
            b = fpt.Board(fpt.BOARD_IP, fpt.BOARD_PORT)
            b.connect()
            self.b = b
            try:
                b.write_bank(OP0, 0x00)
                self.hold(PRESS_S)              # รอ Cylinder C กดแนบครั้งแรกเท่านั้น
            except Exception:
                self.release()
                raise
            return self

    def keep(self):
        with self.blk:
            self.b.write_bank(OP1, CYL_C)
            self.last_use = time.time()

    def hold(self, sec):
        t = time.time()
        while time.time() - t < sec:
            self.keep()
            time.sleep(0.05)

    def pulses(self, n):
        with self.blk:
            for _ in range(n):
                self.b.write_bank(OP1, CYL_C | PUL); time.sleep(HALF_S)
                self.b.write_bank(OP1, CYL_C); time.sleep(HALF_S)
            self.last_use = time.time()

    def release(self, why=""):
        with self.blk:
            if self.b is None:
                return
            try:
                self.b.write_bank(OP1, 0x00); self.b.write_bank(OP0, 0x00)
            except Exception:
                try:  # สายหลุด: ต่อใหม่เพื่อปล่อย Cylinder C ให้ได้
                    b2 = fpt.Board(fpt.BOARD_IP, fpt.BOARD_PORT); b2.connect()
                    b2.write_bank(OP1, 0x00); b2.write_bank(OP0, 0x00); b2.close()
                except Exception as e:
                    set_msg(f"⚠️ ปล่อย Cylinder C ไม่สำเร็จ ({e}) — ปิดวาล์วลม/ไฟเอง")
            finally:
                try:
                    self.b.close()
                except Exception:
                    pass
                self.b = None
            if why:
                set_msg(f"ปล่อย Cylinder C แล้ว ({why})")

    def _keepalive(self):
        while not stop_evt.is_set():
            time.sleep(0.05)
            if self.b is None or not self.blk.acquire(blocking=False):
                continue   # งานกำลังถือสายอยู่ (ส่งพัลส์/วัด) — มันเขียนคั่นเองแล้ว
            try:
                if self.b is None:
                    continue
                if time.time() - self.last_use > HOLD_IDLE_S:
                    self.release(f"ว่างเกิน {HOLD_IDLE_S:.0f} วิ")
                else:
                    self.b.write_bank(OP1, CYL_C)
            except Exception as e:
                set_msg(f"⚠️ สายบอร์ดหลุดระหว่างกด Cylinder C ค้าง ({e}) — กำลังต่อใหม่เพื่อปล่อย")
                self.release("สายหลุด")
            finally:
                self.blk.release()


HOLD_IDLE_S = 20.0
holder = Rig()   # ตัวเดียวทั้งโปรแกรม — บอร์ดรับได้ทีละการเชื่อมต่อ


def job_release():
    holder.release("กดปุ่มปล่อย")


# ---------------- งาน ----------------
def set_msg(m):
    with lock:
        state["msg"] = m
    print(m, flush=True)
    try:  # เก็บข้อความลงไฟล์ด้วย เผื่อหน้าเว็บแสดงไม่ได้ ยังย้อนดูผลได้
        with open(os.path.join(HERE, "feed_pocket_view.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + m + "\n")
    except Exception:
        pass


def grab_avg(rig=None, n=3):
    """ภาพเฉลี่ยจากภาพใหม่ n ภาพ · ถ้ามี rig จะเขียนคั่นบอร์ดระหว่างรอภาพ (บอร์ดตัดสายถ้าเงียบ ~0.2 วิ)"""
    if rig is None:
        img = fresh_avg(n)
    else:
        after, got, last_t = time.time(), [], 0.0
        deadline = after + 10
        while len(got) < n and time.time() < deadline:
            rig.keep()
            with lock:
                im, t = latest["img"], latest["t"]
            if im is not None and t > after and t != last_t:
                got.append(im.astype(np.float32)); last_t = t
            time.sleep(0.05)
        if not got:
            raise RuntimeError("ไม่ได้ภาพใหม่จากกล้อง")
        img = np.mean(got, axis=0)
    return img


MIN_SCORE = 0.5   # คะแนนแม่แบบหลุมต่ำกว่านี้ = ภาพไม่เหมือนหลุมอ้างอิง (มืด/เบลอ/ผิดหลุม) -> หยุด ไม่เดาต่อ


def measure_now(near=None, window=None, rig=None, n=3, tpl=None):
    """ตำแหน่งแม่แบบหลุมในภาพใหม่ (float px) + ระยะรูสเตอร์ · เก็บคะแนนไว้ใน state ให้หน้าเว็บเห็น"""
    img = grab_avg(rig, n)
    tpl = tpl or TPL["main"]
    y, sa, sb = locate(img, tpl, near, window)
    with lock:
        state.update(score_pocket=round(sa, 3), score_holes=round(sb, 3))
    if sa < MIN_SCORE:
        raise RuntimeError(f"ภาพไม่ตรงกับหลุมอ้างอิง (คะแนน {sa:.2f}) — เช็กแสง/เทปขยับผิดปกติ แล้วตั้งจุดอ้างอิงใหม่")
    return round(y, 1), hole_pitch_px(img)


def job_calibrate(n_pulses=40):
    """ส่งพัลส์น้อยๆ ดูขอบหลุมเลื่อนกี่ px -> mm/พัลส์จริง + ทิศที่เทปวิ่งในภาพ"""
    with holder as rig:
        img0 = grab_avg(rig)
        yc = mid_edge(img0)
        tpl_c = make_template(img0, yc)          # แม่แบบชั่วคราว ไม่ทับจุดอ้างอิง
        hp = hole_pitch_px(img0)
        y0, _, _ = locate(img0, tpl_c, yc, 5)
        set_msg(f"calibrate: ขอบหลุมเริ่มที่ y={y0:.1f} · ส่ง {n_pulses} พัลส์")
        rig.pulses(n_pulses)
        rig.hold(SETTLE_S)
        # ยังไม่รู้ทิศ -> ค้นทั้งสองทาง ±500 px (หลุมซ้ำทุก ~1074 px จึงไม่จับผิดหลุม)
        y1, hp2 = measure_now(near=y0, window=500, rig=rig, tpl=tpl_c)
    hp = (hp + hp2) / 2
    dy = y1 - y0
    if abs(dy) < 5:
        raise RuntimeError(f"ขอบหลุมแทบไม่ขยับ ({dy:.1f} px) — เทปลื่น/มอเตอร์ไม่หมุน?")
    mm_pp = float(abs(dy) / (hp / HOLE_MM) / n_pulses)
    with lock:
        state.update(mm_per_pulse=mm_pp, direction=1 if dy > 0 else -1, hole_px=hp,
                     mm_per_pulse_src=f"calibrate {n_pulses} พัลส์ = {dy:+.1f} px", carry=0.0,
                     edge_y=y1, ppx_learned=None)
    ppp = POCKET_MM / mm_pp
    set_msg(f"calibrate เสร็จ: {mm_pp:.5f} mm/พัลส์ → {ppp:.2f} พัลส์/หลุม "
            f"(roller D ใช้งาน {mm_pp * PPR / math.pi:.2f} mm) · เทปวิ่ง{'ลง' if dy > 0 else 'ขึ้น'}ในภาพ")


def job_setref():
    img = grab_avg()
    y = mid_edge(img)
    TPL["main"] = make_template(img, y)
    hp = hole_pitch_px(img)
    with lock:
        state.update(ref_y=y, edge_y=y, hole_px=hp, last_off=0.0)   # ค่า px/พัลส์ที่เรียนรู้แล้วเก็บไว้ใช้ต่อ
    set_msg(f"ตั้งจุดอ้างอิงที่ขอบหลุม y={y} + เก็บแม่แบบหลุม (รูสเตอร์ {hp:.1f} px = 4 mm)")


def job_feed():
    with lock:
        ref, mm_pp, carry = state["ref_y"], state["mm_per_pulse"], state["carry"]
    if ref is None or TPL["main"] is None:
        raise RuntimeError("ยังไม่ได้ตั้งจุดอ้างอิง — กด 'ตั้งจุดอ้างอิง' ก่อน")
    want = POCKET_MM / mm_pp + carry          # แจกเศษพัลส์สะสมข้ามหลุม ระยะรวมไม่ไหล
    n = int(round(want))
    with holder as rig:
        rig.pulses(n)
        rig.hold(SETTLE_S)
        hp_now = state["hole_px"] or 179.0
        y, hp = measure_now(near=ref, window=hp_now * 2.5, rig=rig)   # ขอบหลุมถัดไปควรมาอยู่ใกล้จุดอ้างอิง
    off_px = y - ref
    px_mm = hp / HOLE_MM
    sgn = state["direction"] or 1
    travel_mm = POCKET_MM + sgn * off_px / px_mm    # เยื้องไปทางที่เทปวิ่ง = เดินเกิน
    row = {"i": len(state["results"]) + 1, "pulses": n, "edge_y": y, "off_px": off_px,
           "off_mm": round(off_px / px_mm, 3), "travel_mm": round(travel_mm, 3),
           "t": time.strftime("%H:%M:%S")}
    with lock:
        state["results"].append(row)
        state.update(edge_y=y, hole_px=hp, carry=want - n)
    note = "" if state["direction"] else " (ยังไม่ calibrate ทิศ — เครื่องหมาย +/- ยังไม่แน่นอน)"
    set_msg(f"feed #{row['i']}: {n} พัลส์ · ขอบหลุม y={y} เยื้อง {off_px:+.1f} px = {row['off_mm']:+.2f} mm "
            f"→ เดินจริง ≈ {travel_mm:.2f} mm{note}")


COARSE_FRAC = 0.92      # ช่วงเร็วตอนยังไม่มีค่าที่เรียนรู้: เดิน 92% (calibrate 40 พัลส์คลาดได้ ~7%)
COARSE_FRAC_LEARNED = 0.95   # มีค่า px/พัลส์ที่เรียนรู้แล้ว: เดิน 95% — พัลส์ต่อหลุมจริงแกว่ง 161–170 (±3%) 25 ก.ย.
LEARN_W = 0.5                # น้ำหนักค่าใหม่ใน EMA ของ px/พัลส์
LEARN_MAX_DEV = 0.15         # รอบไหนได้ px/พัลส์ต่างจาก calibrate เกินนี้ ไม่นำไปเรียนรู้ (กันค่าเพี้ยนลาม)
OVERSHOOT_OK_PULSES = 1.0    # เลยเส้นไม่เกิน 1 พัลส์ (~0.15 mm) = ละเอียดสุดที่มอเตอร์หยุดได้ ไม่นับว่าเลย
FINE_GAIN = 0.7         # ช่วงเข้าเส้น: เดินทีละ 70% ของระยะที่เหลือ กันเลยเส้นจากค่าวัดแกว่ง
FINE_MAX_STEPS = 25


def job_feed_to_line():
    """feed จนขอบหลุมถัดไปมาถึงเส้นอ้างอิงแล้วหยุด — ใช้กล้องปิดลูป ไม่พึ่งจำนวนพัลส์อย่างเดียว"""
    with lock:
        ref, mm_pp, sgn, hp = state["ref_y"], state["mm_per_pulse"], state["direction"], state["hole_px"]
        learned, last_off = state.get("ppx_learned"), state.get("last_off", 0)
    if ref is None or sgn is None or TPL["main"] is None:
        raise RuntimeError("ต้อง Calibrate และตั้งจุดอ้างอิงก่อน (ต้องรู้ทิศที่เทปวิ่งในภาพ)")
    px_mm = (hp or 179.0) / HOLE_MM
    px_pp = learned or mm_pp * px_mm                  # px ต่อพัลส์: ค่าที่เรียนรู้จากหลุมก่อนๆ ถ้ามี
    pocket_px = POCKET_MM * px_mm
    # ระยะที่ต้องเดินจริง = 1 หลุม ลบส่วนที่หลุมก่อนเลยเส้นไปแล้ว (บวกส่วนที่ยังไม่ถึง) — ความคลาดไม่สะสม
    need_px = pocket_px - sgn * last_off
    est = need_px / px_pp
    n_coarse = max(0, int(est * (COARSE_FRAC_LEARNED if learned else COARSE_FRAC)))
    total, steps, over = 0, 0, False
    with holder as rig:
        rig.pulses(n_coarse); total += n_coarse
        rig.hold(0.15)
        guess = ref - sgn * (need_px - n_coarse * px_pp)   # ขอบหลุมถัดไปน่าจะอยู่ตรงนี้
        y, hp = measure_now(near=guess, window=pocket_px * 0.25, rig=rig, n=2)
        while True:
            remain = sgn * (ref - y)                      # px ที่ยังต้องเดิน (ติดลบ = เลยเส้น)
            if remain < -OVERSHOOT_OK_PULSES * px_pp:
                over = True
                break
            if remain < -0.5 * px_pp:     # เลยนิดเดียว (≤ 1 พัลส์) = ถึงเส้นแล้ว
                break
            if remain <= 0.5 * px_pp or steps >= FINE_MAX_STEPS:
                break
            k = max(1, int(remain / px_pp * FINE_GAIN))
            rig.pulses(k); total += k; steps += 1
            rig.hold(0.15)
            exp_y = y + sgn * k * px_pp
            y, hp = measure_now(near=exp_y, window=max(60, 3 * k * px_pp), rig=rig, n=2)
    off_px = y - ref
    px_mm = hp / HOLE_MM
    travel_px = pocket_px + sgn * (off_px - last_off)          # เทปเดินจริงรอบนี้ (px) — นับหลุมที่เลยเส้นด้วย
    ppx_now = travel_px / total if total else px_pp
    base = mm_pp * px_mm                                        # ค่าจาก calibrate
    if abs(ppx_now / base - 1) > LEARN_MAX_DEV:
        # ต่างจาก calibrate เกินที่เทปลื่นจริงได้ (±3% ที่วัด 25 ก.ย.) = น่าจะวัดผิด ไม่เอามาเรียนรู้
        new_learned = learned
        set_msg(f"⚠️ หลุมนี้ได้ {pocket_px / ppx_now:.0f} พัลส์/หลุม ต่างจาก calibrate เกิน "
                f"{LEARN_MAX_DEV:.0%} — ไม่นำไปเรียนรู้")
    else:
        new_learned = ppx_now if learned is None else (1 - LEARN_W) * learned + LEARN_W * ppx_now
    row = {"i": len(state["results"]) + 1, "mode": "line", "pulses": total, "edge_y": y, "off_px": off_px,
           "off_mm": round(off_px / px_mm, 3), "travel_mm": round(travel_px / px_mm, 3),
           "fine_steps": steps, "overshoot": over, "t": time.strftime("%H:%M:%S"),
           "pulses_per_pocket": round(pocket_px / ppx_now, 1)}
    with lock:
        state["results"].append(row)
        state.update(edge_y=y, hole_px=hp, ppx_learned=float(new_learned), last_off=float(off_px))
    warn = " ⚠️ เลยเส้น (มอเตอร์ถอยไม่ได้ — หลุมถัดไปจะเดินน้อยลงชดเชย)" if over else ""
    set_msg(f"feed ถึงเส้น #{row['i']}: รวม {total} พัลส์ (เร็ว {n_coarse} + เข้าเส้น {steps} ครั้ง) · "
            f"ห่างเส้น {off_px:+.1f} px = {row['off_mm']:+.2f} mm · หลุมนี้เท่ากับ {row['pulses_per_pocket']} พัลส์/หลุม{warn}")


def run_job(fn):
    with lock:
        if state["busy"]:
            return False
        state["busy"] = True

    def worker():
        try:
            fn()
        except Exception as e:
            set_msg(f"❌ {type(e).__name__}: {e}")
        finally:
            with lock:
                state["busy"] = False
    threading.Thread(target=worker, daemon=True).start()
    return True


# ---------------- กล้อง ----------------
def camera_loop(exposure_us, gain_db):
    try:
        with HikCamera(exposure_us=exposure_us, gain_db=gain_db) as cam:
            print(f"เปิดกล้องแล้ว exposure {exposure_us / 1000:.0f} ms · http://{HOST}:{PORT}", flush=True)
            while not stop_evt.is_set():
                img = cam.grab()
                with lock:
                    latest["img"], latest["t"] = img, time.time()
        print("ปิดกล้องเรียบร้อย", flush=True)
    except Exception as e:
        set_msg(f"❌ กล้อง: {e}")


def annotated_jpeg():
    with lock:
        img = latest["img"]
        edge, ref = state["edge_y"], state["ref_y"]
    if img is None:
        return None
    tpl = TPL["main"]
    if tpl is not None and ref is not None:
        try:   # ภาพสด: หาหลุมที่ตรงแม่แบบใกล้เส้นอ้างอิงที่สุด (ช่วง ±ครึ่งหลุม)
            live_edge, _, _ = locate(img, tpl, ref, 480)
        except Exception:
            live_edge = pocket_edge(img)
    else:
        live_edge = mid_edge(img)
    live_edge = int(round(live_edge))
    vis = cv2.cvtColor(cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX), cv2.COLOR_GRAY2BGR)
    cv2.rectangle(vis, (POCKET_X[0], 0), (POCKET_X[1], vis.shape[0] - 1), (90, 90, 90), 2)
    if ref is not None:
        r = int(round(ref))
        cv2.line(vis, (0, r), (vis.shape[1], r), (0, 200, 0), 5)
        cv2.rectangle(vis, (POCKET_X[0], r - TPL_H), (POCKET_X[1], r + TPL_H), (0, 120, 0), 2)
    cv2.line(vis, (POCKET_X[0], live_edge), (POCKET_X[1], live_edge), (0, 160, 255), 3)
    small = cv2.resize(vis, None, fx=0.35, fy=0.35, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return buf.tobytes() if ok else None


PAGE = """<!doctype html><html lang="th"><head><meta charset="utf-8"><title>Feed Pocket View</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{margin:0;background:#101412;color:#e6ebe8;font:14px/1.5 system-ui,Segoe UI,Tahoma,sans-serif;padding:12px}
.wrap{display:grid;grid-template-columns:minmax(300px,1fr) 1fr;gap:12px}@media(max-width:800px){.wrap{grid-template-columns:1fr}}
img{width:100%;border:1px solid #2c3431;background:#000}button{font:inherit;font-weight:600;padding:10px 14px;margin:0 6px 6px 0;
border:0;border-radius:6px;background:#4fbfb1;color:#101412;cursor:pointer}button:disabled{opacity:.4}
.card{background:#1a1f1d;border:1px solid #2c3431;border-radius:8px;padding:10px 12px;margin-bottom:10px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{border-bottom:1px solid #2c3431;padding:3px 6px;text-align:right}
th{color:#9aa5a0;font-weight:500}.k{color:#9aa5a0}#msg{min-height:1.5em}.g{color:#4fbfb1}.o{color:#f2894f}</style></head><body>
<div class="wrap"><div><img id="cam" alt="camera"><div class="k">เขียว = จุดอ้างอิง (กรอบเขียว = แม่แบบหลุม) · ส้ม = หลุมที่ตรงแม่แบบในภาพสด · ตั้งจุดอ้างอิงตอนขอบหลุมอยู่กลางภาพ</div></div>
<div><div class="card"><button id="bref">ตั้งจุดอ้างอิง</button><button id="bcal">Calibrate (40 พัลส์)</button><button id="bfeed">Feed 1 หลุม (นับพัลส์)</button><button id="bline">Feed ถึงเส้น</button><button id="brel" style="background:#f2894f">ปล่อย Cylinder C</button><button id="bquit" style="background:#555;color:#fff">ปิดโปรแกรม</button>
<div id="msg"></div></div><div class="card" id="info"></div>
<div class="card"><table><thead><tr><th>#</th><th>เวลา</th><th>พัลส์</th><th>เยื้อง px</th><th>เยื้อง mm</th><th>เดินจริง mm</th></tr></thead><tbody id="rows"></tbody></table></div>
<div class="k">⚠️ มือออกจาก roller/หัวกดก่อนกดปุ่ม · Cylinder C จะกดลงเองทุกครั้ง · ปิดโปรแกรมด้วย Ctrl+C เท่านั้น</div></div></div>
<script>
const $=id=>document.getElementById(id);
async function post(p){await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});tick()}
$('bref').onclick=()=>post('/api/setref');$('bcal').onclick=()=>post('/api/calibrate');$('bfeed').onclick=()=>post('/api/feed');$('bline').onclick=()=>post('/api/feed_line');$('brel').onclick=()=>post('/api/release');
$('bquit').onclick=async()=>{if(!confirm('ปิดโปรแกรม? (ปล่อย Cylinder C และปิดกล้องให้เรียบร้อย)'))return;
 await fetch('/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});$('msg').textContent='ปิดโปรแกรมแล้ว — ปิดแท็บนี้ได้'};
async function tick(){try{const s=await(await fetch('/api/state',{cache:'no-store'})).json();
$('msg').textContent=s.msg;for(const b of['bref','bcal','bfeed','bline'])$(b).disabled=s.busy;
const ppp=24/s.mm_per_pulse;$('info').innerHTML=`<div>ความเหมือนแม่แบบ: หลุม <b>${s.score_pocket??'-'}</b> · รูสเตอร์ <b>${s.score_holes??'-'}</b> <span class="k">(1 = ตรงเป๊ะ · หลุมต่ำกว่า 0.5 จะหยุด)</span></div><div>Cylinder C <b class="${s.cyl_held?'o':'g'}">${s.cyl_held?'กดค้าง · ปล่อยเองใน '+s.idle_left.toFixed(0)+' วิ':'ปล่อยอยู่'}</b></div><div>mm/พัลส์ <b class="g">${s.mm_per_pulse.toFixed(5)}</b> <span class="k">(${s.mm_per_pulse_src})</span></div>
<div>พัลส์ต่อหลุม 24 mm <b class="g">${ppp.toFixed(2)}</b> · roller D ใช้งาน <b>${(s.mm_per_pulse*800/Math.PI).toFixed(2)}</b> mm</div>
<div>รูสเตอร์ <b>${s.hole_px?s.hole_px.toFixed(1):'-'}</b> px = 4 mm · จุดอ้างอิง y=<b>${s.ref_y??'-'}</b> · ทิศเทป <b>${s.direction==null?'ยังไม่รู้':(s.direction>0?'ลง':'ขึ้น')}</b></div>`;
$('rows').innerHTML=s.results.slice().reverse().map(r=>`<tr><td>${r.i}</td><td>${r.t}</td><td>${r.pulses}</td><td>${r.off_px}</td><td class="${Math.abs(r.off_mm)>0.3?'o':'g'}">${r.off_mm.toFixed(2)}</td><td>${r.travel_mm.toFixed(2)}</td></tr>`).join('')}catch(e){}}
setInterval(()=>{$('cam').src='/frame.jpg?'+Date.now()},400);setInterval(tick,700);tick();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif path == "/frame.jpg":
            jpg = annotated_jpeg()
            self._send(200, jpg, "image/jpeg") if jpg else self._send(503, b"", "text/plain")
        elif path == "/api/state":
            with lock:
                s = dict(state)
            s["cyl_held"] = holder.engaged
            s["idle_left"] = max(0.0, HOLD_IDLE_S - (time.time() - holder.last_use)) if holder.engaged else 0
            body = json.dumps(s, ensure_ascii=False, default=float)   # กันชนิด numpy หลุดมาอีก
            self._send(200, body.encode(), "application/json")
        else:
            self._send(404, b"", "text/plain")

    def do_POST(self):
        # สั่งฮาร์ดแวร์ได้เฉพาะจากหน้านี้เอง (กันเว็บอื่นยิงข้ามมา)
        origin = self.headers.get("Origin", "")
        if origin not in ("", f"http://{HOST}:{PORT}") or "json" not in self.headers.get("Content-Type", ""):
            return self._send(403, b"", "text/plain")
        if self.path == "/api/shutdown":
            # ปิดอย่างเรียบร้อยโดยไม่พึ่ง Ctrl+C (เคยเจอ 25 ก.ย.: เปิดจากเชลล์ที่ปิดรับ Ctrl+C ไว้
            # โปรแกรมรับค่านั้นติดมา กด Ctrl+C ไม่มีผล ต้องบังคับปิดจนกล้องค้าง)
            self._send(200, b"{}", "application/json")
            threading.Thread(target=SERVER["srv"].shutdown, daemon=True).start()
            return
        jobs = {"/api/setref": job_setref, "/api/calibrate": job_calibrate, "/api/feed": job_feed,
                "/api/feed_line": job_feed_to_line, "/api/release": job_release}
        fn = jobs.get(self.path)
        if not fn:
            return self._send(404, b"", "text/plain")
        ok = run_job(fn)
        self._send(200 if ok else 409, b"{}", "application/json")

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exposure-us", type=float, default=None,
                    help="ค่าเริ่มต้นอ่านจาก cam_settings.json")
    args = ap.parse_args()
    cs = json.load(open(os.path.join(HERE, "cam_settings.json"), encoding="utf-8"))
    exp = args.exposure_us or cs.get("exposure_us", 100000)
    cam_t = threading.Thread(target=camera_loop, args=(exp, cs.get("gain_db", 0.0)))
    cam_t.start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    SERVER["srv"] = srv
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nกำลังปิด...", flush=True)
    finally:
        srv.server_close()
        holder.release("ปิดโปรแกรม")
        stop_evt.set()
        cam_t.join(timeout=10)   # ให้กล้องปิดเองในเธรดของมัน ห้ามทิ้งกลางคัน


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    main()
