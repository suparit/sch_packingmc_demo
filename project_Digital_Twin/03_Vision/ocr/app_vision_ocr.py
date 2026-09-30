"""ตรวจชิ้นงานด้วย OCR แล้วส่งผลให้ FSM — ใช้แทน app_vision.py (OpenMV) เมื่อใช้กล้อง HIKROBOT

หลักการเหมือน app_vision.py ทุกอย่าง ต่างกันแค่วิธีตัดสิน:
  เดิม : นับขอบในภาพ (มีชิ้นงาน = PASS)
  ใหม่ : OCR อ่านตัวหนังสือ แล้วตรวจทีละช่องตาม fields ใน ocr_config.json
         (ช่องที่ required=true ต้องผ่านครบทุกช่อง = PASS)

การคุยกับ gateway ใช้ข้อความเดิม: FSM อยู่สถานะ VISION และ step_allowed=True
  -> ส่ง {"action": "DECISION", "value": true/false, "meta": {...}} -> รอ DECISION_ACK
  PASS = FSM เดินต่อ · FAIL = FSM เข้า ALARM

หน้าจอแสดงผลเป็นหน้าเว็บแบบที่พี่เลี้ยงแนะนำ (Teams 22 ก.ย. 2569 10:35) ที่ http://127.0.0.1:5000

วิธีใช้ (ต้องปิดโปรแกรม MVS และเลือก ROI ไว้ก่อนด้วย ocr_roi.py --select):
    .venv-ocr\\Scripts\\python.exe ocr\\app_vision_ocr.py              # ต่อ gateway (รัน gateway โหมด camera ก่อน)
    .venv-ocr\\Scripts\\python.exe ocr\\app_vision_ocr.py --standalone # ดูผลอย่างเดียว ไม่ต่อ FSM
ปิด: กด Ctrl+C ในหน้าต่าง Terminal หรือสร้างไฟล์ชื่อ STOP ในโฟลเดอร์นี้
     **อย่า kill โปรเซส** — ถ้าตัดกลางการดึงภาพ กล้องอาจค้างจนต้องถอดสาย USB เสียบใหม่ (เจอแล้ว 22 ก.ย.)
"""
import argparse
import json
import queue
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import cv2
import numpy as np

import pocket_measure as pm  # วัดตำแหน่งหลุม carrier (ใช้ร่วมกับ feed_pocket_view.py)

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "ocr_config.json").read_text(encoding="utf-8"))
ROTATE = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


# ---------------------------------------------------------------------------
# การคุยกับ gateway — ลอกพฤติกรรมจาก app_vision.py (GET_STATE / LIVE_SYNC / DECISION / DECISION_ACK)
# ---------------------------------------------------------------------------
class GatewayLink:
    def __init__(self, url):
        import websocket  # websocket-client
        self._websocket = websocket
        self.url = url
        self.ws = None
        # RLock: send() ถือ lock แล้วเรียก _connect() ซ้ำได้ · 25 ก.ย. 2569 เคยมีสายค้าง 2 เส้น —
        # thread ฟังกับ thread ส่งสร้างสายพร้อมกันโดยไม่ล็อก + ส่งพลาดแล้วทิ้งสายเก่าไม่ปิด → สายที่ไม่มีใครอ่าน
        # ทำบัฟเฟอร์ฝั่ง gateway เต็มจน broadcast ค้าง เว็บ 3D หยุดอัปเดตทั้งระบบ
        self.lock = threading.RLock()
        self.acks = queue.Queue()
        self.state = "UNKNOWN"
        self.step_allowed = False
        self.pocket = None
        self.last_sync = 0.0
        threading.Thread(target=self._listen, daemon=True).start()

    def _connect(self):
        with self.lock:   # มีสายได้เส้นเดียวเสมอ
            if self.ws is None:
                try:
                    self.ws = self._websocket.create_connection(self.url, timeout=0.5)
                    self.ws.settimeout(0.1)
                    print(f"✅ ต่อ gateway แล้ว ({self.url})")
                except Exception:
                    self.ws = None
            return self.ws

    def _drop(self, ws=None):
        """ปิดสายที่พัง · ส่ง ws มาด้วย = ปิดเฉพาะถ้ายังเป็นสายปัจจุบัน (ไม่ไปปิดสายใหม่ที่อีก thread เพิ่งต่อ)"""
        with self.lock:
            if ws is not None and ws is not self.ws:
                target, keep = ws, True
            else:
                target, keep = self.ws, False
            if target is not None:
                try:
                    target.close()
                except Exception:
                    pass
            if not keep:
                self.ws = None

    def send(self, payload):
        with self.lock:
            ws = self._connect()
            if ws is None:
                return False
            try:
                ws.send(json.dumps(payload))
                return True
            except Exception:
                self._drop(ws)   # ปิดสายเก่าด้วย ไม่ทิ้งค้างไว้
                return False

    def request_state(self):
        self.send({"action": "GET_STATE"})

    @property
    def online(self):
        return time.time() - self.last_sync < 1.5

    def _listen(self):
        while True:
            ws = self._connect()
            if ws is None:
                time.sleep(0.3)
                continue
            try:
                msg = json.loads(ws.recv())
            except self._websocket.WebSocketTimeoutException:
                continue
            except Exception:
                self._drop(ws)
                time.sleep(0.2)
                continue
            kind = msg.get("type") or msg.get("action")
            if kind == "LIVE_SYNC":
                system = msg.get("system", {})
                if system.get("current_state"):
                    self.state = system["current_state"]
                    self.step_allowed = bool(system.get("step_allowed", False))
                    self.pocket = system.get("pocket")   # ใช้ตั้งชื่อไฟล์ภาพ GOOD/NG
                    self.last_sync = time.time()
            elif kind == "DECISION_ACK":
                self.acks.put(msg)

    def send_decision(self, passed, meta, retries=3, ack_timeout=1.0):
        """ส่งผลแล้วรอ ACK — คืน True ถ้า gateway รับ"""
        for attempt in range(1, retries + 1):
            while not self.acks.empty():
                self.acks.get_nowait()
            if not self.send({"action": "DECISION", "value": bool(passed), "meta": meta}):
                time.sleep(0.2)
                continue
            try:
                ack = self.acks.get(timeout=ack_timeout)
            except queue.Empty:
                print(f"⚠️ ไม่ได้ ACK ครั้งที่ {attempt} ลองใหม่")
                continue
            if ack.get("accepted"):
                return True
            print(f"❌ gateway ไม่รับผล: {ack.get('reason')}")
            return False
        return False


# ---------------------------------------------------------------------------
# การตัดสิน — ตรวจทีละช่องแบบหน้า VERIFICATION RESULT ของพี่เลี้ยง
# ---------------------------------------------------------------------------
def find_part(gray, prefer=None):
    """หาตัวชิ้นงานทรงกลมในภาพ คืน (cx, cy, r) ของวงที่ใกล้จุด prefer ที่สุด (None = ไม่เจอ)

    ย่อภาพ 4 เท่าก่อนเพื่อความเร็ว (~20 ms) แล้วคูณพิกัดกลับ
    วัดจริง 23 ก.ย.: เจอ 6/6 เฟรม จุดกลางแกว่ง ±4 px รัศมีชิ้นงานราว 247 px
    """
    ac = CONFIG.get("auto_center", {})
    small = cv2.resize(gray, None, fx=0.25, fy=0.25)
    circles = cv2.HoughCircles(cv2.medianBlur(small, 5), cv2.HOUGH_GRADIENT,
                               dp=1.2, minDist=120, param1=60,
                               # 25 ก.ย.: 40 -> 32 — ชิ้นงานที่วางถูกในหลุมบางภาพขอบจางจนหาไม่เจอ (FAIL "ไม่พบชิ้นงาน"
                               # ทั้งที่ของถูก) · 32 เจอครบทุกชิ้นใน 2 ภาพทดสอบ และลดถึง 25 ก็ยังไม่มีวงหลอก
                               param2=int(ac.get("hough_param2", 40)),
                               minRadius=int(ac.get("min_radius", 160) / 4),
                               maxRadius=int(ac.get("max_radius", 360) / 4))
    if circles is None:
        return None
    h, w = gray.shape
    tx, ty = prefer if prefer else (w / 2, h / 2)
    best = min(np.round(circles[0]).astype(int),
               key=lambda c: (c[0] * 4 - tx) ** 2 + (c[1] * 4 - ty) ** 2)
    return int(best[0] * 4), int(best[1] * 4), int(best[2] * 4)


def crop_centered(gray, part, scale):
    """ครอปสี่เหลี่ยมจัตุรัสรอบชิ้นงานให้อยู่กลางกรอบ"""
    cx, cy, r = part
    half = int(r * scale / 2)
    h, w = gray.shape
    x1, y1 = max(0, cx - half), max(0, cy - half)
    x2, y2 = min(w, cx + half), min(h, cy + half)
    return gray[y1:y2, x1:x2]


def load_ocr():
    """โหลดตัว OCR ตาม ocr_config.json — คืน (ตัว OCR, ชื่อที่แสดงบนหน้าเว็บ)

    "ocr_engine": "paddle" (ค่าเริ่มต้น) หรือ "easyocr" · "ocr_device": "gpu:0"/"cpu" (เฉพาะ paddle, ว่าง = เลือกเอง)
    แยกไว้ตามหลักพี่เลี้ยง "no HW / no OS / no vendor lock-in" — ส่วนอื่นของแอปไม่รู้ว่าใช้ตัวไหน
    วัดจริง 24 ก.ย. (ไฟ 2 ด้าน · i5-13420H): Paddle GPU ครบ 5 บรรทัด 10/10 · 60 ms/ภาพ ·
    Paddle CPU 10/10 · ~4.9 s · EasyOCR CPU อ่านรหัสรุ่นได้ดีสุด 4/10 · ~1.4 s
    """
    if CONFIG.get("ocr_engine", "paddle") == "easyocr":
        import easyocr
        print("โหลดโมเดล OCR: EasyOCR บน CPU ...")
        ocr = easyocr.Reader(["en"], gpu=False, verbose=False)
        ocr.readtext(np.zeros((64, 64), np.uint8))  # warm-up
        return ocr, "easyocr-cpu"
    import paddle
    from paddleocr import PaddleOCR
    device = CONFIG.get("ocr_device") or (
        "gpu:0" if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() else "cpu")
    print(f"โหลดโมเดล OCR: PaddleOCR บน {device} ...")
    ocr = PaddleOCR(lang="en", use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_textline_orientation=False, enable_mkldnn=False, device=device)
    ocr.predict(np.zeros((64, 64, 3), np.uint8))  # warm-up ครั้งแรกช้า
    return ocr, f"paddle-{device}"


def read_lines(ocr, gray):
    """อ่านตัวหนังสือ คืน [(ข้อความ, ความมั่นใจ, กรอบสี่เหลี่ยมของบรรทัด)] — รองรับทั้ง PaddleOCR และ EasyOCR"""
    if hasattr(ocr, "readtext"):   # EasyOCR คืน [(กรอบ 4 จุด, ข้อความ, ความมั่นใจ)]
        return [(t, float(c), np.array(b, dtype=np.float32).reshape(-1, 2)) for b, t, c in ocr.readtext(gray)]
    out = []
    for r in ocr.predict(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)):
        polys = r.get("rec_polys", r.get("dt_polys"))
        for txt, conf, poly in zip(r["rec_texts"], r["rec_scores"], polys):
            out.append((txt, float(conf), np.array(poly).reshape(-1, 2)))
    return out


def line_angle(poly):
    """มุมเอียงของบรรทัด (องศา) จากขอบบนของกรอบ — ขวาลงล่างเป็นบวก"""
    pts = poly[np.argsort(poly[:, 1])][:2]          # สองจุดบนสุด = ขอบบนของบรรทัด
    (x1, y1), (x2, y2) = pts[np.argsort(pts[:, 0])]  # เรียงซ้าย -> ขวา
    return float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))


def field_hit(field, text, tol):
    """บรรทัด text ตรงกับช่องนี้ไหม · ช่องมีได้หลายรูปแบบ ("patterns") = รับรุ่นไหนก็ได้ในรายการ
    28 ก.ย. 2569: PART NR รับทั้ง 2 รุ่นในชุดทดสอบ (กำหนดใน ocr_config.json) (เจ้าของงานเลือก — ไม่เช็กว่าวางผิดรุ่น)"""
    n = normalize(text)
    for p in field.get("patterns") or [field["pattern"]]:
        if re.search(p, n) if field.get("regex") else close_enough(normalize(p), n, tol):
            return True
    return False


def anchor_line(lines):
    """หาบรรทัดที่ใช้อ้างอิงทิศทาง = ช่องแรกที่ตั้ง orientation_anchor (ปริยาย: PART NR)"""
    want = CONFIG.get("orientation", {}).get("anchor", "PART NR")
    tol = int(CONFIG.get("max_char_errors", 0))
    field = next((f for f in CONFIG["fields"] if f["name"] == want), None)
    if field is None:
        return None
    for text, conf, poly in lines:
        hit = field_hit(field, text, tol)
        if hit and conf >= CONFIG["min_confidence"]:
            return text, conf, poly
    return None


def check_orientation(ocr, roi, lines):
    """คืน (สถานะ, ข้อความอธิบาย, มุมที่วัดได้ หรือ None)

    สถานะมี 4 แบบ — แยก "ผิดแน่ๆ" ออกจาก "ตรวจไม่ได้" เพราะอ่านไม่ออกไม่ได้แปลว่าวางผิด
      ok      = วางตรงตามเกณฑ์
      tilted  = เอียงเกินเกณฑ์
      rotated = ถูกวางหมุน 90/180/270 องศา
      unknown = อ่านบรรทัดอ้างอิงไม่ได้ จึงสรุปทิศทางไม่ได้

    ขั้นที่ 1: ถ้าอ่านบรรทัดอ้างอิงได้ที่ทิศปกติ -> วัดมุมเอียงจากกรอบบรรทัด
    ขั้นที่ 2: ถ้าอ่านไม่ได้ -> ลองหมุน 90/180/270 ถ้าทิศไหนอ่านได้ แปลว่าชิ้นงานถูกวางหมุนเท่านั้น
               (แยก "วางผิดทิศ" ออกจาก "ภาพไม่ดีจนอ่านไม่ออก")
    """
    cfg = CONFIG.get("orientation", {})
    tol_deg = float(cfg.get("max_angle_deg", 15))
    found = anchor_line(lines)
    if found:
        angle = line_angle(found[2])
        ok = abs(angle) <= tol_deg
        return ("ok" if ok else "tilted"), (f"มุม {angle:+.0f}° (เกณฑ์ ±{tol_deg:.0f}°)" if ok
                    else f"เอียง {angle:+.0f}° เกินเกณฑ์ ±{tol_deg:.0f}°"), angle
    if not cfg.get("search_rotations", True):
        return "unknown", "อ่านบรรทัดอ้างอิงไม่ได้", None
    for rot, code in ((90, cv2.ROTATE_90_CLOCKWISE), (180, cv2.ROTATE_180),
                      (270, cv2.ROTATE_90_COUNTERCLOCKWISE)):
        if anchor_line(read_lines(ocr, cv2.rotate(roi, code))):
            return "rotated", f"วางหมุน {rot}° ({'กลับหัว' if rot == 180 else 'ผิดทิศ'})", float(rot)
    return "unknown", "ตรวจทิศทางไม่ได้ (อ่านบรรทัดอ้างอิงไม่ออก)", None


def pocket_check(gray, part):
    """ชิ้นงานอยู่ในหลุมทั้งวงไหม — คืน (สถานะ, ข้อความ, กรอบหลุม (L,T,R,B) หรือ None)

    เงื่อนไขตามพี่เลี้ยง/เจ้าของงาน 25 ก.ย. 2569: "ถูกตำแหน่ง = อยู่ในหลุม + หันถูกทาง" เท่านั้น
    (เดิมเทียบกับจุดตายตัวในภาพ -> ตกทุกครั้งที่ feed หยุดคลาดนิดเดียว ทั้งที่ชิ้นงานยังอยู่ในหลุม)

    วิธีหาหลุม: แสงส่องทางเดียว ขอบบน/ข้างของหลุมจางมาก (ความแรง 1–3) แต่ "สันล่าง" ของหลุมสว่างชัด
    (สว่าง -> มืดเมื่อไล่ลงล่าง ความแรง 15–32) จึงหาเฉพาะสันล่าง แล้วใช้ขนาดหลุมที่วัดไว้กำหนดกรอบที่เหลือ
    ผนังซ้าย/ขวาคงที่เพราะรางบังคับเทปไม่ให้เลื่อนข้าง — ค่าเป็น px ต้องวัดใหม่ถ้าเปลี่ยนระยะกล้อง/เลนส์
    ดูสันล่างจากแถบคอลัมน์ข้างชิ้นงาน (สันลากยาวเต็มความกว้างหลุม) จึงเห็นแม้ชิ้นงานคร่อมสันอยู่
    """
    pk = CONFIG.get("conditions", {}).get("position", {}).get("pocket", {})
    xl, xr = int(pk.get("x_left", 480)), int(pk.get("x_right", 1651))
    height, web = float(pk.get("height_px", 885)), float(pk.get("web_px", 184))
    pitch, tol = float(pk.get("pitch_px", 1066)), float(pk.get("tol_px", 25))
    min_rim = float(pk.get("min_rim_strength", 6.0))
    # ทิศของสันล่างขึ้นกับแสง (28 ก.ย. 2569): ไฟชุดเดิม = สันสว่าง -> มืด · หลอดใหม่ = ในหลุมมืด -> ผิวเทปสว่าง
    # ใช้ผิดทิศ = จับขอบอื่นแทน (เคยได้ "ล้นขอบบน 215 px" ทั้งที่ชิ้นงานอยู่กลางหลุม) · ตั้งใน config ตามไฟที่ใช้
    sign = 1.0 if pk.get("rim_polarity", "bright_to_dark") == "dark_to_bright" else -1.0
    px, py, r = part
    h, w = gray.shape[:2]
    a0, a1 = xl + 30, min(px - r - 25, xr - 30)
    b0, b1 = max(px + r + 25, xl + 30), xr - 30
    cols = np.r_[max(0, a0):max(0, a1), min(w, b0):min(w, b1)]
    if len(cols) < 40:
        return "unknown", "หาหลุมไม่ได้ (ชิ้นงานบังผนังหลุม)", None
    g = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 2)
    # ติดลบ = สว่าง -> มืด (ไล่ลงล่าง) · คูณ sign ให้ "สันตามทิศที่ตั้ง" เป็นค่าบวกเสมอ
    prof = sign * cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)[:, cols].mean(axis=1)

    def rim(lo, hi):
        lo, hi = int(max(0, lo)), int(min(h - 1, hi))
        if hi - lo < 5:
            return None
        i = lo + int(np.argmax(prof[lo:hi]))
        return i if prof[i] >= min_rim else None

    if pk.get("rim_polarity") == "web_band":
        # 28 ก.ย. 2569 (หลอดไฟใหม่): หาสันเส้นเดียวไม่นิ่ง — ขอบในหลุม (ขาจับชิ้นงาน) แรงกว่าสันล่าง
        # ใช้ "แถบผิวเทประหว่างหลุม" แทน: สว่างกว่าในหลุมชัด กว้าง web_px · ในช่วง 1 pitch ใต้กลางชิ้นงานมีแถบเดียว
        mp = g[:, cols].mean(axis=1)
        band = np.convolve(mp, np.ones(int(web)) / web, mode="same")
        lo, hi = int(max(web / 2, py - web / 2)), int(min(h - web / 2, py - web / 2 + pitch))
        if hi - lo < 5:
            return "unknown", "หาแถบระหว่างหลุมไม่ได้ (หลุดกรอบภาพ)", None
        c = lo + int(np.argmax(band[lo:hi]))
        if band[c] - float(np.median(band[lo:hi])) < float(pk.get("min_web_contrast", 5.0)):
            return "unknown", "หาแถบระหว่างหลุมไม่เจอ (มืด/แสงเปลี่ยน)", None
        bottom = c - web / 2
        top = bottom - height
    else:
        below = rim(py + 20, py + pitch)
        if below is not None:
            bottom = below
            top = bottom - height
        else:
            above = rim(py - pitch, py - 20)
            if above is None:
                return "unknown", "หาสันหลุมไม่เจอ (มืด/หลุดกรอบภาพ)", None
            top = above + web
            bottom = top + height
    box = (xl, int(top), xr, int(bottom))
    m = {"ซ้าย": px - r - xl, "ขวา": xr - (px + r), "บน": py - r - top, "ล่าง": bottom - (py + r)}
    worst = min(m, key=m.get)
    if m[worst] < -tol:
        return "out", f"ไม่อยู่ในหลุม — ล้นขอบ{worst} {-m[worst]:.0f} px", box
    return "in", f"อยู่ในหลุม (เผื่อ ซ้าย {m['ซ้าย']:.0f} ขวา {m['ขวา']:.0f} บน {m['บน']:.0f} ล่าง {m['ล่าง']:.0f} px)", box


def check_conditions(part, expected_center, lines, text_ok, text_reason, ori_status, ori_text, pocket=None):
    """เงื่อนไขการตรวจ 4 ข้อตามที่พี่เลี้ยงกำหนด (Teams 23 ก.ย. 2569)

    1. มีชิ้นงานไหม        — หาวงกลมของตัวชิ้นงานเจอหรือไม่
    2. วางถูกตำแหน่งไหม   — จุดกลางห่างจากตำแหน่งที่ควรเป็นเท่าไร และเอียงกี่องศา
    3. ตัวหนังสือเห็นไหม   — OCR เจอบรรทัดข้อความกี่บรรทัด (ยังไม่สนว่าอ่านถูกไหม)
    4. กล้องอ่านออกไหม    — รหัสรุ่น/ยี่ห้อตรงกับที่ตั้งไว้หรือไม่

    ข้อ 1–3 ไม่ต้องพึ่งความแม่นของ OCR จึงใช้งานได้แม้แสงยังไม่ดีพอ
    """
    c = CONFIG.get("conditions", {})
    out = []

    pres = c.get("presence", {})
    out.append({"name": "1 มีชิ้นงาน", "ok": part is not None,
                "value": f"เจอที่ ({part[0]},{part[1]}) รัศมี {part[2]} px" if part else "ไม่พบชิ้นงานในภาพ",
                "conf": 0.0, "required": bool(pres.get("required", True))})

    pos = c.get("position", {})
    if part is None:
        out.append({"name": "2 วางถูกตำแหน่ง", "ok": False, "value": "ตรวจไม่ได้ (ไม่พบชิ้นงาน)",
                    "conf": 0.0, "required": bool(pos.get("required", True))})
    elif pos.get("mode", "offset") == "in_pocket" and pocket is not None:
        # ถูกตำแหน่ง = อยู่ในหลุม + หันถูกทาง (25 ก.ย. 2569) · หาหลุมไม่ได้ = ไม่ผ่าน (ไม่เดาว่าอยู่)
        p_status, p_text, _ = pocket
        # ori_status = unknown (อ่านบรรทัดอ้างอิงไม่ออก) ไม่ถือว่าวางผิด — ข้อนี้ต้องไม่พึ่ง OCR
        ok = p_status == "in" and ori_status in ("ok", "unknown")
        out.append({"name": "2 วางถูกตำแหน่ง", "ok": ok, "value": f"{p_text} · {ori_text}",
                    "conf": 0.0, "required": bool(pos.get("required", True))})
    else:
        dx, dy = part[0] - expected_center[0], part[1] - expected_center[1]
        offset = float(np.hypot(dx, dy))
        max_off = float(pos.get("max_offset_px", 120))
        # ori_status = unknown (อ่านบรรทัดอ้างอิงไม่ออก) ไม่ถือว่าวางผิด — ข้อนี้ต้องไม่พึ่ง OCR
        ok = offset <= max_off and ori_status in ("ok", "unknown")
        detail = f"เยื้อง {offset:.0f} px (เกณฑ์ {max_off:.0f}) · {ori_text}"
        out.append({"name": "2 วางถูกตำแหน่ง", "ok": ok, "value": detail,
                    "conf": round(offset, 1), "required": bool(pos.get("required", True))})

    tv = c.get("text_visible", {})
    min_lines = int(tv.get("min_lines", 2))
    out.append({"name": "3 ตัวหนังสือเห็น", "ok": len(lines) >= min_lines,
                "value": f"เจอ {len(lines)} บรรทัด (ต้องการ {min_lines})",
                "conf": 0.0, "required": bool(tv.get("required", True))})

    rd = c.get("readable", {})
    out.append({"name": "4 กล้องอ่านออก", "ok": text_ok,
                "value": "อ่านรหัสรุ่นตรงกับที่ตั้งไว้" if text_ok else text_reason,
                "conf": 0.0, "required": bool(rd.get("required", False))})

    failed = [o["name"] for o in out if o["required"] and not o["ok"]]
    return (not failed), out, ("ผ่านครบทุกเงื่อนไข" if not failed else "ไม่ผ่าน: " + ", ".join(failed))


def normalize(text):
    """ตัวพิมพ์ใหญ่ ตัดช่องว่าง/สัญลักษณ์ เหลือตัวอักษร ตัวเลข - / เพื่อเทียบได้แม้ OCR เว้นวรรคเพี้ยน"""
    return re.sub(r"[^A-Z0-9\-/]", "", text.upper())


def close_enough(pattern, text, max_errors):
    """ยอมให้ OCR อ่านผิดได้ไม่เกิน max_errors ตัวอักษร (เทียบทุกตำแหน่งที่เป็นไปได้ในบรรทัด)

    max_errors = 0 คือต้องตรงเป๊ะ (ค่าเริ่มต้น) เปิดใช้เมื่อภาพยังไม่ดีพอและยอมรับความเสี่ยงได้ว่า
    รหัสรุ่นที่ใกล้เคียงกันอาจถูกนับว่าตรงกัน
    """
    if max_errors <= 0:
        return pattern in text
    n = len(pattern)
    for start in range(max(1, len(text) - n + 1)):
        window = text[start:start + n]
        errors = sum(1 for a, b in zip(pattern, window) if a != b) + abs(n - len(window))
        if errors <= max_errors:
            return True
    return False


def check_fields(lines):
    """lines = [(text, conf)] -> (passed, [field results], reason)"""
    tolerance = int(CONFIG.get("max_char_errors", 0))
    results = []
    for f in CONFIG["fields"]:
        found = None
        for text, conf in lines:
            hit = field_hit(f, text, tolerance)
            if hit and (found is None or conf > found[1]):
                found = (text, conf)
        ok = bool(found) and found[1] >= CONFIG["min_confidence"]
        results.append({"name": f["name"], "value": found[0] if found else "—",
                        "conf": round(found[1], 3) if found else 0.0,
                        "required": f["required"], "ok": ok})
    failed = [r["name"] for r in results if r["required"] and not r["ok"]]
    if not lines:
        return False, results, "NO TEXT"
    return (not failed), results, ("ALL REQUIRED FIELDS OK" if not failed else "FAILED: " + ", ".join(failed))


# ---------------------------------------------------------------------------
# หน้าเว็บ
# ---------------------------------------------------------------------------
STATUS = {"lock": threading.Lock(), "json": b"{}", "roi": b""}

PAGE = """<!doctype html><html lang="th"><head><meta charset="utf-8"><title>Vision Testing</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
/* 25 ก.ย. 2569: จัดใหม่ให้พอดีหนึ่งจอ ไม่ต้องเลื่อน — ภาพตรวจชิ้นงานกับภาพตำแหน่ง carrier อยู่ข้างกัน */
:root{--bg:#1e1f22;--panel:#2b2d31;--line:#3a3c42;--ink:#e6e6e6;--mute:#9aa0a6;--ok:#16b24b;--ng:#e5383b;--acc:#2ee06c}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.45 system-ui,"Segoe UI",Tahoma,sans-serif;padding:8px;
 display:grid;grid-template-rows:auto minmax(0,1fr);gap:8px;overflow:hidden}
.mono{font-family:Consolas,"Cascadia Mono",monospace}
.card{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px 12px;min-height:0}
header{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
h1{margin:0;color:var(--acc);font-size:16px;letter-spacing:.03em}.sub{color:var(--mute);font-size:11px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-left:auto}
.chip{background:#23252a;border:1px solid var(--line);border-radius:12px;padding:2px 10px;font-size:12px;white-space:nowrap}
.chip b{color:var(--acc)}.chip b.off{color:var(--ng)}
main{display:grid;grid-template-columns:260px minmax(0,1fr) minmax(0,1fr);gap:8px;min-height:0}
aside{display:flex;flex-direction:column;gap:8px;min-height:0;overflow:auto}
.lbl{color:var(--acc);font-weight:700;font-size:12px;margin-bottom:4px;letter-spacing:.02em}
.row{display:flex;justify-content:space-between;gap:8px;padding:1px 0}
.row .v{color:var(--mute);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px}
.pass{color:var(--acc)}.fail{color:var(--ng)}.opt{color:var(--mute)}
.small{font-size:11px;color:var(--mute)}
.view{display:flex;flex-direction:column;gap:6px}
.vhead{display:flex;align-items:center;gap:10px}
.vhead .lbl{margin:0;flex:1}
.badge{font:700 26px/1 system-ui,"Segoe UI",sans-serif;padding:6px 14px;border-radius:6px;background:#555;color:#fff;white-space:nowrap}
.badge.ok{background:var(--ok)}.badge.ng{background:var(--ng)}.badge.idle{background:#444;color:var(--mute);font-size:18px}
.imgbox{flex:1;min-height:0;background:#000;border:1px solid var(--line);border-radius:4px;display:flex;align-items:center;justify-content:center;overflow:hidden}
.imgbox img{max-width:100%;max-height:100%;object-fit:contain;display:block}
.foot{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
/* 28 ก.ย. 2569: ตั้งเส้น index ด้วยการคลิกบนภาพ — โหมดเลือก = เคอร์เซอร์กากบาท + เส้นนำตามเมาส์ */
#cbox{position:relative}#cbox.pick{outline:2px dashed #f5a623;cursor:crosshair}#cbox.pick img{cursor:crosshair}
#guide{position:absolute;height:0;border-top:2px dashed #f5a623;pointer-events:none;display:none}
button.on{background:#f5a623;color:#111;border-color:#f5a623}
button{padding:5px 12px;background:#3a3c42;color:var(--ink);border:1px solid var(--acc);border-radius:4px;cursor:pointer;font:inherit}
button:hover{background:#44474e}
@media (max-width:1100px){
 body{overflow:auto;display:block}main{grid-template-columns:1fr}header{margin-bottom:8px}
 .imgbox{height:55vh;flex:none}aside{overflow:visible}
}
</style></head><body>
<header class="card">
 <div><h1 id="title"></h1><div class="sub" id="subtitle"></div></div>
 <div class="chips">
  <span class="chip">CAMERA <b id="srv">—</b></span>
  <span class="chip">FSM <b id="fsm">—</b></span>
  <span class="chip">ส่งให้ FSM ล่าสุด <b id="sent">—</b></span>
  <span class="chip mono" id="ts">—</span>
 </div>
</header>
<main>
 <aside>
  <div class="card"><div class="lbl">ผลตรวจ 4 ข้อ</div><div id="checks"></div></div>
  <div class="card"><div class="lbl">OCR CONFIDENCE</div><div id="conf" class="small mono"></div></div>
  <div class="card"><div class="lbl">คุณภาพภาพ</div>
   <div class="row"><span>BRIGHTNESS</span><b id="bright" class="mono">—</b></div>
   <div class="row"><span>SHARPNESS</span><span class="mono"><b id="sharp">—</b> <span class="small">/ สูงสุด <span id="peak">—</span></span></span></div>
   <div class="small" id="qtip"></div>
   <div class="small" style="margin-top:4px">ตำแหน่ง: <span id="locate">—</span></div>
   <div class="small">OCR <span id="ms" class="mono">—</span> ms · <span id="dev">—</span></div>
  </div>
 </aside>
 <section class="card view">
  <div class="vhead"><div class="lbl">① ตรวจชิ้นงาน (VISION)</div><div id="banner" class="badge idle">WAIT</div></div>
  <div class="foot"><button id="vdec" class="on">ภาพที่ใช้ตัดสิน</button><button id="vlive">ภาพสด</button>
   <span class="small" id="dcap"></span></div>
  <div class="imgbox"><img id="roi" alt="ROI"></div>
  <div class="small" id="reason"></div>
 </section>
 <section class="card view">
  <div class="vhead"><div class="lbl">② ตำแหน่ง carrier เทียบ index</div><div id="cbanner" class="badge idle">—</div></div>
  <div class="imgbox" id="cbox"><img id="carrier" alt="carrier"><div id="guide"></div></div>
  <div class="small" id="cmsg"></div>
  <div class="foot">
   <button id="setidx">ตั้ง index: คลิกบนภาพ</button>
   <span class="small" id="chint">เขียว = index · ส้ม = ตำแหน่งเดียวกันของหลุมตอนนี้ · ดูอย่างเดียว ไม่ส่งผลให้ FSM · ตั้งตอนเครื่องหยุด + หลุมว่าง</span>
  </div>
 </section>
</main>
<script>
const $=id=>document.getElementById(id);
async function tick(){
 try{
  const s=await (await fetch('/api/status',{cache:'no-store'})).json();
  $('title').textContent=s.title;$('subtitle').textContent=s.subtitle;
  $('srv').textContent=s.camera?'ONLINE':'OFFLINE';$('srv').className=s.camera?'':'off';
  $('fsm').textContent=s.fsm;$('fsm').className=s.fsm_online?'':'off';$('ts').textContent=s.timestamp;
  // ภาพที่ใช้ตัดสิน (ค้างจนตัดสินชิ้นถัดไป) หรือภาพสด — ผลตรวจ 4 ข้อ/ป้าย/เหตุผลตามภาพที่แสดง
  const d=s.decision, useDec=showDec&&d;
  const b=$('banner');
  if(useDec){b.textContent=d.passed?'PASS':'NG';b.className='badge '+(d.passed?'ok':'ng')}
  else{b.textContent=s.camera?(s.passed?'PASS':'FAIL'):'NO CAMERA';b.className='badge '+(s.camera?(s.passed?'ok':'ng'):'idle')}
  $('dcap').textContent=useDec?`ภาพนิ่งที่ส่งผลให้ FSM · ${d.time}${d.pocket!=null?' · หลุม '+d.pocket:''}`:(showDec?'ยังไม่มีภาพที่ใช้ตัดสิน — แสดงภาพสด':'ภาพสด (อัปเดตทุกเฟรม)');
  const flds=useDec?d.fields:s.fields;
  $('checks').innerHTML=flds.map(f=>`<div class="row ${f.ok?'pass':(f.required?'fail':'opt')}"><span>${f.ok?'✓':'✗'} ${esc(f.name)}</span><span class="v" title="${esc(f.value)}">${esc(f.value)}</span></div>`).join('');
  $('conf').innerHTML=s.lines.map(l=>`<div>${esc(l[0])} = ${l[1].toFixed(3)}</div>`).join('')||'—';
  $('ms').textContent=s.ocr_ms;$('dev').textContent=s.device;$('reason').textContent=useDec?d.reason:s.reason;$('sent').textContent=s.last_sent||'—';
  $('bright').textContent=s.brightness;$('bright').className='mono '+((s.brightness>=90&&s.brightness<=170)?'pass':'fail');
  $('sharp').textContent=s.sharpness;$('peak').textContent=s.sharp_peak;$('locate').textContent=s.locate||'—';
  $('sharp').className=(s.sharp_peak&&s.sharpness>=s.sharp_peak*0.95)?'pass':'fail';
  $('qtip').textContent=s.brightness<90?'ภาพมืดไป เพิ่มไฟหรือเปิดรูรับแสง':(s.sharpness<s.sharp_peak*0.95?'หมุนโฟกัสกลับ ค่าเพิ่งตกจากจุดที่ดีที่สุด':'ตอนนี้คมที่สุดเท่าที่เคยวัดได้');
  const src=useDec?'/decision.jpg?d='+encodeURIComponent(d.time+'_'+d.pocket):'/roi.jpg?t='+s.seq;
  if($('roi').getAttribute('src')!==src)$('roi').src=src;   // ภาพตัดสินไม่ต้องโหลดซ้ำทุกวินาที
  const c=s.carrier||{};const cb=$('cbanner');
  cb.textContent=c.off_mm==null?(c.set?'วัดไม่ได้':'ยังไม่ตั้ง index'):`${c.off_mm>0?'+':''}${c.off_mm.toFixed(2)} mm`;
  cb.className='badge '+(c.off_mm==null?'idle':(c.ok?'ok':'ng'));
  $('cmsg').textContent=(c.off_mm!=null?(c.ok?'ตรง index':'ไม่ตรง index')+` (เกณฑ์ ±${c.tol_mm} mm) · `:'')+(c.msg||'')+(c.score!=null?` · คะแนนแม่แบบ ${c.score}`:'');
  $('carrier').src='/carrier.jpg?t='+s.seq;
 }catch(e){$('srv').textContent='OFFLINE';$('srv').className='off'}
}
let showDec=true;
$('vdec').onclick=()=>{showDec=true;$('vdec').classList.add('on');$('vlive').classList.remove('on');tick()};
$('vlive').onclick=()=>{showDec=false;$('vlive').classList.add('on');$('vdec').classList.remove('on');tick()};
// ตั้งเส้น index: กดปุ่ม → คลิกบนภาพตรงแถวที่ต้องการ (ส่งเป็นสัดส่วนความสูงภาพ 0..1) · กดปุ่มซ้ำ/Esc = ยกเลิก
let picking=false;const HINT=$('chint').textContent;
function setPick(on){picking=on;$('cbox').classList.toggle('pick',on);$('setidx').classList.toggle('on',on);
 $('setidx').textContent=on?'ยกเลิก':'ตั้ง index: คลิกบนภาพ';$('guide').style.display='none';
 $('chint').textContent=on?'คลิกบนภาพตรงแถวที่จะให้เป็นเส้น index (เช่น ขอบบนของหลุม) · Esc = ยกเลิก':HINT}
function rowAt(e){const r=$('carrier').getBoundingClientRect();const f=(e.clientY-r.top)/r.height;return(f>=0&&f<=1&&e.clientX>=r.left&&e.clientX<=r.right)?f:null}
$('setidx').onclick=()=>setPick(!picking);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&picking)setPick(false)});
$('cbox').addEventListener('mousemove',e=>{if(!picking)return;const g=$('guide'),img=$('carrier');const f=rowAt(e);
 if(f==null){g.style.display='none';return}
 g.style.display='block';g.style.left=img.offsetLeft+'px';g.style.width=img.offsetWidth+'px';g.style.top=(img.offsetTop+f*img.offsetHeight)+'px'});
$('carrier').onclick=async e=>{if(!picking)return;const f=rowAt(e);if(f==null)return;setPick(false);
 if(!confirm('ตั้งแถวที่คลิกเป็นเส้น index ใหม่? (ทับค่าเดิม)'))return;
 try{const r=await fetch('/api/set_index?y='+f.toFixed(4),{method:'POST'});$('cmsg').textContent=r.ok?'กำลังตั้ง index...':'ตั้งไม่ได้'}catch(err){alert('ส่งคำสั่งไม่ได้')}};
function esc(t){return String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
tick();setInterval(tick,1000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            body, ctype = PAGE.encode("utf-8"), "text/html; charset=utf-8"
        elif path == "/api/status":
            with STATUS["lock"]:
                body = STATUS["json"]
            ctype = "application/json"
        elif path == "/roi.jpg":
            with STATUS["lock"]:
                body = STATUS["roi"]
            ctype = "image/jpeg"
        elif path == "/decision.jpg":
            with STATUS["lock"]:
                body = DECISION["jpg"]
            ctype = "image/jpeg"
        elif path == "/carrier.jpg":
            with STATUS["lock"]:
                body = STATUS.get("carrier", b"")
            ctype = "image/jpeg"
        else:
            self.send_error(404)
            return
        self._reply(body, ctype)

    def do_POST(self):
        u = urlsplit(self.path)
        if u.path == "/api/set_index":
            # ?y=0..1 = แถวที่ผู้ใช้คลิกบนภาพ (สัดส่วนความสูงภาพ) · ไม่ส่ง = ให้โปรแกรมหาขอบหลุมเอง (แบบเดิม)
            # 28 ก.ย. 2569: แบบหาเองจับขอบช่องด้านในหลุมแทนขอบหลุมจริง → เปลี่ยนเป็นคลิกเลือกบนภาพ
            y = parse_qs(u.query).get("y", [None])[0]
            try:
                frac = None if y is None else float(y)
            except ValueError:
                frac = -1.0
            if frac is not None and not 0.0 <= frac <= 1.0:
                self.send_error(400, "y must be 0..1")
                return
            # ลูปหลักตั้งจากภาพถัดไป (กล้องเป็นของลูปหลักคนเดียว)
            CARRIER["set_request"] = True if frac is None else frac
            self._reply(b'{"ok":true}', "application/json")
        else:
            self.send_error(404)

    def _reply(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # ไม่ต้องพิมพ์ทุก request
        pass


def human_view(raw_crop, face=None):
    """ภาพสำหรับคนดูบนหน้าเว็บ — แยกจากภาพที่ส่งเข้า OCR (คำแนะนำพี่เลี้ยง 24 ก.ย.)

    ภาพที่ส่งเข้า OCR ถูกยืดความสว่างจากทั้งภาพให้โมเดลอ่าน แต่คนดูแล้วมัว
    ถ้ารู้ตำแหน่งหน้าชิ้นงาน (face = (cx, cy, r) ในพิกัดของ raw_crop) ยืดความสว่างจากเฉพาะหน้าชิ้นงาน
    (percentile 1–99.7) — แบบ "B" ที่พี่เลี้ยงวงว่าอ่านด้วยตาคนได้ดีกว่าภาพมัว
    ถ้าไม่รู้ ใช้โทนธรรมชาติ (จุดสว่าง 99.5% เป็นขาว + gamma 1/2.2)
    ใช้แสดงผลอย่างเดียว ไม่มีผลกับการตัดสิน PASS/FAIL
    """
    if face:
        cx, cy, r = face
        yy, xx = np.ogrid[:raw_crop.shape[0], :raw_crop.shape[1]]
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= (r * 0.85) ** 2
        if mask.sum() > 100:
            lo, hi = np.percentile(raw_crop[mask], [1, 99.7])
            return np.clip((raw_crop - lo) * 255.0 / max(1e-6, hi - lo), 0, 255).astype(np.uint8)
    hi = max(float(np.percentile(raw_crop, 99.5)), 1.0)
    return (np.clip(raw_crop / hi, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)


# ภาพนิ่งที่ใช้ตัดสินชิ้นล่าสุด — ค้างไว้บนหน้าเว็บให้คนอ่านตามจนกว่าจะตัดสินชิ้นถัดไป (28 ก.ย. 2569 เจ้าของงานขอ)
# ภาพสด (/roi.jpg) เปลี่ยนทุกเฟรม คนอ่านไม่ทัน และอาจไม่ใช่ภาพเดียวกับที่ใช้ตัดสิน
DECISION = {"meta": None, "jpg": b""}


def set_decision(view, meta):
    ok, jpg = cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if ok:
        with STATUS["lock"]:
            DECISION["jpg"], DECISION["meta"] = jpg.tobytes(), meta


def publish(status, roi_img):
    ok, jpg = cv2.imencode(".jpg", roi_img, [cv2.IMWRITE_JPEG_QUALITY, 85]) if roi_img is not None else (False, None)
    status = {**status, "carrier": CARRIER["status"], "decision": DECISION["meta"]}
    with STATUS["lock"]:
        STATUS["json"] = json.dumps(status, ensure_ascii=False).encode("utf-8")
        if ok:
            STATUS["roi"] = jpg.tobytes()


# ---------------------------------------------------------------------------
# ตำแหน่ง carrier เทียบเส้น index (25 ก.ย. 2569) — ดูผลหลังกดปุ่ม STEP บนจอว่าหลุมมาตรงตำแหน่งจริงไหม
# ใช้วิธีวัดเดียวกับ feed_pocket_view.py (pocket_measure.py: แม่แบบหลุม + รูสเตอร์เป็นไม้บรรทัด 4 mm)
# แสดงผลอย่างเดียว ไม่ส่งผลให้ FSM · ตั้งเส้น index ด้วยปุ่มบนหน้าเว็บ แม่แบบเก็บใน index_ref.npz (ไม่เข้า git)
# ---------------------------------------------------------------------------
INDEX_FILE = HERE / "index_ref.npz"
MIN_POCKET_SCORE = 0.5        # เท่า feed_pocket_view — ต่ำกว่านี้ = ภาพไม่เหมือนหลุมตอนตั้ง (มืด/เบลอ/มีชิ้นงานบัง)
PX_PER_MM_FALLBACK = 1066 / 24.0   # หลุม 24 mm = 1066 px (ocr_config.json) ใช้เมื่อวัดระยะรูสเตอร์ไม่ได้
CARRIER = {"tpl": None, "set_request": False, "last": 0.0, "status": {"msg": "ยังไม่ได้วัด"}}


def load_index_template():
    if INDEX_FILE.exists():
        try:
            tpl = pm.load_template(INDEX_FILE)
            # แม่แบบจากพิกัดชุดเก่า (ก่อนวัดใหม่ 28 ก.ย.) ความกว้างไม่ตรง → ใช้ไม่ได้ ต้องตั้ง index ใหม่
            widths = [tpl["pocket"].shape[1]] + [h.shape[1] for h in tpl["holes"]]
            want = [pm.POCKET_X[1] - pm.POCKET_X[0]] + [x1 - x0 for x0, x1 in pm.HOLE_COLS]
            if widths != want:
                print(f"⚠️ {INDEX_FILE.name} ตั้งไว้กับพิกัดกล้องชุดเก่า — ตั้งตำแหน่ง index ใหม่บนหน้าเว็บ")
                return
            CARRIER["tpl"] = tpl
            print(f"📏 โหลดตำแหน่ง index เดิม (ขอบหลุม y={CARRIER['tpl']['y']})")
        except Exception as e:
            print(f"⚠️ โหลด {INDEX_FILE.name} ไม่ได้: {e} — ตั้งตำแหน่ง index ใหม่บนหน้าเว็บ")


def carrier_view(avg, ref_y, live_y, scale=0.3):
    """ภาพย่อเฉพาะช่วงเทป (pm.VIEW_X) + เส้น index (เขียว) + ขอบหลุมตอนนี้ (ส้ม) · ยืดความสว่างจากภาพย่อ (เร็วกว่าทั้งภาพ)
    ครอปแค่แนวนอน ความสูงเต็มเฟรม → แถวที่คลิกบนภาพ (สัดส่วน 0..1) ยังตรงกับแถวในภาพเต็ม"""
    vx0, vx1 = pm.VIEW_X
    small = cv2.resize(avg[:, vx0:vx1].astype(np.float32), None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    lo, hi = np.percentile(small, [1, 99.5])
    vis = cv2.cvtColor(np.clip((small - lo) * 255.0 / max(1.0, hi - lo), 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    x0, x1 = int((pm.POCKET_X[0] - vx0) * scale), int((pm.POCKET_X[1] - vx0) * scale)
    cv2.rectangle(vis, (x0, 0), (x1, vis.shape[0] - 1), (90, 90, 90), 1)
    if ref_y is not None:
        r = int(round(ref_y * scale))
        cv2.line(vis, (0, r), (vis.shape[1], r), (0, 200, 0), 2)
    if live_y is not None:
        y = int(round(live_y * scale))
        cv2.line(vis, (x0, y), (x1, y), (0, 160, 255), 2)
    ok, jpg = cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return jpg.tobytes() if ok else b""


def carrier_update(avg, fsm):
    """วัดตำแหน่งหลุมเทียบเส้น index ทุก interval_s · ข้ามตอน FSM อยู่ VISION (ไม่แย่งเวลาตัดสินชิ้นงาน)"""
    cfg = CONFIG.get("carrier_index", {})
    if not cfg.get("enabled", True):
        return
    now = time.time()
    if CARRIER["set_request"] is False and (fsm == "VISION" or now - CARRIER["last"] < float(cfg.get("interval_s", 0.3))):
        return
    CARRIER["last"] = now
    tol = float(cfg.get("tolerance_mm", 0.3))
    st = {"set": False, "ok": False, "off_mm": None, "score": None, "tol_mm": tol, "msg": ""}
    live = None
    try:
        if avg.shape[:2] != pm.FULL_SHAPE:
            raise RuntimeError(f"ภาพ {avg.shape[1]}x{avg.shape[0]} ไม่ใช่เต็มเฟรม 2592x1944 — เช็ก ROI ค้างในกล้อง (MVS)")
        req = CARRIER["set_request"]
        if req is not False:
            CARRIER["set_request"] = False
            # True = หาขอบหลุมเอง · ตัวเลข 0..1 = แถวที่คลิกบนภาพ (ภาพ carrier เป็นเต็มเฟรมย่อ สัดส่วนเท่าภาพจริง)
            y = pm.mid_edge(avg) if req is True else req * avg.shape[0]
            tpl = pm.make_template(avg, y)
            pm.save_template(INDEX_FILE, tpl)
            CARRIER["tpl"] = tpl
            print(f"📏 ตั้งตำแหน่ง index ใหม่ที่ขอบหลุม y={tpl['y']}")
        tpl = CARRIER["tpl"]
        if tpl is None:
            live = pm.mid_edge(avg)
            st["msg"] = "ยังไม่ได้ตั้งตำแหน่ง index — กด STEP จนหลุมตรงตำแหน่งที่ต้องการ แล้วกด \"ตั้ง index: คลิกบนภาพ\""
        else:
            st["set"] = True
            y, sa, _ = pm.locate(avg, tpl, tpl["y"], 480)   # ±480 px < ครึ่งหลุม (~533) → เลือกหลุมที่ใกล้เส้นที่สุด
            st["score"] = round(sa, 2)
            if sa < MIN_POCKET_SCORE:
                st["msg"] = f"หาหลุมไม่ชัด (คะแนน {sa:.2f}) — มีชิ้นงานบัง/แสงเปลี่ยน/กล้องขยับ ถ้าเป็นตลอดให้ตั้ง index ใหม่"
            else:
                live = y
                hp = pm.hole_pitch_px(avg)
                px_mm = hp / pm.HOLE_MM if hp and 120 < hp < 260 else PX_PER_MM_FALLBACK
                off = (y - tpl["y"]) / px_mm
                st.update(off_mm=round(off, 2), ok=abs(off) <= tol,
                          msg=("ตรงตำแหน่ง index" if abs(off) <= tol else "ไม่ตรงตำแหน่ง index")
                          + f" · ขอบหลุม{'ต่ำกว่า' if off > 0 else 'สูงกว่า'}เส้นในภาพ {abs(off):.2f} mm")
    except Exception as e:
        st["msg"] = f"วัดไม่ได้: {e}"
    CARRIER["status"] = st
    jpg = carrier_view(avg, CARRIER["tpl"]["y"] if CARRIER["tpl"] else None, live)
    with STATUS["lock"]:
        STATUS["carrier"] = jpg


# ---------------------------------------------------------------------------
# เก็บภาพที่ใช้ตัดสินจริงทุกชิ้น แยก GOOD / NG (28 ก.ย. 2569 — เจ้าของงานขอไว้เป็นชุดเปรียบเทียบ)
# captures/<วันที่>/GOOD|NG/<เวลา>_p<หลุม>_{view.jpg ภาพคนดู · ocr.png ภาพที่ส่งเข้า OCR · full.jpg ทั้งเฟรม · .json ผลตรวจ}
# ภาพไม่เข้า git (.gitignore กัน *.jpg *.png และทั้งโฟลเดอร์) — ต้องคัดลอกไปไดรฟ์กลางเองตอนส่งมอบ
# ---------------------------------------------------------------------------
CAPTURE_DIR = HERE / "captures"


def save_capture(passed, view, roi, full, meta):
    if not CONFIG.get("save_captures", True):
        return
    try:
        d = CAPTURE_DIR / time.strftime("%Y-%m-%d") / ("GOOD" if passed else "NG")
        d.mkdir(parents=True, exist_ok=True)
        stem = time.strftime("%H%M%S") + (f"_p{meta['pocket']}" if meta.get("pocket") is not None else "")
        # cv2.imwrite เขียน path ที่มีอักษรไทย (สหกิจ) ไม่ได้บน Windows และไม่ error (คืน False เงียบ ๆ)
        # 28 ก.ย. รอบแรกได้แต่ .json → เข้ารหัสในหน่วยความจำแล้วเขียนด้วย Path แทน
        for name, img, ext, opt in ((f"{stem}_view.jpg", view, ".jpg", [cv2.IMWRITE_JPEG_QUALITY, 92]),
                                    (f"{stem}_ocr.png", roi, ".png", []),
                                    (f"{stem}_full.jpg", full, ".jpg", [cv2.IMWRITE_JPEG_QUALITY, 90])):
            ok, buf = cv2.imencode(ext, img, opt)
            if not ok:
                raise RuntimeError(f"เข้ารหัสภาพ {name} ไม่ได้")
            (d / name).write_bytes(buf.tobytes())
        (d / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"💾 เก็บภาพ {'GOOD' if passed else 'NG'} → captures\\{d.parent.name}\\{d.name}\\{stem}_*")
    except Exception as e:   # เก็บภาพไม่ได้ต้องไม่ทำให้การตรวจหยุด
        print(f"⚠️ เก็บภาพไม่ได้: {e}")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--standalone", action="store_true", help="ไม่ต่อ gateway แสดงผลอย่างเดียว")
    ap.add_argument("--set-center", action="store_true",
                    help="จดตำแหน่งชิ้นงานตอนนี้เป็นจุดอ้างอิงของเงื่อนไข 'วางถูกตำแหน่ง' แล้วออก")
    args = ap.parse_args()

    roi_file = HERE / "roi.json"
    if not roi_file.exists():
        raise SystemExit("ยังไม่มี roi.json — รัน ocr_roi.py --select ก่อน")
    r = json.loads(roi_file.read_text(encoding="utf-8"))
    rx, ry, rw, rh = r["x"], r["y"], r["w"], r["h"]
    # จุดอ้างอิงของเงื่อนไข "วางถูกตำแหน่ง" — ถ้ายังไม่เคยตั้ง ใช้จุดกลางของกรอบใน roi.json
    expected_center = tuple(CONFIG.get("expected_center") or (rx + rw / 2, ry + rh / 2))
    cam_file = HERE / "cam_settings.json"
    cam_cfg = json.loads(cam_file.read_text(encoding="utf-8")) if cam_file.exists() else {}
    load_index_template()

    # torch (มากับ EasyOCR ที่ลงไว้เทียบ 23 ก.ย.) ต้องโหลดก่อน paddle เสมอ
    # ถ้าโหลด paddle ก่อน DLL ของสองตัวชนกัน → WinError 127 ที่ torch\lib\shm.dll แอปปิดตัวทันที
    # (paddleocr → paddlex → modelscope ดึง torch เข้ามาเองถ้ามีติดตั้งอยู่)
    try:
        import torch  # noqa: F401
    except ImportError:
        pass
    from hik_camera import HikCamera

    ocr, device = load_ocr()

    port = CONFIG.get("web_port", 5000)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"🌐 หน้าจอแสดงผล: http://127.0.0.1:{port}")

    link = None if args.standalone else GatewayLink(CONFIG["gateway_url"])
    print("พร้อมทำงาน" + (" (standalone)" if args.standalone else " — รอ FSM เข้าสถานะ VISION"))

    stop_file = HERE / "STOP"
    stop_file.unlink(missing_ok=True)
    history, sent_this_part, in_vision, last_poll, last_sent, seq = [], False, False, 0.0, "", 0
    sharp_peak = 0
    part_hist = []   # ตำแหน่งชิ้นงานที่หาได้ล่าสุด ใช้หาค่ามัธยฐานกันกรอบสั่น
    # โหมดตัดสิน (28 ก.ย. 2569 — พี่เลี้ยงแนะนำ "ถ่ายภาพนิ่งแล้วค่อยอ่าน" แทนอ่านสดต่อเนื่อง)
    #   snapshot : เข้า VISION → รอเครื่องนิ่ง settle_s → ถ่าย (เฉลี่ย average_frames เฟรม) → ตรวจ 4 ข้อจากภาพนั้น
    #              ไม่ผ่าน = ถ่ายใหม่ ห่าง retry_gap_s ได้รวม max_tries ครั้ง · ครบแล้วยังไม่ผ่าน = ส่ง FAIL
    #   vote     : แบบเดิม — อ่านต่อเนื่อง โหวต min_votes จาก vote_frames เฟรมล่าสุด (ถอยกลับได้ใน ocr_config.json)
    # เหตุ: ภาพสดรวมจังหวะมือกำลังวาง/เทปยังสั่น → "ล้นขอบ 40–115 px" · ผ่าน 1/5 เฟรม (ทดสอบเครื่องจริงเช้า 28 ก.ย.)
    snap_mode = CONFIG.get("decision_mode", "vote") == "snapshot"
    snap_cfg = CONFIG.get("snapshot", {})
    settle_s = float(snap_cfg.get("settle_s", 0.5))
    max_tries = int(snap_cfg.get("max_tries", 3))
    retry_gap_s = float(snap_cfg.get("retry_gap_s", 0.3))
    attempts, next_snap = 0, 0.0
    print(f"โหมดตัดสิน: {'ภาพนิ่ง (รอนิ่ง %.1f s · สูงสุด %d ภาพ)' % (settle_s, max_tries) if snap_mode else 'โหวตหลายเฟรม'}")
    cam, fails, last_try = None, 0, 0.0
    base = {"title": CONFIG.get("title", ""), "subtitle": CONFIG.get("subtitle", ""), "device": device}
    try:
        while not stop_file.exists():
            if link and time.time() - last_poll > 0.1:
                link.request_state()
                last_poll = time.time()
            fsm = (link.state if link.online else "OFFLINE") if link else "STANDALONE"

            # ---------- กล้องหลุด: ต่อใหม่ทุก 2 วินาที แทนที่จะปล่อยให้ทั้งโปรแกรมตาย ----------
            if cam is None:
                if time.time() - last_try >= 2.0:
                    last_try = time.time()
                    try:
                        cam = HikCamera(exposure_us=cam_cfg.get("exposure_us"),
                                        gain_db=cam_cfg.get("gain_db"),
                                        pixel_format=CONFIG.get("pixel_format", "mono8")).open()
                        fails = 0
                        print("📷 เปิดกล้องแล้ว")
                    except Exception as e:
                        cam = None
                        print(f"⚠️ เปิดกล้องไม่ได้: {e}")
                publish({**base, "camera": False, "passed": False, "fields": [], "lines": [], "fsm": fsm,
                         "fsm_online": bool(link and link.online), "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                         "ocr_ms": 0, "reason": "CAMERA RECONNECTING", "last_sent": last_sent, "seq": seq,
                         "brightness": 0, "sharpness": 0, "sharp_peak": sharp_peak, "locate": "-"}, None)
                time.sleep(0.2)
                continue
            # เข้า/ออก VISION — ล้างสถานะของชิ้นก่อนหน้า (ประวัติโหวต · ตำแหน่งมัธยฐาน · จำนวนครั้งที่ถ่าย)
            vis_now = bool(link and link.state == "VISION")
            if vis_now and not in_vision:
                in_vision, sent_this_part, history, attempts = True, False, [], 0
                if snap_mode:
                    part_hist, next_snap = [], time.time() + settle_s
            elif not vis_now:
                in_vision, sent_this_part = False, False
            t_grab = time.time()
            try:
                frame = cam.grab()
                fails = 0
            except Exception as e:
                fails += 1
                print(f"⚠️ ดึงภาพไม่ได้ ({fails}/3): {e}")
                if fails >= 3:
                    try:
                        cam.close()
                    except Exception:
                        pass
                    cam = None
                continue
            # โหมดภาพนิ่ง: ภาพที่เริ่มถ่ายก่อนครบเวลารอนิ่ง ทิ้งเลย ไม่เสียเวลา OCR (ให้ภาพถัดไปเป็นภาพนิ่งเร็วที่สุด)
            if snap_mode and vis_now and not sent_this_part and t_grab < next_snap:
                continue

            # เฉลี่ยหลายเฟรมเพื่อลด noise (ชิ้นงานต้องอยู่นิ่ง) — 1 = ปิด
            n_avg = int(CONFIG.get("average_frames", 1))
            acc = frame.astype(np.float32)
            for _ in range(n_avg - 1):
                acc += cam.grab()
            avg = acc / n_avg

            # Mono12 ให้ค่า 0–4095 ต้องยืดคอนทราสต์ลงเป็น 8 บิตก่อนส่งเข้า OCR
            # วัดจริง 23 ก.ย.: Mono12 + ยืดทั้งภาพ 2–98% อ่านถูก 92% · Mono8 ตรงๆ 67%
            if CONFIG.get("pixel_format", "mono8") == "mono12":
                lo_p, hi_p = CONFIG.get("stretch_percentiles", [2, 98])
                lo, hi = np.percentile(avg, lo_p), np.percentile(avg, hi_p)
                frame = np.clip((avg - lo) * 255.0 / max(1.0, hi - lo), 0, 255).astype(np.uint8)
            else:
                frame = avg.astype(np.uint8)

            # ตำแหน่ง carrier เทียบเส้น index — ใช้ภาพดิบเต็มเฟรม (avg) ก่อนครอป · ข้ามเองตอนอยู่ VISION
            carrier_update(avg, fsm)

            # หาตัวชิ้นงานแล้วครอปให้อยู่กลางกรอบ ถ้าหาไม่เจอให้ใช้กรอบตายตัวจาก roi.json
            ac = CONFIG.get("auto_center", {})
            if args.set_center:
                # ตั้งจุดอ้างอิงใหม่: ชิ้นงานอาจย้ายไปไกลจากจุดเดิม จึงยังไม่ตัดวงที่ไกลทิ้ง
                part = find_part(frame, (rx + rw / 2, ry + rh / 2)) if ac.get("enabled") else None
            else:
                part = find_part(frame, expected_center) if ac.get("enabled") else None
                # กันภาพแกว่ง (24 ก.ย.): บางเฟรม Hough ไปจับวงที่ขอบเทปด้านขวาแทนตัวชิ้นงาน
                # (เคยเลือกวงจากจุดกลางของ roi.json ซึ่งเก่าตั้งแต่ก่อนย้ายกล้อง วงจริงกับวงผิดห่างพอๆ กัน)
                # ตัดวงที่ไกลจากจุดอ้างอิงเกิน max_jump_px ทิ้ง — ชิ้นงานที่วางเยื้องจริงแต่ไม่เกินนี้
                # ยังหาเจอ และเงื่อนไขข้อ 2 ตัดสินว่าวางผิดตามปกติ
                max_jump = float(ac.get("max_jump_px", 300))
                if part and np.hypot(part[0] - expected_center[0], part[1] - expected_center[1]) > max_jump:
                    part = None
                # ใช้ค่ามัธยฐานของ 5 เฟรมล่าสุด ลดการสั่นของกรอบ — ตัดเฟรมหลุด 1–2 เฟรมทิ้งได้เอง
                # (ถ้าชิ้นงานย้ายจริง ค่ามัธยฐานตามทันภายใน 3 เฟรม) ห้ามเริ่มนับใหม่เมื่อตำแหน่งกระโดด
                # เคยลองแล้ว 24 ก.ย. — ทำให้เฟรมหลุดเฟรมเดียวหลุดผ่านไปแสดงผลได้
                # โหมดภาพนิ่งตอนตัดสิน: ใช้ตำแหน่งจากภาพนี้ภาพเดียว ไม่เอาภาพก่อนเครื่องนิ่งมาเฉลี่ย
                if part and not (snap_mode and vis_now):
                    part_hist = (part_hist + [part])[-5:]
                    part = tuple(int(v) for v in np.median(np.array(part_hist), axis=0))
            if part:
                roi = crop_centered(frame, part, float(ac.get("crop_scale", 2.4)))
                raw_roi = crop_centered(avg, part, float(ac.get("crop_scale", 2.4)))
                locate = f"auto ({part[0]},{part[1]}) r={part[2]}"
            else:
                roi = frame[ry:ry + rh, rx:rx + rw]
                raw_roi = avg[ry:ry + rh, rx:rx + rw]
                locate = "กรอบตายตัว" if not ac.get("enabled") else "หาชิ้นงานไม่เจอ ใช้กรอบตายตัว"
            face = None
            if part:   # ตำแหน่งหน้าชิ้นงานในพิกัดของกรอบที่ครอป (crop_centered ตัดที่ขอบภาพได้)
                half = int(part[2] * float(ac.get("crop_scale", 2.4)) / 2)
                face = (part[0] - max(0, part[0] - half), part[1] - max(0, part[1] - half), part[2])
            view = human_view(raw_roi, face)   # ภาพให้คนดู — roi ด้านล่างคือภาพที่ส่งเข้า OCR (ห้ามสลับกัน)
            if ROTATE[CONFIG["rotate"]] is not None:
                roi = cv2.rotate(roi, ROTATE[CONFIG["rotate"]])
                view = cv2.rotate(view, ROTATE[CONFIG["rotate"]])
            # ตัวเลขคุณภาพภาพ ไว้ดูตอนหมุนเลนส์ — sharpness เทียบกับค่าสูงสุดที่เคยวัดได้ (peak)
            brightness = round(float(roi.mean()))
            sharpness = round(float(cv2.Laplacian(roi, cv2.CV_64F).var()))
            sharp_peak = max(sharp_peak, sharpness)

            t = time.time()
            raw_lines = read_lines(ocr, roi)
            ocr_ms = round((time.time() - t) * 1000)
            lines = [(tx, cf) for tx, cf, _ in raw_lines]
            text_ok, text_fields, text_reason = check_fields(lines)

            ori = CONFIG.get("orientation", {})
            if ori.get("enabled"):
                ori_status, ori_text, _ = check_orientation(ocr, roi, raw_lines)
            else:
                ori_status, ori_text = "ok", "ไม่ได้ตรวจทิศทาง"

            if args.set_center:
                if part is None:
                    print("ยังหาชิ้นงานไม่เจอ ลองใหม่...")
                    continue
                cfg_path = HERE / "ocr_config.json"
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
                data["expected_center"] = [part[0], part[1]]
                cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"บันทึกจุดอ้างอิงเป็น ({part[0]},{part[1]}) ลง ocr_config.json แล้ว")
                break

            # ผลตัดสินหลักมาจากเงื่อนไข 4 ข้อ ส่วนผลอ่านทีละช่อง (BRAND/PART NR/...) แสดงเป็นรายละเอียด
            pocket = pocket_check(frame, part) if part else None
            passed, fields, reason = check_conditions(
                part, expected_center, lines, text_ok, text_reason, ori_status, ori_text, pocket)
            fields = fields + [{**f, "name": "· " + f["name"]} for f in text_fields]

            # โหวตจากหลายเฟรม: OCR อ่านถูกราวครึ่งหนึ่งของเฟรม และค่าที่ผิดกระจายไปคนละแบบ
            # จึงนับว่าผ่านถ้ามีเฟรมที่ผ่านอย่างน้อย min_votes ครั้งจาก vote_frames เฟรมล่าสุด
            votes = int(CONFIG.get("vote_frames", CONFIG.get("stable_reads", 2)))
            need = int(CONFIG.get("min_votes", votes))
            history = (history + [passed])[-votes:]
            stable = len(history) == votes
            voted_pass = sum(history) >= need

            if vis_now:
                # (สถานะเข้า/ออก VISION ล้างไว้แล้วตอนต้นรอบ — ก่อนถ่ายภาพ)
                # เฟรมแรกหลังเข้า VISION ในโหมดโหวตมี history ยาว 1 → stable เป็น False เอง ไม่ตัดสินด้วยเฟรมเดียว
                if not sent_this_part:
                    print(f"[VISION] {'PASS' if passed else 'FAIL'} {reason} | read={lines} "
                          f"| step_allowed={link.step_allowed} " + (f"ภาพนิ่ง {attempts + 1}/{max_tries}" if snap_mode else f"stable={stable}"))
                decide = False
                if link.step_allowed and not sent_this_part:
                    if snap_mode:
                        attempts += 1
                        if passed or attempts >= max_tries:
                            decide = True
                            reason = f"{reason} · ภาพนิ่ง {attempts}/{max_tries}"
                        else:
                            next_snap = time.time() + retry_gap_s   # ไม่ผ่าน — ถ่ายใหม่ (อาจมีอะไรบังชั่วขณะ)
                    elif stable:
                        decide = True
                        passed = voted_pass   # ตัดสินจากผลโหวตหลายเฟรม ไม่ใช่เฟรมเดียว
                        reason = f"{reason} · โหวต {sum(history)}/{len(history)} เฟรม"
                if decide:
                    ok = link.send_decision(passed, {"reason": reason, "source": "hikrobot-ocr",
                                                     "fields": {f["name"]: f["value"] for f in fields}})
                    word = "PASS" if passed else "FAIL"
                    last_sent = f"{word} at {time.strftime('%H:%M:%S')}" + ("" if ok else " (NOT accepted)")
                    print(f"📡 ส่ง {word} ให้ FSM {'แล้ว' if ok else 'แต่ gateway ไม่รับ'} — {reason}")
                    # 27 ก.ย. 2569: gateway ปฏิเสธ "ไม่พบชิ้นงาน" ช่วงแรกเพื่อรอคนวางชิ้นงาน (NO_PART_WAIT_S)
                    # ไม่รับ = ตัดสินใหม่จากภาพชุดใหม่ (ล้างโหวต/นับครั้งใหม่) · เดิมส่งครั้งเดียวต่อการเข้า VISION แล้ว FSM จะค้างรอตลอด
                    sent_this_part = ok
                    if ok:
                        set_decision(view, {"passed": bool(passed), "time": time.strftime("%H:%M:%S"),
                                            "pocket": link.pocket, "reason": reason,
                                            "fields": [{k: f.get(k) for k in ("name", "ok", "value", "required")}
                                                       for f in fields],
                                            "lines": [t_ for t_, _ in lines]})
                        save_capture(passed, view, roi, frame, {
                            "time": time.strftime("%Y-%m-%d %H:%M:%S"), "pocket": link.pocket, "passed": passed,
                            "reason": reason, "mode": "snapshot" if snap_mode else "vote", "locate": locate,
                            "fields": fields, "lines": [[t_, round(c_, 4)] for t_, c_ in lines],
                            "brightness": brightness, "sharpness": sharpness})
                    else:
                        history, attempts = [], 0
                        next_snap = time.time() + retry_gap_s

            seq += 1
            publish({**base, "camera": True, "passed": passed, "fields": fields,
                     "lines": [[t_, round(c_, 4)] for t_, c_ in lines], "fsm": fsm,
                     "fsm_online": bool(link and link.online) or not link,
                     "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "ocr_ms": ocr_ms, "reason": reason,
                     "last_sent": last_sent, "seq": seq,
                     "brightness": brightness, "sharpness": sharpness, "sharp_peak": sharp_peak,
                     "locate": locate}, view)
    except KeyboardInterrupt:
        pass
    finally:
        if cam is not None:
            cam.close()
        server.shutdown()
        stop_file.unlink(missing_ok=True)
        print("ปิดแอปแล้ว (ปิดกล้องเรียบร้อย)")


if __name__ == "__main__":
    main()
