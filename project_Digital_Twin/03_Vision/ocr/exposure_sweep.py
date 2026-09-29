r"""ไล่ค่า exposure หลายระดับ แล้ววัดผล OCR ด้วยขั้นตอนเดียวกับ app_vision_ocr.py

ทำไมต้องมี: 23 ก.ย. เราตั้ง exposure 40 ms ภาพมืด เพราะเข้าใจผิดว่าตัวหนังสือเป็นรอยนูนต้องพึ่งเงา
ของจริงเป็น laser mark และพี่เลี้ยงสั่ง "Exposure มากที่สุด Gain น้อยที่สุด" (ภาพพี่ 500 ms)
สคริปต์นี้วัดทุกระดับในรอบเดียว ภายใต้แสงห้องเดียวกัน ผลจึงเทียบกันได้ (บทเรียน 92% เช้า vs 0% บ่าย)

ใช้ฟังก์ชันหาชิ้นงาน/ครอป/อ่านของ app_vision_ocr.py ตรงๆ ผลที่ได้จึงตรงกับที่แอปจริงจะเห็น

ตัวอย่าง:
  cd 03_Vision
  .venv-ocr\Scripts\python.exe ocr\exposure_sweep.py --label out-of-pocket
  .venv-ocr\Scripts\python.exe ocr\exposure_sweep.py --label in-pocket --exposures 100 200 500

ผลลัพธ์: ตารางบนจอ + ocr\sweep\<label>_<เวลา>.csv + ภาพ ROI ต่อระดับ exposure
หยุดกลางคัน: Ctrl+C (ปิดกล้องถูกวิธี)
"""
import argparse
import csv
import time
from pathlib import Path

# torch ต้องโหลดก่อน paddle (ดู app_vision_ocr.py) — ต้องอยู่ก่อน import app_vision_ocr ด้วย
try:
    import torch  # noqa: F401
except ImportError:
    pass

import cv2
import numpy as np

from hik_camera import HikCamera  # ตั้ง path ของ MVS ให้
from app_vision_ocr import CONFIG, ROTATE, crop_centered, find_part, normalize, read_lines

HERE = Path(__file__).resolve().parent
# รหัสรุ่นที่นับว่าอ่านถูก = ช่อง PART NR ใน ocr_config.json (28 ก.ย. 2569: รับหลายรุ่นผ่าน "patterns")
_part = next((f for f in CONFIG["fields"] if f["name"] == "PART NR"), {"pattern": "PART-MODEL-A"})
TARGETS = [normalize(p) for p in (_part.get("patterns") or [_part["pattern"]])]
TARGET = TARGETS[0]
# ตัวที่ OCR สับสนกันบ่อย — ภาพของพี่เลี้ยงเองยังอ่านได้ RE1OO-1-10M (0 เป็น O)
LOOKALIKE = str.maketrans({"O": "0", "I": "1"})


def save_png(path, img):
    """cv2.imwrite เขียนไฟล์ไม่ได้เงียบๆ เมื่อ path มีอักษรไทย (สหกิจ) — เข้ารหัสในหน่วยความจำแล้วเขียนเอง"""
    ok, buf = cv2.imencode(".png", img)
    if ok:
        Path(path).write_bytes(buf.tobytes())


def to_8bit(avg, pixel_format):
    """แปลงภาพเฉลี่ยเป็น 8 บิตแบบเดียวกับแอป (Mono12 = ยืดคอนทราสต์ percentile)"""
    if pixel_format == "mono12":
        lo_p, hi_p = CONFIG.get("stretch_percentiles", [2, 98])
        lo, hi = np.percentile(avg, lo_p), np.percentile(avg, hi_p)
        return np.clip((avg - lo) * 255.0 / max(1.0, hi - lo), 0, 255).astype(np.uint8)
    return avg.astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exposures", type=float, nargs="+", default=[40, 100, 200, 350, 500],
                    help="ค่า exposure ที่จะไล่ (มิลลิวินาที)")
    ap.add_argument("--frames", type=int, default=10, help="จำนวนครั้งที่อ่านต่อหนึ่งระดับ")
    ap.add_argument("--avg", type=int, default=4, help="เฉลี่ยกี่เฟรมก่อนอ่านหนึ่งครั้ง (แอปใช้ 16)")
    ap.add_argument("--gain", type=float, default=0.0)
    ap.add_argument("--label", default="test", help="ชื่อสภาพการทดลอง เช่น out-of-pocket / in-pocket")
    ap.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], default=None,
                    help="หมุนภาพก่อนอ่าน (ค่าเริ่มต้นใช้ค่าใน ocr_config.json)")
    args = ap.parse_args()

    import paddle
    from paddleocr import PaddleOCR
    device = "gpu:0" if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() else "cpu"
    print(f"โหลดโมเดล OCR บน {device} ...")
    ocr = PaddleOCR(lang="en", use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_textline_orientation=False, enable_mkldnn=False, device=device)

    out_dir = HERE / "sweep"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"{args.label}_{stamp}.csv"
    pixel_format = CONFIG.get("pixel_format", "mono8")
    rot_deg = CONFIG["rotate"] if args.rotate is None else args.rotate
    rot = ROTATE[rot_deg]
    crop_scale = float(CONFIG.get("auto_center", {}).get("crop_scale", 2.7))

    rows, summary = [], []
    cam = HikCamera(exposure_us=args.exposures[0] * 1000, gain_db=args.gain,
                    pixel_format=pixel_format).open()
    c = cam.cam
    try:
        for exp_ms in args.exposures:
            # หยุด-เริ่มถ่ายใหม่ทุกครั้งที่เปลี่ยน exposure เพื่อล้างบัฟเฟอร์ของกล้อง
            # กับดัก (24 ก.ย.): ทิ้งแค่ 2 เฟรมไม่พอ ตอน exposure สั้นกล้องค้างเฟรมเก่าไว้หลายเฟรม
            # ระดับที่สองของแต่ละรอบเลยวัดได้ความสว่างเท่าระดับแรก (20 ms = 193, 40 ms = 194)
            c.MV_CC_StopGrabbing()
            c.MV_CC_SetEnumValue("ExposureAuto", 0)
            c.MV_CC_SetFloatValue("ExposureTime", float(exp_ms * 1000))
            c.MV_CC_StartGrabbing()
            timeout = int(exp_ms * 2 + 2000)
            for _ in range(2):  # ทิ้งเฟรมแรกหลังเริ่มถ่ายใหม่
                cam.grab(timeout)
            raw = cam.grab(timeout)
            raw_max = 4095 if pixel_format == "mono12" else 255
            sat = float((raw >= raw_max).mean() * 100)

            exact = lenient = found_part = 0
            confs, texts = [], []
            for i in range(args.frames):
                acc = cam.grab(timeout).astype(np.float32)
                for _ in range(args.avg - 1):
                    acc += cam.grab(timeout)
                frame = to_8bit(acc / args.avg, pixel_format)
                part = find_part(frame, tuple(CONFIG.get("expected_center") or (frame.shape[1] / 2, frame.shape[0] / 2)))
                if part:
                    found_part += 1
                    roi = crop_centered(frame, part, crop_scale)
                else:
                    roi = frame
                if rot is not None:
                    roi = cv2.rotate(roi, rot)
                lines = read_lines(ocr, roi)
                # บรรทัดที่หน้าตาใกล้รหัสรุ่นที่สุด (เริ่มด้วย RE/TE/LE... + ตัวเลข) เพื่อดูว่าผิดตรงไหน
                best = max(lines, key=lambda l: max(sum(a == b for a, b in zip(normalize(l[0]), t)) for t in TARGETS),
                           default=None)
                text, conf = (best[0], best[1]) if best else ("", 0.0)
                n = normalize(text)
                hit = any(t in n for t in TARGETS)
                hit_l = any(t in n.translate(LOOKALIKE) for t in TARGETS)
                exact += hit
                lenient += hit_l
                confs.append(conf)
                texts.append(text)
                rows.append({"label": args.label, "exposure_ms": exp_ms, "gain_db": args.gain, "i": i,
                             "raw_mean": round(float(raw.mean()), 1), "saturated_pct": round(sat, 2),
                             "roi_mean": round(float(roi.mean()), 1), "part_found": bool(part),
                             "best_line": text, "conf": round(conf, 3), "exact": hit, "lenient": hit_l,
                             "all_lines": " | ".join(t for t, _, _ in lines)})
                if i == 0:
                    save_png(out_dir / f"{args.label}_{stamp}_{int(exp_ms)}ms.png", roi)
            common = max(set(texts), key=texts.count) if texts else ""
            summary.append((exp_ms, float(raw.mean()), sat, found_part, exact, lenient,
                            float(np.mean(confs)) if confs else 0.0, common))
            print(f"  {exp_ms:6.0f} ms  เสร็จ  ถูกเป๊ะ {exact}/{args.frames}  ยอม O/0 {lenient}/{args.frames}"
                  f"  อ่านบ่อยสุด '{common}'")
    except KeyboardInterrupt:
        print("หยุดกลางคัน — บันทึกเท่าที่วัดได้")
    finally:
        cam.close()

    if rows:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    print(f"\nสภาพ: {args.label} · หมุน {rot_deg}° · gain {args.gain} dB · เฉลี่ย {args.avg} เฟรม · {args.frames} ครั้งต่อระดับ · "
          f"{time.strftime('%H:%M')}")
    print(f"{'Exposure':>9} {'ภาพดิบ':>8} {'อิ่มตัว%':>8} {'เจอชิ้นงาน':>10} {'ถูกเป๊ะ':>8} {'ยอม O/0':>8} "
          f"{'conf':>6}  อ่านได้บ่อยสุด")
    for exp_ms, rmean, sat, fp, ex, le, cf, common in summary:
        print(f"{exp_ms:7.0f}ms {rmean:8.0f} {sat:8.2f} {fp:>6}/{args.frames:<3} {ex:>4}/{args.frames:<3} "
              f"{le:>4}/{args.frames:<3} {cf:6.2f}  {common}")
    print(f"\nบันทึก: {csv_path}")


if __name__ == "__main__":
    main()
