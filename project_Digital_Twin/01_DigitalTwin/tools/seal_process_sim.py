"""
====================================================
SEAL_PROCESS SIMULATION — จำลองสถานะที่ 14 ของ FSM
====================================================
สคริปต์แยกสำหรับดูพฤติกรรมของสถานะ SEAL_PROCESS กับฮาร์ดแวร์จริง
ไม่เกี่ยวข้องและไม่แตะ gateway_fsm.py / FSM หลัก / เว็บ / rust bridge

ลำดับที่จำลอง (สเปกที่เจ้าของงานยืนยัน 2 ก.ย. 2026 รอบเย็น)
    เริ่มมา            -> ตรวจ IP0 ต้องเจอสัญญาณ = ซีลอยู่ตำแหน่งบน
    กด SPACE           -> สั่งโซลินอยด์ "ทั้งสองตัว" พร้อมกัน กดลงมา
                       -> รอจนถึง IP1 (เซนเซอร์ล่าง)
                       -> ดีเลย์ 5 วินาที
                       -> สั่งดันกลับขึ้นไปที่ IP0
                       -> ไปสถานะถัดไป

----------------------------------------------------
คำเตือนด้านความปลอดภัย
----------------------------------------------------
ต่อลมแล้วหัวซีลจะกดลงจริงด้วยแรง -> เอามือออกจากบริเวณกระบอกก่อนกด SPACE
ปิด gateway / START_FULL.bat ก่อนรัน ไม่งั้นจะแย่งกันเขียนเอาต์พุต

----------------------------------------------------
สถานะการยืนยัน — ทดสอบกับเครื่องจริงครบวงแล้ว 2 ก.ย. 2026 เย็น
----------------------------------------------------
ลูปเดินครบตามสเปก: จ่ายลม -> กระบอกยกขึ้น IP0 ติด -> สั่งงาน โซลินอยด์ทำงาน
กดลง IP1 ติด -> ครบเวลา ตัดโซลินอยด์ -> ยกขึ้น IP0 ติด -> จบรอบ

เซนเซอร์ทั้งสี่ตัวอ่านผ่าน Modbus ได้ครบแล้ว
   IP0 (addr 0) bit 6, 7 = เซนเซอร์บน   <- ยืนยัน 2 ก.ย. 2026 เย็น
   IP1 (addr 8) bit 6, 7 = เซนเซอร์ล่าง
หมายเหตุประวัติ: ช่วงบ่ายวันเดียวกันอ่าน IP0 ได้ 00000000 ตลอดจนเกือบสรุปว่าอ่านไม่ได้
สาเหตุคือกระบอกยังไม่ได้นั่งสุดที่เซนเซอร์บน (ลมยังไม่เข้าเต็ม) ไม่ใช่บอร์ดมีปัญหา
-> ถ้าเจออาการอ่านเซนเซอร์ไม่ขึ้น ให้เช็คตำแหน่งกลไกจริงก่อนโทษ Modbus

----------------------------------------------------
ข้อควรระวังของบอร์ดตัวนี้ — เจอมาแล้ว อย่าเสียเวลาไล่ซ้ำ
----------------------------------------------------
1. บอร์ดอ่านค่าเอาต์พุตกลับไม่ได้
   เขียน OP0 = 0b11 แล้วอ่าน addr 64 กลับมาได้ 00000000 เสมอ
   -> ห้ามใช้การอ่านกลับเป็นหลักฐานว่าสั่งสำเร็จ ดูที่เซนเซอร์กับของจริงเท่านั้น

2. ช่อง length ในเฟรมตอบกลับใส่ค่าผิด
   ตอบมาจริง 10 ไบต์ แต่เขียนในช่องว่า 6 ซึ่งตามมาตรฐานต้องแปลว่า 12
   -> ต้องอ่านขนาดตายตัว ถ้าเขียนโค้ดอ่านตามความยาวที่เฟรมบอกจะค้างทันที

3. บอร์ดไม่รองรับ FC2 (Read Discrete Inputs) แต่ไม่แจ้ง error
   ส่ง FC2 ไป มันตอบ fc=01 กลับมา คือแปลงเป็น FC1 ให้เฉยๆ
   -> ใช้ FC1 อย่างเดียวพอ

4. address ตั้งแต่ 160 ขึ้นไปคืนเลข address ออกมาเอง ไม่ใช่ข้อมูล
   เช่นอ่าน addr 200 ได้ 11001000 (= 200) -> อย่าหลงว่าเจอ address ใหม่

5. ต้องมี Modbus frame วิ่งตลอด ส่งแค่ *IDN? ไม่พอ
   ทดลองแล้ว: IDN อย่างเดียว -> หลุดที่ 0.52 วินาที
              IDN + อ่าน Modbus ทุก 0.2 วิ -> รอด ไม่มี error
   -> ทุกลูปที่รอคน/รอเวลา ต้องมีการอ่านหรือเขียน bank คั่นด้วย

6. บอร์ดรับการเชื่อมต่อได้ทีละหนึ่งเท่านั้น
   เปิดสคริปต์สองตัวพร้อมกันจะ timeout ต้องปิดตัวเก่าก่อน

7. Transaction ID ต้องเป็น 00 00 คงที่ ห้ามนับขึ้น (เพื่อนเจอ 24 ก.ย. 2569)
   นับขึ้นไปถึง 0x2A0A = "*\n" ไปปลุกตัวอ่านคำสั่งข้อความของบอร์ด (ตัวเดียวกับ *RST)
   บอร์ดตอบ Unknown Command แทรกกลางสาย -> หลุด (เพื่อนเจอที่พัลส์ 5,390)
   ที่มา: repo เพื่อน docs/specs/board_protocol.md ข้อ 9.3.1

----------------------------------------------------
ย้ายโซลินอยด์ไปแผ่น OP1 (ตกลงกับเพื่อน 24 ก.ย. 2569)
----------------------------------------------------
เดิมโซลินอยด์ A/B อยู่ OP0 (addr 64) bit 0/1 ซึ่ง FSM ใช้เป็นไฟสถานะ
-> เดินเครื่อง auto แล้วโซลินอยด์ A กดลงตอน FEED_CARRIER เอง (ผิดจังหวะ)
ตอนนี้ย้ายมา OP1 (addr 72) bit 0/1 แล้ว — OP0 เหลือเป็นไฟสถานะอย่างเดียว
บิตอื่นของ OP1 ที่เพื่อนใช้: bit 2 = Cylinder C · bit 4 = พัลส์มอเตอร์ feed
สคริปต์นี้เขียน OP1 ทั้งไบต์ -> บิต 2/4 เป็น 0 ตลอดที่รัน (มอเตอร์กับ Cylinder C ไม่ขยับ)

วิธีรัน
   01_DigitalTwin/.venv/Scripts/python.exe 01_DigitalTwin/tools/seal_process_sim.py
====================================================
"""

import os
import socket
import sys
import time

try:
    import msvcrt          # Windows เท่านั้น — ใช้อ่านปุ่มแบบไม่บล็อก
except ImportError:
    msvcrt = None

if os.name == "nt":
    os.system("chcp 65001 > nul")
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==================================================
# ตั้งค่า
# ==================================================
CYLS = ["A", "B"]         # ทำงานพร้อมกันทั้งสองตัวตามสเปก

TRIGGER = "key"           # "key" = รอกดปุ่มทุกรอบ | "auto" = เดินเอง
HOLD_SECONDS = 5.0        # ดีเลย์ตอนกดค้าง — สเปกใหม่คือ 5 วินาที
DOWN_TIMEOUT = 5.0        # รอให้ถึงเซนเซอร์ล่างนานสุดเท่านี้
UP_TIMEOUT   = 5.0        # รอให้กลับถึงเซนเซอร์บนนานสุดเท่านี้
IDLE_BETWEEN = 1.0        # เว้นระหว่างรอบ (โหมด auto)
CYCLES       = 0          # 0 = ไม่จำกัด

# ==================================================
# แผนที่ I/O
# ==================================================
H7_IP   = "192.168.0.100"
H7_PORT = 502
UNIT_ID = 1

SOCKET_TIMEOUT = 0.5
IDN_INTERVAL   = 0.5
IDN_GAP        = 0.05     # ต้องเว้นหลัง *IDN? ก่อนยิง Modbus ไม่งั้นคำสั่งแรกล้ม

UPPER_ADDR = 0            # IP0 — เซนเซอร์บน
LOWER_ADDR = 8            # IP1 — เซนเซอร์ล่าง
OPBASE     = 72           # OP1 — โซลินอยด์ (ย้ายจาก OP0 24 ก.ย. 2569)
STATUS_ADDR = 64          # OP0 — ไฟสถานะ FSM (ปิดตอนจบสคริปต์)

SOL_BIT   = {"A": 0, "B": 1}    # OP1 bit 0/1 (เดิม OP0 bit 0/1 ยืนยัน 2 ก.ย.)
LOWER_BIT = {"A": 6, "B": 7}    # ยืนยันแล้ว
UPPER_BIT = {"A": 6, "B": 7}    # ยืนยันแล้ว 2 ก.ย. 2026 เย็น (ทดสอบครบวงกับลมจริง)

ALL_SOL = 0
for _c in CYLS:
    ALL_SOL |= 1 << SOL_BIT[_c]

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


class SCHClient:
    """โครงเดียวกับ io_bit_probe.py

    ห้ามเปลี่ยนไปอ่านตามช่อง length ของเฟรม — บอร์ดนี้ใส่ length ผิด
    (ตอบมาจริง 10 ไบต์ แต่เขียนในช่องว่า 6 ซึ่งควรแปลว่า 12) ยืนยัน 2 ก.ย. 2026 เย็น
    การอ่านขนาดตายตัวจึงเป็นวิธีที่ถูกสำหรับบอร์ดตัวนี้
    """

    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.sock = None
        self.next_idn = 0.0

    def next_tid(self):
        # ห้ามนับขึ้น — ถึง 0x2A0A ("*\n") บอร์ดจะหลุด ดูข้อ 7 ด้านบน
        return b"\x00\x00"

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(SOCKET_TIMEOUT)
        self.sock.connect((self.ip, self.port))
        self.next_idn = 0.0
        self.beat()

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise RuntimeError("Socket closed")
            buf += chunk
        return buf

    def recv_line(self):
        buf = b""
        while True:
            c = self.sock.recv(1)
            if not c:
                raise RuntimeError("Socket closed")
            buf += c
            if c == b"\n":
                return buf

    def beat(self):
        now = time.time()
        if now >= self.next_idn:
            self.sock.sendall(b"*IDN?\n")
            self.recv_line()
            time.sleep(IDN_GAP)
            self.next_idn = time.time() + IDN_INTERVAL

    def read_bank(self, addr):
        self.beat()
        pkt = (
            self.next_tid() + b"\x00\x00" + b"\x00\x06" +
            UNIT_ID.to_bytes(1, "big") + b"\x01" +
            addr.to_bytes(2, "big") + b"\x00\x08"
        )
        self.sock.sendall(pkt)
        return self.recv_exact(10)[9]

    def write_bank(self, addr, value):
        self.beat()
        pkt = (
            self.next_tid() + b"\x00\x00" + b"\x00\x08" +
            UNIT_ID.to_bytes(1, "big") + b"\x0F" +
            addr.to_bytes(2, "big") + b"\x00\x08" +
            b"\x01" + value.to_bytes(1, "big")
        )
        self.sock.sendall(pkt)
        self.recv_exact(12)


def bit(v, i):
    return bool((v >> i) & 1)


T0 = time.time()


def log(state, msg, tag=""):
    print(f"  [{time.time() - T0:6.2f}s]  {state:<11} {msg} {tag}", flush=True)


def read_pos(io):
    """คืนตำแหน่งกระบอกทุกตัว: (upper, lower, ค่าดิบ IP0, ค่าดิบ IP1)"""
    up_raw = io.read_bank(UPPER_ADDR)
    lo_raw = io.read_bank(LOWER_ADDR)
    upper = {c: bit(up_raw, UPPER_BIT[c]) for c in CYLS}
    lower = {c: bit(lo_raw, LOWER_BIT[c]) for c in CYLS}
    return upper, lower, up_raw, lo_raw


def fmt_pos(upper, lower):
    out = []
    for c in CYLS:
        if lower[c]:
            where, col = "ล่าง", GREEN
        elif upper[c]:
            where, col = "บน", GREEN
        else:
            where, col = "ไม่รู้", DIM
        out.append(f"{c}={col}{where}{RESET}")
    return "  ".join(out)


def set_sol(io, on):
    op_sol = ALL_SOL if on else 0x00
    io.write_bank(OPBASE, op_sol)
    return op_sol


def wait_until(io, want, op_sol, timeout):
    """
    รอจนกระบอกทุกตัวถึงตำแหน่งที่ต้องการ ("upper" หรือ "lower")
    ระหว่างรอยัง refresh เอาต์พุตและส่ง heartbeat ตลอด
    คืน (สำเร็จไหม, เวลาที่ใช้)
    """
    start = time.time()
    while time.time() - start < timeout:
        io.write_bank(OPBASE, op_sol)
        upper, lower, _, _ = read_pos(io)
        target = upper if want == "upper" else lower
        if all(target[c] for c in CYLS):
            return True, time.time() - start
        time.sleep(0.05)
    return False, time.time() - start


def wait_for_trigger(io):
    """
    รอผู้ใช้กดปุ่มก่อนเริ่มรอบใหม่ — SPACE เริ่ม / Q ออก
    ระหว่างรอต้องมี Modbus frame วิ่งตลอด ไม่งั้นบอร์ดตัดการเชื่อมต่อใน ~0.5 วินาที
    (ส่งแค่ *IDN? ไม่พอ พิสูจน์แล้ว 2 ก.ย. 2026)
    """
    if msvcrt is None:
        ans = input("\n  กด ENTER เพื่อเริ่ม 1 รอบ  |  พิมพ์ q แล้ว ENTER เพื่อออก > ")
        return ans.strip().lower() != "q"

    print()
    print(f"  {YELLOW}พร้อมแล้ว{RESET} — กด {GREEN}SPACE{RESET} เพื่อสั่งทำงาน 1 รอบ  |  "
          f"กด {RED}Q{RESET} เพื่อออก  |  Ctrl+C หยุดฉุกเฉิน", flush=True)

    while msvcrt.kbhit():
        msvcrt.getch()

    last_poll = 0.0
    while True:
        now = time.time()
        if now - last_poll >= 0.2:
            last_poll = now
            try:
                upper, lower, up_raw, lo_raw = read_pos(io)
                print(f"\r  รอปุ่ม...  {fmt_pos(upper, lower)}   "
                      f"{DIM}IP0={format(up_raw, '08b')} IP1={format(lo_raw, '08b')}{RESET}   ",
                      end="", flush=True)
            except Exception as e:
                print(f"\n  {YELLOW}หลุดการเชื่อมต่อ ({type(e).__name__}) กำลังต่อใหม่...{RESET}",
                      flush=True)
                io.close()
                time.sleep(0.5)
                try:
                    io.connect()
                    print(f"  {GREEN}ต่อใหม่สำเร็จ{RESET}", flush=True)
                except Exception as e2:
                    print(f"  {RED}ต่อใหม่ไม่สำเร็จ: {e2}{RESET}", flush=True)
                    time.sleep(1.0)

        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch in (b" ", b"\r", b"\n"):
                print()
                return True
            if ch in (b"q", b"Q"):
                print()
                return False
        time.sleep(0.03)


def run_cycle(io, n):
    print()
    print("=" * 66)
    print(f"  รอบที่ {n}  —  จำลองสถานะ SEAL_PROCESS  (กระบอก {' + '.join(CYLS)} พร้อมกัน)")
    print("=" * 66)

    # ---------- INIT_CHECK : ตรวจ IP0 ตามสเปก ----------
    upper, lower, up_raw, lo_raw = read_pos(io)
    log("INIT_CHECK", f"IP0 = {format(up_raw, '08b')}   IP1 = {format(lo_raw, '08b')}")

    if all(upper[c] for c in CYLS):
        log("INIT_CHECK", f"{GREEN}IP0 มีสัญญาณครบทุกกระบอก — ซีลอยู่ตำแหน่งบน{RESET}",
            f"{GREEN}[ยืนยันด้วยเซนเซอร์]{RESET}")
    elif up_raw == 0:
        log("INIT_CHECK",
            f"{RED}IP0 ไม่มีสัญญาณเลย{RESET} — กระบอกยังไม่ได้นั่งสุดที่เซนเซอร์บน")
        log("INIT_CHECK",
            f"{DIM}เช็คก่อน: จ่ายลมแล้วหรือยัง / กระบอกค้างกลางทางหรือเปล่า{RESET}")
    else:
        miss = [c for c in CYLS if not upper[c]]
        log("INIT_CHECK", f"{YELLOW}IP0 มีสัญญาณไม่ครบ — ขาดกระบอก {', '.join(miss)}{RESET}")

    if any(lower[c] for c in CYLS):
        down_now = [c for c in CYLS if lower[c]]
        log("INIT_CHECK",
            f"{YELLOW}IP1 ติดอยู่ก่อนสั่ง (กระบอก {', '.join(down_now)}){RESET} — ยังไม่ได้อยู่บนจริง")

    # ---------- SEAL_DOWN ----------
    op_sol = set_sol(io, True)
    log("SEAL_DOWN", f"สั่งโซลินอยด์ทั้งสองตัว ON   OP1 = 0b{format(op_sol, '08b')}")
    ok, dt = wait_until(io, "lower", op_sol, DOWN_TIMEOUT)
    if ok:
        log("SEAL_DOWN", f"{GREEN}ถึง IP1 ครบทุกกระบอก ใช้เวลา {dt:.2f}s{RESET}",
            f"{GREEN}[ยืนยันด้วยเซนเซอร์]{RESET}")
    else:
        _, lower_now, _, lo_raw = read_pos(io)
        got = [c for c in CYLS if lower_now[c]]
        log("SEAL_DOWN",
            f"{RED}หมดเวลา {DOWN_TIMEOUT}s ยังไม่ถึง IP1 ครบ{RESET} — "
            f"ถึงแล้ว: {got if got else 'ไม่มีเลย'}  (IP1 = {format(lo_raw, '08b')})")

    # ---------- SEAL_HOLD ----------
    log("SEAL_HOLD", f"ดีเลย์ {HOLD_SECONDS}s ...")
    t_hold = time.time()
    while time.time() - t_hold < HOLD_SECONDS:
        io.write_bank(OPBASE, op_sol)
        io.read_bank(LOWER_ADDR)
        time.sleep(0.05)
    log("SEAL_HOLD", f"ครบ {time.time() - t_hold:.2f}s", f"{GREEN}[ค่าตามสเปก]{RESET}")

    # ---------- SEAL_UP ----------
    set_sol(io, False)
    log("SEAL_UP", "สั่งโซลินอยด์ OFF   OP1 = 0b00000000  (ดันกลับไปที่ IP0)")
    ok, dt = wait_until(io, "upper", 0x00, UP_TIMEOUT)
    if ok:
        log("SEAL_UP", f"{GREEN}กลับถึง IP0 ครบทุกกระบอก ใช้เวลา {dt:.2f}s{RESET}",
            f"{GREEN}[ยืนยันด้วยเซนเซอร์]{RESET}")
    else:
        upper_now, lower_now, up_raw, lo_raw = read_pos(io)
        if up_raw == 0 and not any(lower_now[c] for c in CYLS):
            log("SEAL_UP",
                f"{YELLOW}IP1 ดับแล้ว = ออกจากตำแหน่งล่างจริง{RESET} "
                f"แต่ยังไม่ถึง IP0 — น่าจะค้างกลางทาง (ลมอ่อน / ติดขัดทางกล)",
                f"{RED}[ไม่ถึงตำแหน่งปลายทาง]{RESET}")
        else:
            log("SEAL_UP",
                f"{RED}หมดเวลา {UP_TIMEOUT}s ยังไม่กลับถึง IP0{RESET} "
                f"(IP0 = {format(up_raw, '08b')}  IP1 = {format(lo_raw, '08b')})")

    # ---------- DONE ----------
    log("DONE", "จบสถานะ SEAL_PROCESS พร้อมไปสถานะถัดไป")


def main():
    io = SCHClient(H7_IP, H7_PORT)
    try:
        io.connect()
        print()
        print(f"เชื่อมต่อบอร์ดแล้ว  {H7_IP}:{H7_PORT}")
        print(f"กระบอกที่ใช้ = {' + '.join(CYLS)}  |  "
              f"โซลินอยด์ OP1 (addr {OPBASE}) bit {', '.join(str(SOL_BIT[c]) for c in CYLS)}")
        print(f"เซนเซอร์บน   IP0 (addr {UPPER_ADDR}) bit "
              f"{', '.join(str(UPPER_BIT[c]) for c in CYLS)}")
        print(f"เซนเซอร์ล่าง IP1 (addr {LOWER_ADDR}) bit "
              f"{', '.join(str(LOWER_BIT[c]) for c in CYLS)}")
        print(f"ดีเลย์ตอนกดค้าง {HOLD_SECONDS}s")

        n = 0
        while True:
            if CYCLES and n >= CYCLES:
                print(f"\n{'=' * 66}\n  ครบ {CYCLES} รอบ\n{'=' * 66}")
                break

            if TRIGGER == "key":
                if not wait_for_trigger(io):
                    print(f"\n  {YELLOW}ผู้ใช้สั่งออก{RESET}")
                    break
            elif n > 0:
                t_end = time.time() + IDLE_BETWEEN
                while time.time() < t_end:
                    io.write_bank(OPBASE, 0x00)
                    io.read_bank(LOWER_ADDR)
                    time.sleep(0.05)

            n += 1
            run_cycle(io, n)

    except KeyboardInterrupt:
        print(f"\n{YELLOW}ผู้ใช้กด Ctrl+C{RESET}")
    except Exception as e:
        print(f"\n{RED}[ERR]{RESET} {type(e).__name__}: {e}")
    finally:
        try:
            if io.sock:
                io.write_bank(OPBASE, 0x00)
                io.write_bank(STATUS_ADDR, 0x00)
                # หมายเหตุ: บอร์ดนี้อ่านค่าเอาต์พุตกลับไม่ได้ (อ่านได้ 0 เสมอ)
                # จึงไม่อ่านกลับมาแสดงว่า "ปิดแล้ว" เพราะไม่ได้พิสูจน์อะไร
                print(f"  {GREEN}[OK] ส่งคำสั่งปิดเอาต์พุตแล้ว{RESET} "
                      f"{DIM}(บอร์ดอ่านค่าเอาต์พุตกลับไม่ได้ ยืนยันด้วยของจริงเท่านั้น){RESET}")
        except Exception as e:
            print(f"  {RED}[!!] ปิดเอาต์พุตไม่สำเร็จ: {e} -> ไปตัดลม/ไฟเอง{RESET}")
        io.close()


if __name__ == "__main__":
    main()
