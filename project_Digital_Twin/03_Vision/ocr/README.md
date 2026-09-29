# 03_Vision/ocr — กล้องตรวจชิ้นงาน + OCR

กล้องอุตสาหกรรม USB3 (HIKROBOT MV-CE050-30UM) + PaddleOCR ตรวจชิ้นงานในหลุม carrier tape แล้วส่ง PASS / NG ให้ FSM
ใช้บนเครื่องจริงแล้ว (28 ก.ย. 2569): ตัดสินจาก **ภาพนิ่ง** · ~2 วินาที/ชิ้น · batch 4 ชิ้นผ่าน 4/4

> ฉบับย่อสำหรับ repo นี้ — ผลทดลองละเอียดทุกรอบอยู่ใน repo พัฒนาของนักศึกษา
> **ข้อความบนชิ้นงานใน `ocr_config.json` เป็นค่าตัวอย่าง** (`BRAND_TEXT`, `PART-MODEL-A/B`, `RATING_TEXT`) ต้องแก้เป็นของจริงก่อนใช้

## ภาพรวม

```
กล้อง USB3 ─▶ MVS SDK ─▶ hik_camera.py ─▶ ภาพ numpy ─▶ ครอป ROI ─▶ PaddleOCR ─▶ ตรวจ 4 ข้อ ─▶ PASS/NG ─▶ gateway (WebSocket)
             (ไดรเวอร์ผู้ผลิต)  (ตัวรับภาพ)                                                         + หน้าเว็บ :5000
```

แยกชั้นตามข้อกำหนดของพี่เลี้ยง (layer separation + vendor abstraction) — **เปลี่ยนกล้องยี่ห้ออื่น แก้แค่ `hik_camera.py`**

| ไฟล์ | หน้าที่ |
|---|---|
| `app_vision_ocr.py` | **ตัวตรวจชิ้นงานจริง** — ตรวจ 4 ข้อ → ส่ง PASS/NG ให้ FSM + หน้าเว็บแสดงผล `http://127.0.0.1:5000` |
| `hik_camera.py` | คลาส `HikCamera` เปิดกล้อง ตั้ง exposure/gain ดึงภาพเป็น numpy |
| `ocr_config.json` | ข้อความที่ต้องตรวจ (`fields`) · เกณฑ์ความมั่นใจ · การหมุนภาพ · โหมดตัดสิน (`decision_mode: snapshot`) |
| `cam_settings.json` | ค่า exposure/gain ที่ใช้ (ตอนทดสอบ = 12 ms · gain 0) |
| `ocr_roi.py` | ถ่ายภาพ → เลือกกรอบ ROI → อ่านด้วย PaddleOCR (ใช้ทดสอบ) |
| `focus_helper.py` · `align_helper.py` | ช่วยปรับโฟกัส / จัดกล้องให้ตั้งฉาก |
| `position_helper.py` · `pocket_measure.py` | ตั้งตำแหน่งหลุม / วัดว่าหลุมตรงเส้น index ไหม |
| `exposure_sweep.py` | ไล่ exposure หลายค่าแล้ววัดผล OCR → หาค่าที่เหมาะกับไฟชุดใหม่ |
| `feed_pocket_view.py` | เครื่องมือเดิมดูหลุมระหว่าง feed (**ห้ามรันพร้อมระบบหลัก**) |

## เงื่อนไขการตรวจ 4 ข้อ

| # | เงื่อนไข | วิธีตรวจ |
|---|---|---|
| 1 | มีชิ้นงานไหม | หาวงกลมตัวชิ้นงาน (Hough Circle) |
| 2 | วางถูกตำแหน่ง/ทิศไหม | อยู่ในหลุม + ทิศจากมุมบรรทัดตัวหนังสือ |
| 3 | ตัวหนังสือเห็นไหม | นับบรรทัดที่ OCR เจอ |
| 4 | อ่านออกและตรงไหม | ข้อความตรงกับ `fields` ใน `ocr_config.json` |

เหตุผล NG ที่ส่งให้ FSM: `NO PART` · `WRONG POSITION` · `TEXT NOT FOUND` · `TEXT UNREADABLE`

## ติดตั้ง

1. ลงโปรแกรม **MVS** ของผู้ผลิตกล้อง (มีไลบรารี Python `MvImport` มาด้วย)
2. สร้าง venv แยก (Paddle ใหญ่ ~1 GB):

```powershell
cd 03_Vision
python -m venv .venv-ocr
.venv-ocr\Scripts\python.exe -m pip install --only-binary=:all: paddlepaddle==3.3.1
.venv-ocr\Scripts\python.exe -m pip install --prefer-binary "paddleocr>=3.4"
.venv-ocr\Scripts\python.exe -m pip install -r requirements.txt
```

มี GPU (NVIDIA): ใช้ `paddlepaddle-gpu` แทน — อ่าน ROI จาก ~4,700 ms เหลือ ~46 ms

## ใช้งาน

```powershell
cd 03_Vision
.venv-ocr\Scripts\python.exe ocr\app_vision_ocr.py --standalone   # ดูผลอย่างเดียว (ไม่ต่อ FSM)
.venv-ocr\Scripts\python.exe ocr\app_vision_ocr.py                # ส่งผลให้ FSM (START.bat เปิดให้เอง)
```

**ปิดด้วย Ctrl+C หรือสร้างไฟล์ `ocr\STOP` เท่านั้น** — kill โปรเซส = กล้องค้างจนต้องถอดสาย USB ·
**ปิดโปรแกรม MVS ก่อนรันทุกครั้ง** กล้องเปิดได้ทีละโปรแกรม

## ย้ายไฟ/กล้อง ต้องจูนใหม่

1. `position_helper.py` — ตั้งตำแหน่งหลุม/จุดอ้างอิงใหม่
2. `exposure_sweep.py` — หา exposure ที่ผ่านทุกรุ่น แล้วเลือกค่ากลางช่วงใส่ `cam_settings.json`
3. ทดสอบกับ FSM จริงก่อนใช้

## กับดักที่เจอแล้ว

| เรื่อง | ต้องทำยังไง |
|---|---|
| **แสงสะท้อนบนผิวโลหะ** | ไฟส่องตรงทำให้ตัวอักษรเลเซอร์หาย — จัดไฟเฉียงต่ำ + บังแสงเพดาน · ไฟขยับนิดเดียวก็ต้องจูนใหม่ |
| **กล้องค้าง 1 ภาพ/วินาที** | ค่าจำกัดเฟรมเรตค้างในตัวกล้อง — `hik_camera.py` ปิดให้แล้ว (ตรวจจาก 10 s → 2 s) |
| **ค่าที่ตั้งใน MVS ค้างอยู่ในกล้อง** | จนกว่าจะถอดสาย USB — ขนาดภาพต้องเป็น 2592×1944 (ROI ใน MVS ไม่ใช่การซูม) |
| **อ่านได้ข้อความแปลกคล้ายกลับหัว** | เช็กค่า `rotate` ใน `ocr_config.json` ทุกครั้งที่ย้าย/หมุนกล้อง |
| **Paddle บน CPU error `ConvertPirAttribute2RuntimeAttribute`** | ใส่ `enable_mkldnn=False` (ใส่ในโค้ดแล้ว) |
| **ลง EasyOCR แล้วเปิดไม่ขึ้น (`WinError 127`)** | ต้อง `import torch` ก่อน `import paddle` (ใส่ในโค้ดแล้ว) |
| **ผลแกว่งตามแสงห้อง** | อย่าเชื่อผลรอบเดียว — วัดซ้ำและจดเวลาที่วัด |
| **path มีอักษรที่ไม่ใช่ภาษาอังกฤษ** | pip ที่ build จาก source พัง — ใช้ `--only-binary=:all:` |
