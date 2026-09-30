"""ถ่ายภาพจากกล้อง HIKROBOT -> ครอป ROI -> อ่านตัวอักษรด้วย PaddleOCR

ต่อยอดจากโค้ดที่พี่เลี้ยงส่งมาใน Teams (22 ก.ย. 2569) — ส่วน OCR เหมือนเดิมทุกบรรทัด

วิธีใช้ (รันด้วย venv ของ OCR):
    .venv-ocr\\Scripts\\python.exe ocr\\ocr_roi.py --select        # ครั้งแรก: ลากกรอบ ROI แล้วกด Enter
    .venv-ocr\\Scripts\\python.exe ocr\\ocr_roi.py                 # ครั้งต่อไป: ใช้กรอบเดิมที่บันทึกไว้
    .venv-ocr\\Scripts\\python.exe ocr\\ocr_roi.py --image a.png   # ทดสอบกับไฟล์รูป ไม่ใช้กล้อง

ตัวเลือกกล้อง: --exposure 20000 (ไมโครวินาที)  --gain 0 (dB)
"""
import argparse
import json
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
ROI_FILE = HERE / "roi.json"          # เก็บกรอบ ROI ที่เลือกไว้
ROI_IMAGE = HERE / "temp_roi.png"     # ชื่อเดียวกับโค้ดของพี่เลี้ยง
FULL_IMAGE = HERE / "last_frame.png"


def get_frame(args):
    if args.image:
        img = cv2.imread(args.image, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise SystemExit(f"เปิดรูปไม่ได้: {args.image}")
        return img
    from hik_camera import HikCamera
    saved = HERE / "cam_settings.json"   # ค่าที่บันทึกจาก focus_helper.py
    if args.exposure is None and saved.exists():
        s = json.loads(saved.read_text(encoding="utf-8"))
        args.exposure, args.gain = s["exposure_us"], s.get("gain_db", args.gain)
        print(f"ใช้ค่ากล้องจาก {saved.name}: exposure {args.exposure} us, gain {args.gain} dB")
    with HikCamera(exposure_us=args.exposure, gain_db=args.gain) as cam:
        cam.grab()          # ทิ้งภาพแรก เผื่อค่า exposure ใหม่ยังไม่มีผล
        return cam.grab()


def select_roi(img):
    """ให้ผู้ใช้ลากกรอบบนภาพ (ย่อภาพให้พอดีจอก่อน แล้วแปลงพิกัดกลับ)"""
    scale = min(1.0, 1280 / img.shape[1], 800 / img.shape[0])
    small = cv2.resize(img, None, fx=scale, fy=scale)
    # ชื่อหน้าต่าง OpenCV ต้องเป็นภาษาอังกฤษ (ภาษาไทยจะขึ้นเป็นตัวเพี้ยนบน Windows)
    x, y, w, h = cv2.selectROI("Drag a box around the text, then press ENTER (c = cancel)",
                               small, showCrosshair=True)
    cv2.destroyAllWindows()
    if w == 0 or h == 0:
        raise SystemExit("ไม่ได้เลือกกรอบ")
    roi = [int(v / scale) for v in (x, y, w, h)]
    ROI_FILE.write_text(json.dumps({"x": roi[0], "y": roi[1], "w": roi[2], "h": roi[3]}), encoding="utf-8")
    print(f"บันทึก ROI {roi} ลง {ROI_FILE.name}")
    return roi


def load_roi(img):
    if not ROI_FILE.exists():
        print("ยังไม่มี ROI ใช้ภาพเต็มไปก่อน (รันด้วย --select เพื่อเลือกกรอบ)")
        return [0, 0, img.shape[1], img.shape[0]]
    r = json.loads(ROI_FILE.read_text(encoding="utf-8"))
    return [r["x"], r["y"], r["w"], r["h"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="ใช้ไฟล์รูปแทนกล้อง")
    ap.add_argument("--select", action="store_true", help="เลือกกรอบ ROI ใหม่")
    ap.add_argument("--exposure", type=float, help="เวลาเปิดรับแสง (ไมโครวินาที)")
    ap.add_argument("--gain", type=float, help="gain (dB)")
    ap.add_argument("--lang", default="en", help="en หรือ th")
    ap.add_argument("--rotate", type=int, default=180, choices=[0, 90, 180, 270],
                    help="หมุน ROI ก่อน OCR (ขาจับกล้องปัจจุบันทำให้ตัวหนังสือกลับหัว = 180)")
    args = ap.parse_args()

    img = get_frame(args)
    cv2.imwrite(str(FULL_IMAGE), img)
    print(f"ภาพ {img.shape[1]}x{img.shape[0]}  ความสว่างเฉลี่ย {img.mean():.0f}/255")

    x, y, w, h = select_roi(img) if args.select else load_roi(img)
    roi = img[y:y + h, x:x + w]
    rot = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    if args.rotate:
        roi = cv2.rotate(roi, rot[args.rotate])
    cv2.imwrite(str(ROI_IMAGE), roi)

    # torch (มากับ EasyOCR) ต้องโหลดก่อน paddle ไม่งั้น DLL ชนกัน → WinError 127 (ดู app_vision_ocr.py)
    try:
        import torch  # noqa: F401
    except ImportError:
        pass

    # ---------- ส่วนนี้คือโค้ดของพี่เลี้ยง ----------
    import paddle
    from paddleocr import PaddleOCR
    device = "gpu:0" if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() else "cpu"
    print(f"รันบน {device}")
    t0 = time.time()
    ocr = PaddleOCR(
        lang=args.lang,  # ภาษาไทยใช้ 'th'
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,  # เพิ่มเอง: Paddle 3.3.1 บน CPU พังตอนเปิด oneDNN (NotImplementedError)
        device=device,        # เพิ่มเอง: GPU เร็วกว่า CPU ~100 เท่า (46 ms vs 4.7 s)
    )
    t1 = time.time()
    result = ocr.predict(str(ROI_IMAGE))
    t2 = time.time()

    found = False
    for res in result:
        for t, s in zip(res["rec_texts"], res["rec_scores"]):
            print(f"{t} (conf: {s:.2f})")
            found = True
    # ---------------------------------------------
    if not found:
        print("ไม่เจอตัวอักษรใน ROI — เช็กโฟกัส ความสว่าง และขนาดกรอบ")
    # ครั้งแรกหลังโหลดโมเดลจะช้ากว่าปกติ (GPU: ~420 ms) ครั้งต่อไป ~46 ms
    print(f"โหลดโมเดล {t1 - t0:.1f} s · อ่านภาพ {1000 * (t2 - t1):.0f} ms (ครั้งแรก รวม warm-up)")


if __name__ == "__main__":
    main()
