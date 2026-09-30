r"""หน้าต่างช่วยวางชิ้นงานให้ตรงจุดที่กล้องตรวจ (28 ก.ย. 2569)

ใช้ตอนเลื่อนเทปด้วยมือก่อนจูนกล้อง (exposure_sweep.py) — ถ้าชิ้นงานไม่อยู่ตรงจุดตรวจ ผลจูนใช้ไม่ได้
(28 ก.ย. บ่าย: เทปค้างครึ่งหลุม กรอบตกร่องระหว่างหลุม อ่านได้ 0/6 ทุก exposure)

เห็นอะไร:
  วงเขียว + กากบาท = จุดที่กล้องตรวจ (expected_center ใน ocr_config.json)
  วงเหลือง         = ชิ้นงานที่หาเจอ (ฟังก์ชันเดียวกับแอปตรวจจริง) + เส้นไปหาจุดตรวจ
  บรรทัดบน         = ห่างกี่ mm · OK (เขียว) เมื่อห่างไม่เกิน 1.5 mm
  เส้นขอบกรอบส้ม   = ช่วงที่แอปครอปไปอ่าน OCR

ปิด: q หรือ Esc (ปิดกล้องถูกวิธี) · +/- = ปรับ exposure (ดูภาพ ไม่บันทึก)
ต้องปิดระบบก่อน (STOP.bat) — กล้องเปิดได้ทีละโปรแกรม

รันด้วย venv ที่เปิดหน้าต่างได้ (.venv-ocr ไม่มี GUI):
  cd 03_Vision ; .venv\Scripts\python.exe ocr\position_helper.py --exposure-ms 4
"""
import argparse

import cv2
import numpy as np

from hik_camera import HikCamera  # ต้อง import ก่อน เพราะตั้ง path ของ MVS ให้
import app_vision_ocr as app      # ใช้ find_part / crop scale ตัวเดียวกับแอปจริง

PX_PER_MM = 44.57        # ไม้บรรทัดรูสเตอร์ 28 ก.ย. (4 mm = 178.3 px)
OK_MM = 1.5
SCALE = 0.4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exposure-ms", type=float, default=4.0)
    args = ap.parse_args()

    cfg = app.CONFIG
    ac = cfg.get("auto_center", {})
    target = tuple(int(v) for v in cfg["expected_center"])
    crop_scale = float(ac.get("crop_scale", 2.4))
    exp_ms = args.exposure_ms
    cam = HikCamera(exposure_us=exp_ms * 1000, gain_db=0.0, pixel_format=cfg.get("pixel_format", "mono8")).open()
    win = "position helper - q/Esc = close"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
    try:
        while True:
            raw = cam.grab().astype(np.float32)
            lo, hi = np.percentile(raw, [2, 98])
            frame = np.clip((raw - lo) * 255.0 / max(1.0, hi - lo), 0, 255).astype(np.uint8)
            part = app.find_part(frame, target)
            if part and np.hypot(part[0] - target[0], part[1] - target[1]) > float(ac.get("max_jump_px", 520)):
                part = None

            vis = cv2.cvtColor(cv2.resize(frame, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
            s = lambda v: int(round(v * SCALE))
            tx, ty = s(target[0]), s(target[1])
            cv2.circle(vis, (tx, ty), s(360), (0, 200, 0), 2)
            cv2.drawMarker(vis, (tx, ty), (0, 200, 0), cv2.MARKER_CROSS, 40, 2)
            if part:
                px, py, pr = part
                half = pr * crop_scale / 2
                cv2.rectangle(vis, (s(px - half), s(py - half)), (s(px + half), s(py + half)), (0, 140, 255), 1)
                cv2.circle(vis, (s(px), s(py)), s(pr), (0, 230, 255), 2)
                cv2.line(vis, (s(px), s(py)), (tx, ty), (0, 230, 255), 2)
                dx, dy = (px - target[0]) / PX_PER_MM, (py - target[1]) / PX_PER_MM
                dist = float(np.hypot(dx, dy))
                ok = dist <= OK_MM
                where = f"part {abs(dy):.1f} mm {'BELOW' if dy > 0 else 'ABOVE'} target, {abs(dx):.1f} mm {'right' if dx > 0 else 'left'}"
                msg, color = (f"OK  ({dist:.1f} mm)", (0, 200, 0)) if ok else (f"MOVE TAPE: {where}", (0, 0, 255))
            else:
                msg, color = "NO PART FOUND near target", (0, 0, 255)
            cv2.rectangle(vis, (0, 0), (vis.shape[1], 64), (0, 0, 0), -1)
            cv2.putText(vis, msg, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
            cv2.putText(vis, f"exposure {exp_ms:g} ms  raw mean {raw.mean():.0f}/4095  (+/- to change, q = close)",
                        (10, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
            cv2.imshow(win, vis)
            k = cv2.waitKey(30) & 0xFF
            if k in (ord("q"), 27) or cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
            if k in (ord("+"), ord("=")) or k in (ord("-"), ord("_")):
                exp_ms = max(0.5, exp_ms * (1.25 if k in (ord("+"), ord("=")) else 0.8))
                cam.close()
                cam = HikCamera(exposure_us=exp_ms * 1000, gain_db=0.0, pixel_format=cfg.get("pixel_format", "mono8")).open()
    finally:
        cam.close()
        cv2.destroyAllWindows()
        print("ปิดกล้องแล้ว")


if __name__ == "__main__":
    main()
