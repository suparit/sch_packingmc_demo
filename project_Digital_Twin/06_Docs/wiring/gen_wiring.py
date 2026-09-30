"""
สร้างภาพ wiring ของชุดทดสอบ (test rig) เป็น SVG แบบภาพอุปกรณ์ + สายสี

รัน:  python 06_Docs/wiring/gen_wiring.py   (จาก root ของ repo)
ได้:  06_Docs/wiring/test_rig_wiring.svg   (เขียนข้างไฟล์สคริปต์นี้เสมอ)
      test_rig_wiring.png = ภาพ render ของ SVG เดียวกัน (สร้างด้วยมือ — แก้ SVG แล้วต้อง export PNG ใหม่เอง)

ย้ายมาจาก dt-taping-dev/docs/wiring/ เมื่อ 29 ก.ย. 2569 — ที่นี่คือฉบับทางการของผัง wiring ชุดทดสอบ
ข้อมูลการต่อสายทั้งหมดมาจาก board_protocol.md 9.1.1, HANDOFF.md และ tools/feed_pulse_test.py (path ใน dt-taping-dev/)
ส่วนที่ repo ไม่ได้บันทึก (ไฟเลี้ยงไดรเวอร์) วาดเป็นเส้นประสีแดง
ยังไม่วาดเซนเซอร์ของกระบอกสูบ (บน/ล่าง) และสายสัญญาณอินพุต — user สั่งตัดออก 2026-09-29
"""
from pathlib import Path

W, H = 1600, 1010
FONT = "'Leelawadee UI','Tahoma',sans-serif"

C_24V = "#8d4a1f"      # น้ำตาล  +24V
C_0V = "#1f5fbf"       # ฟ้า     0V
C_OUT = "#ef7d00"      # ส้ม     เอาต์พุต 24V จากบอร์ด
C_DATA = "#8a8f98"     # เทา     LAN / USB
C_AIR = "#9fd0ef"      # ฟ้าอ่อน ท่อลม
C_UNK = "#d32f2f"      # แดง     ยังไม่ยืนยัน
C_MOTOR = "#5a5a5a"

out = []


def add(s):
    out.append(s)


def text(x, y, s, size=13, color="#222", anchor="start", weight="normal"):
    add(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{color}" '
        f'text-anchor="{anchor}" font-weight="{weight}">{s}</text>')


def wire(d, color, width=3.5, dash=None):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
        f'stroke-linecap="round" stroke-linejoin="round"{da}/>')


def dot(x, y, color):
    add(f'<circle cx="{x}" cy="{y}" r="5.5" fill="{color}"/>')


def terminal(cx, cy, size=24):
    h = size / 2
    add(f'<rect x="{cx-h}" y="{cy-h}" width="{size}" height="{size}" rx="3" fill="#e9e9e9" stroke="#555" stroke-width="1.2"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="{h-5}" fill="#b9b9b9" stroke="#666" stroke-width="1"/>')
    add(f'<line x1="{cx-h+7}" y1="{cy+h-7}" x2="{cx+h-7}" y2="{cy-h+7}" stroke="#555" stroke-width="1.6"/>')


# ---------------------------------------------------------------- พิกัดหลัก
RAIL24, RAIL0 = 440, 462            # ราง +24V / 0V ด้านบน
TERM_Y = 375                        # แถวขั้วบนบอร์ด I/O
T_BOT = TERM_Y + 13

PWR = {"+24": 540, "0V": 568}
IN = [620, 648, 676, 704]           # 8.6, 8.7, ?, ?
OP0 = [780 + 26 * i for i in range(8)]
OP1 = [1030 + 26 * i for i in range(8)]

VALVES = {"A": 760, "B": 910, "C": 1060}
DRV_X, DRV_Y, DRV_W, DRV_H = 1215, 540, 235, 220
DRV_T = {"PUL+": 1237, "PUL−": 1263, "DIR+": 1289, "DIR−": 1315,
         "ENA+": 1341, "ENA−": 1367, "V+": 1400, "GND": 1426}
MOT_T = {"A+": 1260, "A−": 1286, "B+": 1312, "B−": 1338}

add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')

text(40, 48, "ผังต่อสาย (Wiring) ชุดทดสอบ Digital Twin — เครื่อง Taping", 26, "#111", weight="bold")
text(40, 76, "บอร์ด I/O (Modbus TCP) · โซลินอยด์กระบอกซีล · มอเตอร์ feed  —  ตามที่บันทึกใน repo ณ 29 ก.ย. 2026", 15, "#555")

# ================================================================ สายไฟ (วาดก่อน อุปกรณ์ทับปลายสาย)
# AC เข้า PSU
wire("M120 261 V330 H92", C_24V, 2.5)
wire("M160 261 V348 H92", C_0V, 2.5)

# ราง +24V / 0V จาก PSU
wire(f"M370 261 V{RAIL24} H1440", C_24V)
wire(f"M250 261 V{RAIL0} H1440", C_0V)

# ไฟเลี้ยงบอร์ด
wire(f"M{PWR['+24']} {T_BOT} V{RAIL24}", C_24V)
wire(f"M{PWR['0V']} {T_BOT} V{RAIL0}", C_0V)
dot(PWR['+24'], RAIL24, C_24V)
dot(PWR['0V'], RAIL0, C_0V)

# เอาต์พุต OP1.0/.1/.2 -> ขั้ว + ของคอยล์วาล์ว A/B/C · ขั้ว − ลง 0V
jog = {"A": 410, "B": 418, "C": 426}
for i, (name, vx) in enumerate(VALVES.items()):
    wire(f"M{OP1[i]} {T_BOT} V{jog[name]} H{vx+25} V540", C_OUT)
    wire(f"M{vx+10} 540 V{RAIL0}", C_0V)
    dot(vx + 10, RAIL0, C_0V)

# OP1.4 -> PUL+ · PUL− -> 0V
wire(f"M{OP1[4]} {T_BOT} V500 H{DRV_T['PUL+']} V{DRV_Y}", C_OUT)
wire(f"M{DRV_T['PUL−']} {DRV_Y} V{RAIL0}", C_0V)
dot(DRV_T['PUL−'], RAIL0, C_0V)
# ไฟเลี้ยงไดรเวอร์: repo ไม่ได้บันทึก -> เส้นประ
wire(f"M{DRV_T['V+']} {DRV_Y} V{RAIL24}", C_24V, 3, "7 6")
wire(f"M{DRV_T['GND']} {DRV_Y} V{RAIL0}", C_0V, 3, "7 6")
text(1436, 506, "ไฟเลี้ยง ?", 13, C_UNK, weight="bold")

# ไดรเวอร์ -> มอเตอร์
depth = {"A+": 814, "A−": 806, "B+": 798, "B−": 790}
for k, x in MOT_T.items():
    wire(f"M{x} {DRV_Y+DRV_H} V{depth[k]} H1472", C_MOTOR, 2.5)
wire("M1525 882 V922", C_UNK, 2.5, "6 5")
text(1525, 942, "สาย encoder ยังไม่ต่อ", 12, C_UNK, "middle")

# ท่อลม: เมนลม + วาล์ว -> กระบอก
wire("M790 675 H1190", C_AIR, 5)
for vx in VALVES.values():
    wire(f"M{vx+100} 675 V634", C_AIR, 5)
    wire(f"M{vx+55} 634 V706", C_AIR, 5)
    wire(f"M{vx+80} 634 V695 H{vx+115} V860 H{vx+95}", C_AIR, 5)

# LAN / USB
wire("M1300 170 H1325 V238 H1350", C_DATA, 6)
wire("M1420 247 V300", C_DATA, 5)
wire("M1520 247 V300", C_DATA, 5)

# ================================================================ อุปกรณ์
# ปลั๊ก AC
add('<rect x="46" y="318" width="46" height="42" rx="6" fill="#f2f2f2" stroke="#444" stroke-width="1.5"/>')
add('<rect x="30" y="326" width="16" height="6" fill="#999"/><rect x="30" y="346" width="16" height="6" fill="#999"/>')
text(62, 382, "AC 220V", 12, "#444", "middle")

# Power supply 24V
add('<rect x="90" y="120" width="320" height="160" rx="6" fill="#d9dde1" stroke="#555" stroke-width="1.5"/>')
for i in range(14):
    add(f'<rect x="{110+i*20}" y="132" width="10" height="36" rx="2" fill="#b7bdc3"/>')
text(250, 196, "POWER SUPPLY", 17, "#333", "middle", "bold")
text(250, 218, "24V DC", 15, "#333", "middle")
for lbl, x in (("L", 120), ("N", 160), ("⏚", 200), ("−V", 250), ("−V", 290), ("+V", 330), ("+V", 370)):
    text(x, 244, lbl, 11, "#333", "middle", "bold")
    terminal(x, 261)

# บอร์ด I/O
add('<rect x="500" y="110" width="760" height="290" rx="10" fill="#1f6f43" stroke="#0f3d24" stroke-width="2"/>')
for hx, hy in ((514, 124), (1246, 124), (514, 386), (1246, 386)):
    add(f'<circle cx="{hx}" cy="{hy}" r="5" fill="#cfd8dc"/>')
add('<rect x="540" y="140" width="100" height="100" rx="4" fill="#1b1b1b"/>')
for i in range(8):
    add(f'<rect x="{546+i*12}" y="132" width="5" height="8" fill="#bbb"/><rect x="{546+i*12}" y="240" width="5" height="8" fill="#bbb"/>')
text(590, 196, "STM32", 15, "#ddd", "middle", "bold")
text(680, 162, "บอร์ด I/O  SCH_XPLCV1", 20, "#fff", weight="bold")
text(680, 188, "192.168.0.100 · Modbus TCP พอร์ต 502", 15, "#e8f5e9")
text(680, 212, "FW:133 · ห้ามแฟลชทับ (ไม่มี source)", 13, "#ffe082")
# RJ45
add('<rect x="1255" y="148" width="46" height="44" rx="3" fill="#cfd4d8" stroke="#555" stroke-width="1.5"/>')
add('<rect x="1266" y="158" width="26" height="24" fill="#2b2b2b"/>')
text(1312, 162, "LAN", 11, "#555")

def term_group(xs, title, labels, leds=True):
    x0, x1 = xs[0] - 14, xs[-1] + 14
    add(f'<rect x="{x0}" y="{TERM_Y-17}" width="{x1-x0}" height="34" rx="3" fill="#2e7d32" stroke="#0f3d24"/>')
    text((x0 + x1) / 2, 300, title, 12, "#fff", "middle", "bold")
    for x, lbl in zip(xs, labels):
        if leds:
            add(f'<circle cx="{x}" cy="{318}" r="4.5" fill="#9e9e9e" stroke="#333"/>')
        text(x, 348, lbl, 11, "#fff", "middle")
        terminal(x, TERM_Y)

term_group([PWR["+24"], PWR["0V"]], "POWER", ["+24", "0V"], leds=False)
term_group(IN, "INPUT", ["8.6", "8.7", "–", "–"])
term_group(OP0, "OP0 · coil 64 · ไฟสถานะ FSM", [str(i) for i in range(8)])
term_group(OP1, "OP1 · coil 72", [str(i) for i in range(8)])

# PC + จอ HMI + กล้อง
add('<rect x="1372" y="110" width="176" height="118" rx="6" fill="#2b2f36"/>')
add('<rect x="1380" y="118" width="160" height="100" fill="#3d7bd9"/>')
text(1460, 156, "PC", 18, "#fff", "middle", "bold")
text(1460, 178, "gateway + rust_bridge", 12, "#fff", "middle")
text(1460, 198, "192.168.0.55", 12, "#fff", "middle")
add('<path d="M1352 228 H1568 L1580 248 H1340 Z" fill="#9aa3ad" stroke="#555"/>')
text(1460, 268, "LAN ผ่าน USB-LAN (อีเทอร์เน็ต 3)", 12, "#444", "middle")
add('<rect x="1360" y="300" width="100" height="70" rx="4" fill="#1f6f43"/>')
add('<rect x="1368" y="306" width="84" height="56" fill="#0d2b52"/>')
text(1410, 339, "HMI", 14, "#fff", "middle", "bold")
text(1410, 390, "จอ HMI · USB COM7", 12, "#444", "middle")
add('<rect x="1490" y="300" width="60" height="60" rx="4" fill="#222"/>')
add('<circle cx="1520" cy="330" r="17" fill="#555" stroke="#999" stroke-width="2"/><circle cx="1520" cy="330" r="7" fill="#111"/>')
text(1520, 390, "Camera · COM10", 12, "#444", "middle")

# วาล์ว + กระบอก
for name, vx in VALVES.items():
    add(f'<rect x="{vx+8}" y="538" width="5" height="10" fill="#888"/><rect x="{vx+23}" y="538" width="5" height="10" fill="#888"/>')
    add(f'<rect x="{vx}" y="548" width="35" height="94" rx="3" fill="#333"/>')
    text(vx + 17, 600, "SOL", 11, "#fff", "middle", "bold")
    add(f'<rect x="{vx+35}" y="560" width="75" height="70" rx="3" fill="#cfd8dc" stroke="#555" stroke-width="1.2"/>')
    add(f'<path d="M{vx+110} 580 l8 5 l-8 5 l8 5 l-8 5 l8 5" fill="none" stroke="#555" stroke-width="1.5"/>')
    text(vx + 72, 590, f"วาล์ว {name}", 13, "#263238", "middle", "bold")
    text(vx + 72, 610, "+ / −", 11, "#455a64", "middle")
    for px in (vx + 55, vx + 80, vx + 100):
        add(f'<rect x="{px-5}" y="630" width="10" height="8" fill="#888"/>')
    cx = vx + 65
    add(f'<rect x="{vx+31}" y="704" width="68" height="14" rx="3" fill="#90a4ae"/>')
    add(f'<rect x="{vx+35}" y="712" width="60" height="168" fill="#e0e5e8" stroke="#78909c" stroke-width="1.5"/>')
    add(f'<rect x="{vx+31}" y="874" width="68" height="14" rx="3" fill="#90a4ae"/>')
    add(f'<rect x="{cx-6}" y="888" width="12" height="57" fill="#b0bec5" stroke="#78909c"/>')
    add(f'<rect x="{cx-15}" y="945" width="30" height="13" rx="2" fill="#78909c"/>')
    label = "Cylinder C (INIT)" if name == "C" else f"กระบอกซีล {name}"
    text(cx, 990, label, 13, "#263238", "middle", "bold")

# ไดรเวอร์ E-EDR57A
add(f'<rect x="{DRV_X}" y="{DRV_Y}" width="{DRV_W}" height="{DRV_H}" rx="6" fill="#2b2b2b" stroke="#111"/>')
for k, x in DRV_T.items():
    terminal(x, DRV_Y + 14, 22)
    text(x, DRV_Y + 40, k, 10, "#fff", "middle")
for i in range(9):
    add(f'<rect x="{DRV_X+20+i*22}" y="614" width="12" height="30" rx="2" fill="#3a3a3a"/>')
text(DRV_X + DRV_W / 2, 606, "DIR / ENA / ALM ไม่ได้ต่อ", 12, "#ffcc80", "middle")
text(DRV_X + DRV_W / 2, 666, "MISUMI E-EDR57A", 15, "#fff", "middle", "bold")
add(f'<rect x="{DRV_X+50}" y="676" width="136" height="22" rx="2" fill="#c62828"/>')
for i in range(8):
    up = i == 5
    add(f'<rect x="{DRV_X+56+i*16}" y="{680 if up else 688}" width="9" height="8" fill="#fff"/>')
text(DRV_X + DRV_W / 2, 714, "DIP: SW6 = ON (open loop)", 11, "#ddd", "middle")
for k, x in MOT_T.items():
    terminal(x, DRV_Y + DRV_H - 14, 22)
    text(x, DRV_Y + DRV_H - 30, k, 10, "#fff", "middle")

# มอเตอร์
add('<rect x="1472" y="770" width="108" height="108" rx="8" fill="#4a4f55" stroke="#222" stroke-width="1.5"/>')
for hx, hy in ((1484, 782), (1568, 782), (1484, 866), (1568, 866)):
    add(f'<circle cx="{hx}" cy="{hy}" r="5" fill="#222"/>')
add('<circle cx="1526" cy="824" r="26" fill="#6b7178" stroke="#222"/><circle cx="1526" cy="824" r="7" fill="#ccc"/>')
text(1526, 760, "มอเตอร์ E-57ESTM02", 12, "#333", "middle", "bold")

# ================================================================ ป้ายราง + คำอธิบาย
text(382, 432, "+24V", 14, C_24V, weight="bold")
text(262, 482, "0V", 14, C_0V, weight="bold")

add('<rect x="30" y="500" width="425" height="470" rx="8" fill="#fafafa" stroke="#bbb"/>')
text(48, 530, "สีสาย", 16, "#111", weight="bold")
legend = [
    (C_24V, None, 3.5, "+24V DC"),
    (C_0V, None, 3.5, "0V (คอมมอน)"),
    (C_OUT, None, 3.5, "เอาต์พุต 24V จากบอร์ด (สั่งงาน)"),
    (C_DATA, None, 6, "สาย LAN / USB"),
    (C_AIR, None, 5, "ท่อลม"),
    (C_UNK, "7 5", 3, "ยังไม่ยืนยัน / repo ไม่ได้บันทึก"),
]
y = 556
for color, dash, w, lbl in legend:
    wire(f"M50 {y-5} H100", color, w, dash)
    text(114, y, lbl, 13, "#333")
    y += 24
y += 8
text(48, y, "เอาต์พุต", 16, "#111", weight="bold")
rows = [
    ("OP1.0", "โซลินอยด์ A → กระบอกซีล A"),
    ("OP1.1", "โซลินอยด์ B → กระบอกซีล B"),
    ("OP1.2", "วาล์ว Cylinder C (ปุ่ม INIT)"),
    ("OP1.4", "PUL+ ไดรเวอร์มอเตอร์ feed"),
    ("OP1.3,5–7", "ว่าง / ยังไม่รู้ว่าต่ออะไร"),
    ("OP0.0–3", "ไฟ FEED / SEAL / TAKEUP / ALARM"),
]
y += 24
for a, b in rows:
    text(48, y, a, 13, "#111", weight="bold")
    text(150, y, b, 13, "#333")
    y += 21
y += 10
text(48, y, "หมายเหตุ", 16, "#111", weight="bold")
y += 22
for s in ("• ตำแหน่งขั้วบนบอร์ด/ไดรเวอร์เป็นภาพแทน ไม่ใช่ layout จริง",
          "• เส้นตัดกันโดยไม่มีจุด = ไม่ได้ต่อกัน",
          "• วาล์วเป็นโซลินอยด์เดี่ยว สปริงดันกลับ · DOWN = จ่ายไฟ"):
    text(48, y, s, 12, "#444")
    y += 19

add("</svg>")

dst = Path(__file__).with_name("test_rig_wiring.svg")
dst.write_text("\n".join(out), encoding="utf-8")
print(f"wrote {dst} ({dst.stat().st_size} bytes)")
