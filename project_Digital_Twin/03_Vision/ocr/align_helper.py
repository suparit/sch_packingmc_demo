r"""หน้าต่างช่วยจัดกล้อง HIKROBOT ให้ตั้งฉากกับชิ้นงาน — เทียบความคม 4 มุม + กลางภาพ

ทำไมต้องมีตัวนี้แยกจาก focus_helper.py: focus_helper วัดความคมแค่กลางภาพ ใช้หมุนโฟกัสได้
แต่บอกไม่ได้ว่ากล้องเอียงไหม ถ้ากล้องเอียง ด้านที่ใกล้เลนส์กับด้านที่ไกลจะคมไม่เท่ากัน
(22 ก.ย. เคยวัดได้ซ้ายบน 323 · ขวาล่าง 17 ต่างกันเกือบ 20 เท่า)

ขั้นตอน:
  1. วางกระดาษที่มีตัวหนังสือหรือลายตารางให้เต็มภาพ (ทุกกรอบต้องมีลาย ไม่งั้นค่าความคมไม่มีความหมาย)
  2. หมุนโฟกัสให้กรอบ P (สีม่วง บนตัวชิ้นงาน) ได้ค่าใกล้ peak ที่สุด — ไม่ใช่กรอบ C
     (กรอบ P วางตามจุดอ้างอิงใน ocr_config.json ต้อง --set-center ก่อนถ้าย้ายกล้อง)
  3. ปรับขาจับจนค่า L/R และ T/B ใกล้ 1.00 (เขียว = ต่างกันไม่เกิน 1.5 เท่า)
     ใช้เส้นตารางเทียบกับขอบเทปเพื่อหมุนให้ภาพไม่เอียง
  4. เช็กบรรทัด SIZE ต้องเป็น 2592x1944 ถ้าเป็นสีแดง = ROI ของเซนเซอร์ถูกตัดไว้ใน MVS

ปิด: q หรือ Esc (ปิดกล้องถูกวิธี) · r = รีเซ็ตค่าเฉลี่ย · ไม่บันทึกค่าใดๆ ลงไฟล์

รันด้วย venv ของกล้องเดิม (มี OpenCV แบบเปิดหน้าต่างได้) ไม่ใช่ .venv-ocr:
  cd 03_Vision ; .venv\Scripts\python.exe ocr\align_helper.py
"""
import json
from pathlib import Path

import cv2
import numpy as np

from hik_camera import HikCamera  # ต้อง import ก่อน เพราะตั้ง path ของ MVS ให้

FULL_SIZE = (2592, 1944)
MAX_EXPOSURE_US = 200000  # ภาพสดต้องขยับตามทันตอนปรับขาจับ ค่า exposure จริงค่อยจูนทีหลัง
VIEW_W, VIEW_H = 1296, 972
OK_RATIO = 1.5


def part_center():
    """จุดอ้างอิงชิ้นงานจาก ocr_config.json (ตั้งด้วย app_vision_ocr.py --set-center) — ไม่มีคืน None"""
    try:
        c = json.loads((Path(__file__).resolve().parent / "ocr_config.json").read_text(encoding="utf-8"))
        return tuple(int(v) for v in c["expected_center"])
    except Exception:
        return None


def zone_boxes(w, h):
    """กรอบ 5 จุด: มุมทั้งสี่ (เว้นขอบ 5%) + กลาง ขนาด 1/5 ของภาพ + กรอบ P บนตัวชิ้นงาน

    กรอบ P ใช้หมุนโฟกัส (24 ก.ย.): ชิ้นงานไม่ได้อยู่กลางภาพ กรอบ C จึงมีพื้นหลังปนครึ่งหนึ่ง
    หมุนหาค่าสูงสุดของ C แล้วโฟกัสไปลงที่พื้นรอบๆ ไม่ใช่ตัวหนังสือ — OCR ตกจาก 10/10 เหลือ 0/10
    """
    bw, bh = w // 5, h // 5
    mx, my = int(w * 0.05), int(h * 0.05)
    boxes = {
        "TL": (mx, my), "TR": (w - mx - bw, my),
        "BL": (mx, h - my - bh), "BR": (w - mx - bw, h - my - bh),
        "C": ((w - bw) // 2, (h - bh) // 2),
    }
    pc = part_center()
    if pc:
        pw, ph = w // 8, h // 12   # เล็กพอให้อยู่บนหน้าชิ้นงาน (รัศมี ~250 px) ครอบบรรทัดตัวหนังสือกลางชิ้น
        boxes["P"] = (max(0, pc[0] - pw // 2), max(0, pc[1] - ph // 2), pw, ph)
    return boxes, bw, bh


def main():
    cam = HikCamera(gain_db=0.0).open()
    c = cam.cam
    c.MV_CC_SetEnumValue("GainAuto", 0)
    c.MV_CC_SetIntValue("AutoExposureTimeUpperLimit", MAX_EXPOSURE_US)
    c.MV_CC_SetEnumValue("ExposureAuto", 2)

    hist = {}
    win = "Align helper  (q = quit, r = reset)"
    try:
        # สร้างหน้าต่างใน try เพื่อให้ finally ปิดกล้องเสมอ — .venv-ocr มี OpenCV แบบ headless
        # เปิดหน้าต่างไม่ได้ ถ้าพังตรงนี้โดยไม่ปิดกล้อง กล้องจะค้าง (ต้องรันด้วย 03_Vision\.venv)
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, VIEW_W, VIEW_H)
        while True:
            img = cam.grab()
            h, w = img.shape
            boxes, bw, bh = zone_boxes(w, h)
            sharp = {}
            size = {k: (b[2], b[3]) if len(b) == 4 else (bw, bh) for k, b in boxes.items()}
            for k, b in boxes.items():
                x, y = b[0], b[1]
                zw, zh = size[k]
                v = cv2.Laplacian(img[y:y + zh, x:x + zw], cv2.CV_64F).var()
                hist[k] = (hist.get(k, []) + [v])[-5:]
                sharp[k] = float(np.mean(hist[k]))

            left, right = (sharp["TL"] + sharp["BL"]) / 2, (sharp["TR"] + sharp["BR"]) / 2
            top, bottom = (sharp["TL"] + sharp["TR"]) / 2, (sharp["BL"] + sharp["BR"]) / 2
            lr = left / max(right, 1e-6)
            tb = top / max(bottom, 1e-6)

            view = cv2.cvtColor(cv2.resize(img, (VIEW_W, VIEW_H)), cv2.COLOR_GRAY2BGR)
            s = VIEW_W / w
            # เส้นตาราง 8x6 + กากบาทกลาง ไว้เทียบกับขอบเทปว่าภาพหมุนเอียงไหม
            for i in range(1, 8):
                cv2.line(view, (VIEW_W * i // 8, 0), (VIEW_W * i // 8, VIEW_H), (90, 90, 90), 1)
            for i in range(1, 6):
                cv2.line(view, (0, VIEW_H * i // 6), (VIEW_W, VIEW_H * i // 6), (90, 90, 90), 1)
            cv2.line(view, (VIEW_W // 2, 0), (VIEW_W // 2, VIEW_H), (0, 200, 255), 1)
            cv2.line(view, (0, VIEW_H // 2), (VIEW_W, VIEW_H // 2), (0, 200, 255), 1)

            best = max(v for k, v in sharp.items() if k != "P") or 1.0
            for k, b in boxes.items():
                x, y = b[0], b[1]
                zw, zh = size[k]
                p1, p2 = (int(x * s), int(y * s)), (int((x + zw) * s), int((y + zh) * s))
                if k == "P":
                    # กรอบบนตัวชิ้นงาน — ใช้ค่านี้หมุนโฟกัส (PEAK = ค่าสูงสุดที่เคยได้ตั้งแต่เปิด/กด r)
                    peak_p = max(hist.get("P_peak", [0])[0], sharp[k])
                    hist["P_peak"] = [peak_p]
                    col = (255, 0, 255)
                    cv2.rectangle(view, p1, p2, col, 3)
                    cv2.putText(view, f"P {sharp[k]:.0f} (peak {peak_p:.0f})", (p1[0], p1[1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, col, 2)
                    continue
                frac = sharp[k] / best
                col = (0, 200, 0) if frac >= 1 / OK_RATIO else (0, 0, 255)
                cv2.rectangle(view, p1, p2, col, 2)
                cv2.putText(view, f"{k} {sharp[k]:.0f}", (p1[0] + 6, p1[1] + 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)

            size_ok = (w, h) == FULL_SIZE
            mean = float(img.mean())
            cv2.rectangle(view, (0, VIEW_H - 110), (VIEW_W, VIEW_H), (20, 20, 20), -1)
            cv2.putText(view, f"SIZE {w}x{h}" + ("" if size_ok else "  <- NOT FULL SENSOR! fix ROI in MVS"),
                        (16, VIEW_H - 75), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 200, 0) if size_ok else (0, 0, 255), 2)
            cv2.putText(view, f"BRIGHT {mean:.0f}/255", (820, VIEW_H - 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
            for i, (name, r, a, b) in enumerate((("L/R", lr, "LEFT", "RIGHT"), ("T/B", tb, "TOP", "BOTTOM"))):
                ok = 1 / OK_RATIO <= r <= OK_RATIO
                hint = "ok" if ok else f"{a if r > 1 else b} is sharper"
                cv2.putText(view, f"{name} {r:5.2f}  {hint}", (16 + i * 620, VIEW_H - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 0) if ok else (0, 0, 255), 2)
            cv2.imshow(win, view)

            k = cv2.waitKey(1) & 0xFF
            if k == ord("r"):
                hist = {}
            if k in (ord("q"), 27) or cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
    except KeyboardInterrupt:
        pass
    finally:
        c.MV_CC_SetEnumValue("ExposureAuto", 0)
        cam.close()
        cv2.destroyAllWindows()
        print("ปิดกล้องแล้ว")


if __name__ == "__main__":
    main()
