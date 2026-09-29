"""หน้าต่างช่วยปรับเลนส์กล้อง HIKROBOT — ดูภาพสด + ค่าความสว่าง + ค่าความคม

ขั้นตอน:
  1. เปิดวงรูรับแสง (aperture) ให้กว้างจนแถบ BRIGHT เป็นสีเขียว
  2. หมุนวงโฟกัสช้าๆ ดูค่า SHARP ให้สูงที่สุด (PEAK คือค่าสูงสุดที่เคยได้)
     พอหมุนเลยจุดคม ค่าจะตก ให้หมุนกลับมาที่ค่าใกล้ PEAK
  3. กด s เพื่อบันทึกค่า exposure ลง cam_settings.json แล้วปิด (q = ปิดโดยไม่บันทึก)

ความคมวัดจากกรอบสีเหลืองกลางภาพ — วางตัวหนังสือไว้ในกรอบนี้
"""
import json
import time
from pathlib import Path

import cv2
import numpy as np

from hik_camera import HikCamera  # ต้อง import ก่อน เพราะตั้ง path ของ MVS ให้
import MvCameraControl_class as M  # noqa: E402

SETTINGS = Path(__file__).resolve().parent / "cam_settings.json"
MAX_EXPOSURE_US = 100000  # เกิน 0.1 วินาที ภาพจะเบลอเวลาของขยับ


def main():
    cam = HikCamera().open()
    c = cam.cam
    c.MV_CC_SetEnumValue("GainAuto", 0)
    c.MV_CC_SetFloatValue("Gain", 0.0)
    c.MV_CC_SetIntValue("AutoExposureTimeUpperLimit", MAX_EXPOSURE_US)
    c.MV_CC_SetEnumValue("ExposureAuto", 2)  # ให้กล้องปรับ exposure ตามแสงเอง
    fv = M.MVCC_FLOATVALUE()

    peak, hist = 0.0, []
    win = "Focus helper  (s = save, q = quit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 1296, 972)
    saved = False
    try:
        while True:
            img = cam.grab()
            h, w = img.shape
            cx, cy, bw, bh = w // 2, h // 2, w // 4, h // 4
            roi = img[cy - bh // 2:cy + bh // 2, cx - bw // 2:cx + bw // 2]
            sharp = cv2.Laplacian(roi, cv2.CV_64F).var()
            hist = (hist + [sharp])[-5:]
            sharp_s = float(np.mean(hist))  # เฉลี่ย 5 เฟรม ลดตัวเลขกระตุก
            peak = max(peak, sharp_s)
            mean = float(img.mean())
            c.MV_CC_GetFloatValue("ExposureTime", fv)
            exp = fv.fCurValue

            view = cv2.cvtColor(cv2.resize(img, (1296, 972)), cv2.COLOR_GRAY2BGR)
            s = 1296 / w
            cv2.rectangle(view, (int((cx - bw // 2) * s), int((cy - bh // 2) * s)),
                          (int((cx + bw // 2) * s), int((cy + bh // 2) * s)), (0, 220, 255), 2)
            ok_b = 90 <= mean <= 170 and exp < MAX_EXPOSURE_US * 0.95
            col_b = (0, 200, 0) if ok_b else (0, 0, 255)
            cv2.rectangle(view, (0, 0), (1296, 120), (20, 20, 20), -1)
            cv2.putText(view, f"BRIGHT {mean:5.0f}/255   exposure {exp / 1000:6.1f} ms", (16, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, col_b, 2)
            hint = "open aperture / add light" if exp >= MAX_EXPOSURE_US * 0.95 else ("ok" if ok_b else "")
            cv2.putText(view, hint, (820, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col_b, 2)
            frac = sharp_s / peak if peak else 0
            col_s = (0, 200, 0) if frac > 0.9 else (0, 200, 255)
            cv2.putText(view, f"SHARP {sharp_s:7.1f}   PEAK {peak:7.1f}", (16, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, col_s, 2)
            cv2.rectangle(view, (700, 70), (1270, 96), (80, 80, 80), 1)
            cv2.rectangle(view, (700, 70), (700 + int(570 * frac), 96), col_s, -1)
            cv2.imshow(win, view)

            k = cv2.waitKey(1) & 0xFF
            if k == ord("r"):
                peak, hist = 0.0, []
            if k in (ord("s"), ord("q"), 27):
                if k == ord("s"):
                    SETTINGS.write_text(json.dumps({"exposure_us": round(exp), "gain_db": 0.0,
                                                    "saved_at": time.strftime("%Y-%m-%d %H:%M"),
                                                    "sharpness": round(sharp_s, 1), "brightness": round(mean)}),
                                        encoding="utf-8")
                    saved = True
                break
            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        c.MV_CC_SetEnumValue("ExposureAuto", 0)
        cam.close()
        cv2.destroyAllWindows()
    print(f"บันทึกค่าลง {SETTINGS.name} แล้ว" if saved else "ปิดโดยไม่บันทึก")


if __name__ == "__main__":
    main()
