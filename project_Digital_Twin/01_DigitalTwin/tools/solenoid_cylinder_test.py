"""
====================================================
SOLENOID + CYLINDER + POSITION SENSOR — TEST ONLY
====================================================
สคริปต์ทดสอบแยกเดี่ยว ไม่เกี่ยวกับ gateway / FSM / เว็บ

โจทย์: เมื่อเซนเซอร์ตรวจว่ากระบอกสูบอยู่ตำแหน่งล่าง -> สั่งโซลินอยด์ทำงาน

ฮาร์ดแวร์ที่รองรับ
  - เซนเซอร์ตำแหน่ง 4 ตัว (กระบอกละ 2 ตัว: บน/ล่าง)  -> อินพุต IP0
  - โซลินอยด์ 2 ตัว                                  -> เอาต์พุต OP0

----------------------------------------------------
ข้อควรระวังก่อนรัน
----------------------------------------------------
1. ปิด gateway / START_FULL.bat ก่อน
   ถ้ารันพร้อมกันจะแย่งกันเขียนเอาต์พุต โซลินอยด์จะกระพริบมั่ว

2. FC15 เขียนเต็ม bank 8 บิตเสมอ
   ทุกครั้งที่สั่ง OP0 บิตที่ไม่ได้ใช้ในธนาคารเดียวกันจะถูกเขียน 0 ไปด้วย
   ถ้ามีอุปกรณ์อื่นต่ออยู่บิตอื่นของ OP0 มันจะถูกสั่งปิด -> ตรวจสายก่อนรัน

3. เริ่มที่ MODE = "monitor" เสมอ
   โหมดนี้ไม่เขียนเอาต์พุตเลย ใช้หาว่าเซนเซอร์ตัวไหนอยู่บิตไหน

วิธีรัน
   01_DigitalTwin/.venv/Scripts/python.exe 01_DigitalTwin/tools/solenoid_cylinder_test.py
====================================================
"""

import os
import socket
import sys
import time

# --------------------------------------------------
# กันกับดัก path ภาษาไทย: console ของ Windows เป็น cp1252
# ทำให้ print ภาษาไทยแล้ว UnicodeEncodeError ตั้งแต่บรรทัดแรก
# บังคับ stdout เป็น UTF-8 ตรงนี้เลย จะได้ไม่ต้องตั้ง PYTHONUTF8 ทุกครั้ง
# --------------------------------------------------
if os.name == "nt":
    os.system("chcp 65001 > nul")
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==================================================
# ตั้งค่าตรงนี้
# ==================================================

MODE = "run"          # "monitor" = ดูอย่างเดียว ปลอดภัย | "run" = สั่งโซลินอยด์จริง

# --- ธนาคารอินพุตที่เซนเซอร์ต่ออยู่ ---
# วัดจริงเมื่อ 1 ก.ย. 2026: สัญญาณเซนเซอร์อยู่ที่ bank 1 (Modbus address 8)
# หมายเหตุ: ป้ายบนบอร์ดอาจเขียนว่า "IP2" ซึ่งไม่ตรงกับเลข bank ของ Modbus
#          ยึดตัวเลขที่วัดได้จริงเป็นหลัก ไม่ใช่ป้าย
SENSOR_BANK = 1

# --- บิตของเซนเซอร์ในธนาคารนั้น (0-7) ---
# ยืนยันแล้ว 2 ก.ย. 2026 (วัดจริง + เจ้าของงานยืนยัน)
# เซนเซอร์ "ล่าง" ของกระบอกทั้งสองอยู่ที่ IP1 บิต 6 และ 7
# เซนเซอร์ "บน" ต่ออยู่ที่ IP0 (addr 0) แต่ยังไม่ได้ยืนยันว่าอยู่บิตไหน
# ที่อ่าน IP0 ได้ 00000000 ตอนทดสอบเป็นเรื่องปกติ ไม่ใช่ความผิดปกติ
# เพราะกระบอกจอดอยู่ตำแหน่งล่าง เซนเซอร์บนจึงไม่เจออะไร
# -> ยืนยันได้โดยดันกระบอกขึ้นแล้วดูว่า IP0 บิตไหนติด
CYL_A_DOWN = 6            # ยืนยันแล้ว  กระบอก A เซนเซอร์ล่าง -> ทริกโซลินอยด์ A
CYL_B_DOWN = 7            # ยืนยันแล้ว  กระบอก B เซนเซอร์ล่าง -> ทริกโซลินอยด์ B
CYL_A_UP   = 4            # ยังไม่ยืนยัน เป็นเลขที่เดาไว้ ใช้แสดงผลเฉยๆ
CYL_B_UP   = 5            # ยังไม่ยืนยัน เป็นเลขที่เดาไว้ ใช้แสดงผลเฉยๆ

# --- บิตของโซลินอยด์ใน OP0 (0-7) ---
# ยืนยันแล้ว 2 ก.ย. 2026 โดยเจ้าของงาน: โซลินอยด์อยู่ OP0 บิต 0 และ 1
SOL_A = 0
SOL_B = 1

# --- ถ้าเซนเซอร์ให้ลอจิกกลับด้าน (ถึงตำแหน่งแล้วอ่านได้ 0) เปลี่ยนเป็น False ---
# วัดจริงแล้ว: อยู่ตำแหน่ง = อ่านได้ 1 -> active high
SENSOR_ACTIVE_HIGH = True

# --- กรองสัญญาณรบกวน ---
# วัดจริงพบสัญญาณรบกวนกระพริบ 1 สแกน (~0.1 วิ) หลายบิต ทั้งที่ไม่มีเซนเซอร์ต่อ
# เซนเซอร์จริงจะค้างเป็นวินาที ต้องอ่านค่าเดิมซ้ำกันครบเท่านี้ก่อนถึงจะเชื่อ
# ถ้ายังกระตุกอยู่ให้เพิ่มค่านี้
DEBOUNCE_SCANS = 5

# --- กันกระบอกสูบกระแทกรัว ---
HOLD_MS     = 1000        # โซลินอยด์ติดค้างอย่างน้อยเท่านี้ ก่อนยอมให้ดับ
COOLDOWN_MS = 1000        # หลังดับแล้ว เว้นช่วงเท่านี้ก่อนรับทริกครั้งใหม่
MAX_CYCLES  = 0           # ครบจำนวนรอบแล้วหยุดเอง (0 = ไม่จำกัด รันค้างจนกด Ctrl+C)

# ==================================================
# เครือข่าย + ไทม์มิ่ง
# คัดลอกจาก tools/modbus_io_test.py ซึ่งเป็นค่าที่จูนจนบอร์ดไม่หลุดแล้ว
# อย่าลดค่าลงจากนี้ เคยทำให้บอร์ดหลุด 28 ครั้งมาแล้ว
# ==================================================
H7_IP   = "192.168.0.100"
H7_PORT = 502
UNIT_ID = 1

IDN_INTERVAL    = 1.0     # heartbeat *IDN? — ห้ามถี่กว่านี้
LOOP_DELAY      = 0.02    # 20 ms
SOCKET_TIMEOUT  = 0.5
RECONNECT_DELAY = 0.5

IPBASE_ADDRESS = 0        # IP0 = 0, IP1 = 8
OPBASE_ADDRESS = 64       # OP0 = 64, OP1 = 72


# ==================================================
# ตัวช่วยแสดงผล
# ==================================================
GREEN = "\033[32m"
RED   = "\033[31m"
DIM   = "\033[2m"
RESET = "\033[0m"


def clear_console():
    os.system("cls" if os.name == "nt" else "clear")


def bit(value: int, index: int) -> bool:
    """อ่านบิตที่ index จากไบต์"""
    return bool((value >> index) & 1)


def sensor_on(ip_value: int, index: int) -> bool:
    """แปลงบิตดิบเป็น 'เซนเซอร์ทำงานอยู่ไหม' ตามค่า SENSOR_ACTIVE_HIGH"""
    raw = bit(ip_value, index)
    return raw if SENSOR_ACTIVE_HIGH else (not raw)


def bits_table(value: int, labels: dict) -> str:
    """แสดงบิตทั้ง 8 พร้อมชื่อกำกับ"""
    lines = []
    for i in range(8):
        on = bit(value, i)
        mark = f"{GREEN}[ 1 ]{RESET}" if on else f"{DIM}[ 0 ]{RESET}"
        name = labels.get(i, "")
        lines.append(f"   bit {i}  {mark}  {name}")
    return "\n".join(lines)


# ==================================================
# ไคลเอนต์ Modbus — คัดลอกจาก modbus_io_test.py
# ==================================================
class SCHClient:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.sock = None

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(SOCKET_TIMEOUT)
            self.sock.connect((self.ip, self.port))
            print("[OK] เชื่อมต่อบอร์ดแล้ว")
            return True
        except Exception as e:
            print("[FAIL] เชื่อมต่อไม่ได้:", e)
            self.sock = None
            return False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def send(self, data: bytes):
        self.sock.sendall(data)

    def recv_line(self):
        buf = b''
        while True:
            c = self.sock.recv(1)
            if not c:
                raise RuntimeError("Socket closed")
            buf += c
            if c == b'\n':
                return buf

    # -------- FC1 : อ่านอินพุต 8 บิต
    def read_ip(self, bank):
        addr = IPBASE_ADDRESS + 8 * bank
        pkt = (
            b'\x00\x00\x00\x00\x00\x06' +
            UNIT_ID.to_bytes(1, 'big') +
            b'\x01' +
            addr.to_bytes(2, 'big') +
            b'\x00\x08'
        )
        self.send(pkt)
        resp = self.sock.recv(10)
        return resp[9]

    # -------- FC15 : เขียนเอาต์พุตเต็ม bank 8 บิต
    def write_op(self, bank, value):
        addr = OPBASE_ADDRESS + 8 * bank
        pkt = (
            b'\x00\x00\x00\x00\x00\x08' +
            UNIT_ID.to_bytes(1, 'big') +
            b'\x0F' +
            addr.to_bytes(2, 'big') +
            b'\x00\x08' +
            b'\x01' +
            value.to_bytes(1, 'big')
        )
        self.send(pkt)
        self.sock.recv(12)


# ==================================================
# ตัวคุมโซลินอยด์ 1 ตัว — กันกระแทกรัวด้วย HOLD + COOLDOWN
# ==================================================
class BitDebouncer:
    """กรองสัญญาณรบกวน: ต้องอ่านค่าเดิมซ้ำครบ DEBOUNCE_SCANS ครั้งก่อนถึงจะยอมรับ"""

    def __init__(self):
        self.stable = 0
        self.candidate = 0
        self.count = 0

    def update(self, raw: int) -> int:
        if raw == self.candidate:
            self.count += 1
        else:
            self.candidate = raw
            self.count = 1
        if self.count >= DEBOUNCE_SCANS:
            self.stable = self.candidate
        return self.stable


class SolenoidChannel:
    def __init__(self, name, sensor_bit, output_bit):
        self.name = name
        self.sensor_bit = sensor_bit
        self.output_bit = output_bit
        self.on = False
        self.changed_at = 0.0     # เวลาที่เปลี่ยนสถานะล่าสุด
        self.cycles = 0

    def _ms_since_change(self, now):
        return (now - self.changed_at) * 1000.0

    def update(self, ip0: int, now: float) -> bool:
        """คืนค่าสถานะโซลินอยด์ที่ควรเป็นในรอบนี้"""
        triggered = sensor_on(ip0, self.sensor_bit)

        if self.on:
            # ติดอยู่ -> ดับได้ก็ต่อเมื่อเซนเซอร์หลุด และติดมานานพอแล้ว
            if not triggered and self._ms_since_change(now) >= HOLD_MS:
                self.on = False
                self.changed_at = now
        else:
            # ดับอยู่ -> ติดได้ก็ต่อเมื่อเซนเซอร์ทำงาน และพ้น cooldown แล้ว
            if triggered and self._ms_since_change(now) >= COOLDOWN_MS:
                self.on = True
                self.changed_at = now
                self.cycles += 1

        return self.on

    def status_line(self, ip0: int) -> str:
        triggered = sensor_on(ip0, self.sensor_bit)
        sens = f"{GREEN}ถึงตำแหน่งล่าง{RESET}" if triggered else f"{DIM}ไม่ถึง{RESET}"
        sol = f"{GREEN}ทำงาน{RESET}" if self.on else f"{DIM}ดับ{RESET}"
        return (f"   {self.name}   เซนเซอร์ล่าง(bit {self.sensor_bit}): {sens:>28}"
                f"   |   โซลินอยด์(bit {self.output_bit}): {sol:>18}"
                f"   |   รอบ: {self.cycles}")


# ==================================================
# MAIN
# ==================================================
INPUT_LABELS = {
    CYL_A_DOWN: "<- กระบอก A ล่าง",
    CYL_A_UP:   "<- กระบอก A บน",
    CYL_B_DOWN: "<- กระบอก B ล่าง",
    CYL_B_UP:   "<- กระบอก B บน",
}


def main():
    if MODE not in ("monitor", "run"):
        print(f"MODE ต้องเป็น 'monitor' หรือ 'run' เท่านั้น (ตอนนี้เป็น {MODE!r})")
        return

    io = SCHClient(H7_IP, H7_PORT)
    debouncer = BitDebouncer()
    ch_a = SolenoidChannel("กระบอก A", CYL_A_DOWN, SOL_A)
    ch_b = SolenoidChannel("กระบอก B", CYL_B_DOWN, SOL_B)

    next_idn = 0.0
    stop_reason = None

    print("=" * 60)
    print(f"  โหมด: {MODE}")
    if MODE == "monitor":
        print("  ไม่เขียนเอาต์พุตใดๆ โซลินอยด์จะไม่ทำงาน")
        print("  ขยับกระบอกสูบด้วยมือ แล้วดูว่าบิตไหนเปลี่ยน")
    else:
        print("  *** จะสั่งโซลินอยด์จริง ระวังมือ ***")
    print("  กด Ctrl+C เพื่อหยุด (เอาต์พุตจะถูกปิดให้อัตโนมัติ)")
    print("=" * 60)
    time.sleep(1.5)

    try:
        while True:
            if io.sock is None:
                if not io.connect():
                    time.sleep(RECONNECT_DELAY)
                    continue
                next_idn = time.time()

            try:
                now = time.time()

                # heartbeat ที่บอร์ดต้องการ
                if now >= next_idn:
                    io.send(b"*IDN?\n")
                    io.recv_line()
                    next_idn = now + IDN_INTERVAL

                ip_raw = io.read_ip(SENSOR_BANK)
                ip0 = debouncer.update(ip_raw)
                # อ่านอีกธนาคารมาโชว์ด้วย เพื่อดูว่าเซนเซอร์บนขึ้นค่าไหม (ปัจจุบันยังอ่านไม่ได้)
                ip_other = io.read_ip(0 if SENSOR_BANK == 1 else 1)

                op0 = 0
                if MODE == "run":
                    if ch_a.update(ip0, now):
                        op0 |= (1 << ch_a.output_bit)
                    if ch_b.update(ip0, now):
                        op0 |= (1 << ch_b.output_bit)
                    io.write_op(0, op0)

                # ---------- แสดงผล ----------
                clear_console()
                print("=" * 60)
                print(f"  ทดสอบโซลินอยด์ + กระบอกสูบ    [โหมด {MODE}]")
                print("=" * 60)
                other_bank = 0 if SENSOR_BANK == 1 else 1
                print(f"\n  อินพุต IP{SENSOR_BANK} = 0b{format(ip0, '08b')}   "
                      f"{DIM}(IP{other_bank} = 0b{format(ip_other, '08b')} <- เซนเซอร์บน){RESET}\n")
                print(bits_table(ip0, INPUT_LABELS))

                if MODE == "run":
                    print(f"\n  เอาต์พุต OP0 = 0b{format(op0, '08b')}\n")
                    print(ch_a.status_line(ip0))
                    print(ch_b.status_line(ip0))
                    if MAX_CYCLES:
                        print(f"\n  จะหยุดเองเมื่อกระบอกใดกระบอกหนึ่งครบ {MAX_CYCLES} รอบ")
                else:
                    print(f"\n  {DIM}โหมด monitor — ไม่แตะเอาต์พุตเลย{RESET}")
                    print(f"  {DIM}จดเลขบิตที่เปลี่ยนตอนกระบอกถึงตำแหน่ง แล้วไปแก้ค่าคงที่บนหัวไฟล์{RESET}")

                print("\n  Ctrl+C เพื่อหยุด")

                # ---------- หยุดเองเมื่อครบรอบ ----------
                if MODE == "run" and MAX_CYCLES:
                    if ch_a.cycles >= MAX_CYCLES or ch_b.cycles >= MAX_CYCLES:
                        stop_reason = f"ครบ {MAX_CYCLES} รอบแล้ว"
                        break

                time.sleep(LOOP_DELAY)

            except Exception as e:
                print("[WARN] หลุดการเชื่อมต่อ:", e)
                io.close()
                time.sleep(RECONNECT_DELAY)

    except KeyboardInterrupt:
        stop_reason = "ผู้ใช้กด Ctrl+C"

    finally:
        # ---------- ปิดเอาต์พุตให้แน่ใจ ----------
        print("\n" + "=" * 60)
        if io.sock is not None:
            try:
                io.write_op(0, 0x00)
                io.write_op(1, 0x00)
                print("  [OK] ปิดเอาต์พุตทั้งหมดแล้ว (OP0 = 0, OP1 = 0)")
            except Exception as e:
                print(f"  {RED}[!!] ปิดเอาต์พุตไม่สำเร็จ: {e}{RESET}")
                print(f"  {RED}     ไปตัดไฟ/ลมที่ตัวเครื่องด้วยตัวเองทันที{RESET}")
        else:
            print("  [--] ไม่มีการเชื่อมต่อ ไม่ได้สั่งเอาต์พุตอะไรไว้")

        io.close()
        if stop_reason:
            print(f"  หยุดเพราะ: {stop_reason}")
        print(f"  จำนวนรอบ — กระบอก A: {ch_a.cycles}  |  กระบอก B: {ch_b.cycles}")
        print("=" * 60)


if __name__ == "__main__":
    main()
