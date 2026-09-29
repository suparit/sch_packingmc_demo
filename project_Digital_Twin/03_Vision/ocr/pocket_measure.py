"""วัดตำแหน่งหลุม carrier จากภาพกล้อง — ใช้ร่วมกันระหว่าง feed_pocket_view.py (:5050) กับ app_vision_ocr.py (:5000)

แยกออกมาจาก feed_pocket_view.py 25 ก.ย. 2569 (โค้ดเดิม ไม่ได้เปลี่ยนวิธีวัด) — วันเดียวกันใช้วัด feed ถึงเส้น 10 หลุม
9/10 หลุมห่างเส้นไม่เกิน ±0.13 mm (06_Docs/test_evidence/2026-09-25_feed_to_line_10pockets.md)

พิกัดทั้งหมดเป็นพิกัดภาพเต็ม 2592x1944 ของกล้อง HIKROBOT ตำแหน่งติดตั้ง 25 ก.ย. — ย้ายกล้องแล้วต้องวัดใหม่
"""
import cv2
import numpy as np

FULL_SHAPE = (1944, 2592)     # (สูง, กว้าง) ที่พิกัดด้านล่างใช้ได้ · ROI ค้างในกล้องจะได้ภาพเล็กกว่านี้
# วัดใหม่ 28 ก.ย. 2569 — กล้องเลื่อนไปจากวันที่ 25 ราว 120 px (เทปค่อนซ้ายของภาพ ~8 mm)
# เดิม 25 ก.ย.: POCKET_X = (560, 1580) · HOLE_COLS = ((110, 180), (1925, 2000))
# ตอนนี้: ผนังหลุม x≈325–1525 · รูสเตอร์ขวา ≈1805–1875 · รูซ้ายโดนขอบภาพตัดครึ่ง (0–58) · ขอบเทปขวา ≈1915
POCKET_X = (440, 1460)        # แถบแนวตั้งในหลุม (px เต็มภาพ) — ตำแหน่งเทียบผนังหลุมเท่าของเดิม
HOLE_COLS = ((0, 58), (1805, 1875))   # แถวรูสเตอร์ซ้าย (ครึ่งรู)/ขวา
VIEW_X = (0, 1940)            # ช่วงที่ครอปไปแสดงบนหน้าเว็บ — ตัดแผ่นมืดทางขวาที่ไม่ใช่เทปออก ให้เทปอยู่กลางภาพ
HOLE_MM = 4.0                 # รูสเตอร์ห่างกัน 4 mm = ไม้บรรทัดในภาพ


def pocket_edge(img, near=None, window=None):
    """แถวของขอบหลุม = จุดที่ความสว่างเปลี่ยนแรงสุดตามแนวเทป · near/window = ค้นใกล้ค่าเดิม"""
    band = img[:, POCKET_X[0]:POCKET_X[1]].astype(np.float32)
    prof = cv2.GaussianBlur(band, (0, 0), 3).mean(axis=1)
    g = np.abs(np.diff(prof))
    if near is not None and window:
        lo, hi = max(0, int(near - window)), min(len(g), int(near + window))
        return lo + int(np.argmax(g[lo:hi]))
    return int(np.argmax(g))


def hole_pitch_px(img):
    """ระยะรูสเตอร์เป็น px จาก autocorrelation ของแถวรู เลือกฝั่งที่ชัดกว่า"""
    best = (0.0, None)
    for x0, x1 in HOLE_COLS:
        col = cv2.GaussianBlur(img[:, x0:x1].astype(np.float32), (0, 0), 2).mean(axis=1)
        c = col - col.mean()
        ac = np.correlate(c, c, "full")[len(c) - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        lag = int(np.argmax(ac[100:400])) + 100
        # ปรับจุดยอดแบบพาราโบลาให้ละเอียดกว่า 1 px
        y0, y1, y2 = ac[lag - 1], ac[lag], ac[lag + 1]
        d = (y0 - y2) / (2 * (y0 - 2 * y1 + y2)) if (y0 - 2 * y1 + y2) != 0 else 0.0
        if y1 > best[0]:
            best = (float(y1), float(lag + d))   # float ของ Python — np.float32 แปลงเป็น JSON ไม่ได้
    return best[1]


# ---------------- หาตำแหน่งด้วย template matching (A) + รูสเตอร์ (B) ----------------
# เดิมหา "ขอบที่ชัดที่สุดในช่วงค้น" แล้วจับผิดเส้นในหลุม (ในหลุมมีขอบด้านในหลายเส้น ห่างกัน ~140 px)
# 25 ก.ย.: หลุม 4–5 วัดได้ +3.20 mm เท่ากันเป๊ะทั้งที่พัลส์ต่างกัน -> ค่าที่เรียนรู้เพี้ยนตาม
# ตอนนี้: เก็บภาพแถบหลุมรอบจุดอ้างอิงเป็นแม่แบบ แล้วหาตำแหน่งที่ "ทั้งรูปร่าง" ตรงกันที่สุด (A)
# จากนั้นเกลาด้วยแถวรูสเตอร์ที่คมกว่า ในช่วง ±TPL_HOLE_W ซึ่งแคบกว่าครึ่งระยะรู (~89 px) จึงไม่จับผิดรู (B)
TPL_H = 150          # ครึ่งความสูงแม่แบบแถบหลุม (px)
TPL_HOLE_H = 110     # ครึ่งความสูงแม่แบบแถวรูสเตอร์ (~1.2 ระยะรู)
TPL_HOLE_W = 60      # ช่วงค้นของขั้นเกลาด้วยรู (px) — ต้องน้อยกว่าครึ่งระยะรู


def make_template(img, y):
    y = int(round(y))
    if y - TPL_H < 0 or y + TPL_H > img.shape[0]:
        raise RuntimeError(f"จุดอ้างอิงชิดขอบภาพเกินไป (y={y}) — เลือกแถวที่ห่างขอบบน/ล่างของภาพมากกว่านี้ หรือเลื่อนเทปให้หลุมอยู่กลางภาพ")
    f = img.astype(np.float32)
    return {"y": y,
            "pocket": f[y - TPL_H:y + TPL_H, POCKET_X[0]:POCKET_X[1]].copy(),
            "holes": [f[max(0, y - TPL_HOLE_H):y + TPL_HOLE_H, x0:x1].copy() for x0, x1 in HOLE_COLS]}


def _match(img, tpl, x0, x1, half, pred, window):
    """หาแถวกลางของแม่แบบในแถบ [x0:x1] รอบ pred ±window · คืน (y, คะแนน 0–1) · ละเอียดกว่า 1 px ด้วยพาราโบลา"""
    top = int(max(0, pred - half - window))
    bot = int(min(img.shape[0], pred + half + window))
    strip = img[top:bot, x0:x1].astype(np.float32)
    if strip.shape[0] < tpl.shape[0] + 3:
        return None, 0.0
    res = cv2.matchTemplate(strip, tpl, cv2.TM_CCOEFF_NORMED)[:, 0]
    i = int(np.argmax(res))
    d = 0.0
    if 0 < i < len(res) - 1:
        a, b, c = res[i - 1], res[i], res[i + 1]
        den = a - 2 * b + c
        d = float((a - c) / (2 * den)) if den != 0 else 0.0
    return top + i + d + tpl.shape[0] / 2, float(res[i])


def locate(img, tpl, pred, window):
    """(A) รูปร่างหลุม -> ตำแหน่งหยาบ · (B) แถวรูสเตอร์ -> เกลาให้ละเอียด · คืน (y, คะแนน A, คะแนน B)"""
    ya, sa = _match(img, tpl["pocket"], POCKET_X[0], POCKET_X[1], TPL_H, pred, window)
    if ya is None:
        raise RuntimeError("ช่วงค้นหลุดขอบภาพ — เลื่อนจุดอ้างอิงเข้ามากลางภาพ")
    best = (ya, sa, 0.0)
    ys, ws = [], []
    for (x0, x1), ht in zip(HOLE_COLS, tpl["holes"]):
        yb, sb = _match(img, ht, x0, x1, ht.shape[0] / 2, ya, TPL_HOLE_W)
        if yb is not None and sb > 0.6 and abs(yb - ya) < TPL_HOLE_W:
            ys.append(yb); ws.append(sb)
    if ys:
        best = (float(np.average(ys, weights=ws)), sa, float(max(ws)))
    return best


def mid_edge(img):
    """ขอบหลุมที่ชัดที่สุด เฉพาะช่วงกลางภาพ (เผื่อที่ให้แม่แบบ + ช่วงค้นไม่หลุดขอบ)"""
    lo, hi = TPL_H + 150, img.shape[0] - TPL_H - 150
    return pocket_edge(img, near=(lo + hi) / 2, window=(hi - lo) / 2)


# ---------------- เก็บ/โหลดตำแหน่ง index (แม่แบบหลุม) ลงไฟล์ ----------------
def save_template(path, tpl):
    np.savez_compressed(path, y=tpl["y"], pocket=tpl["pocket"], hole0=tpl["holes"][0], hole1=tpl["holes"][1])


def load_template(path):
    d = np.load(path)
    return {"y": int(d["y"]), "pocket": d["pocket"], "holes": [d["hole0"], d["hole1"]]}
