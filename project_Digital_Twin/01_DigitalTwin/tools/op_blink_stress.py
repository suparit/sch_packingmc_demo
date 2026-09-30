"""
====================================================
OP BLINK / STRESS TEST — ทดสอบเอาต์พุตทั้ง 2 โมดูลขยาย
====================================================
สลับเปิด OP0 <-> OP1 เพื่อดูว่าแผ่นขยาย I/O แผ่นไหนตอบสนอง address ไหน

สถาปัตยกรรมของบอร์ด (ยืนยัน 2 ก.ย. 2026)
  - บอร์ด CPU/เครือข่าย 1 ตัว  = 1 IP = 192.168.0.100 (สถานี Modbus เดียว)
  - แผ่นขยาย I/O 2 แผ่นเสียบซ้อนอยู่บน CPU ตัวเดียวกัน
  - แยกกันด้วย "ช่วง address ของ Modbus" ไม่ใช่คนละ IP

----------------------------------------------------
คำเตือน
----------------------------------------------------
สคริปต์นี้สั่ง 0xFF = เปิดเอาต์พุตทั้ง 8 ช่องพร้อมกัน และสลับเร็ว
ถ้ามีโซลินอยด์/วาล์วต่ออยู่และ "ต่อลมไว้" กระบอกสูบจะกระแทกรัว
-> ใช้ตอนถอดลมออกแล้วเท่านั้น หรือปรับ BLINK_PERIOD ให้ช้าลง

ปิด gateway / START_FULL.bat ก่อนรัน ไม่งั้นจะแย่งกันเขียนเอาต์พุต

วิธีรัน
   01_DigitalTwin/.venv/Scripts/python.exe 01_DigitalTwin/tools/op_blink_stress.py
====================================================
"""

import os
import socket
import sys
import time

# กับดัก path ภาษาไทย: console Windows เป็น cp1252 -> print ไทยแล้วพัง
if os.name == "nt":
    os.system("chcp 65001 > nul")
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==================================================
# CONFIG
# ==================================================
H7_IP = "192.168.0.100"
H7_PORT = 502
UNIT_ID = 1

IO_PERIOD = 0.01          # 10 ms — โหมด stress (ค่าที่จูนไว้ปลอดภัยคือ 0.02)
UI_PERIOD = 0.5
BLINK_PERIOD = 0.2        # เพิ่มค่านี้ถ้าต่อลมแล้วไม่อยากให้กระบอกกระแทก

IDN_INTERVAL = 1.0        # heartbeat ที่บอร์ดต้องการ (ตัวเดิมไม่มี เพิ่มเข้ามา)

SOCKET_TIMEOUT = 0.5
RECONNECT_DELAY = 0.5

RUN_SECONDS = 20          # 0 = ไม่จำกัด, ใส่ตัวเลขเพื่อให้หยุดเองและปิดเอาต์พุต

IPBASE = 0
OPBASE = 64

# ==================================================
# สถิติ
# ==================================================
q_count = 0
q_start = time.time()
q_rate = 0.0

lat_last = 0.0
lat_min = 9999.0
lat_max = 0.0

cycle_last = 0.0
cycle_min = 9999.0
cycle_max = 0.0

error_count = 0


def bits_spaced(v: int) -> str:
    b = format(v, "08b")
    return " ".join(b[:4]) + " | " + " ".join(b[4:])


# ==================================================
# CLIENT
# ==================================================
class SCHClient:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.sock = None
        self.tid = 0

    def next_tid(self):
        self.tid = (self.tid + 1) & 0xFFFF
        return self.tid.to_bytes(2, "big")

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(SOCKET_TIMEOUT)
            self.sock.connect((self.ip, self.port))
            print("[OK] Connected")
            return True
        except Exception as e:
            print("[FAIL] Connect:", e)
            self.sock = None
            return False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def send(self, data):
        self.sock.sendall(data)

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

    def read_ip(self, bank):
        global q_count, lat_last, lat_min, lat_max
        addr = IPBASE + 8 * bank
        pkt = (
            self.next_tid() + b"\x00\x00" + b"\x00\x06" +
            UNIT_ID.to_bytes(1, "big") + b"\x01" +
            addr.to_bytes(2, "big") + b"\x00\x08"
        )
        self.send(pkt)
        t0 = time.perf_counter()
        resp = self.recv_exact(10)
        dt = (time.perf_counter() - t0) * 1000
        lat_last = dt
        lat_min = min(lat_min, dt)
        lat_max = max(lat_max, dt)
        q_count += 1
        return resp[9]

    def write_op(self, bank, value):
        global q_count, lat_last, lat_min, lat_max
        addr = OPBASE + 8 * bank
        pkt = (
            self.next_tid() + b"\x00\x00" + b"\x00\x08" +
            UNIT_ID.to_bytes(1, "big") + b"\x0F" +
            addr.to_bytes(2, "big") + b"\x00\x08" +
            b"\x01" + value.to_bytes(1, "big")
        )
        self.send(pkt)
        t0 = time.perf_counter()
        self.recv_exact(12)
        dt = (time.perf_counter() - t0) * 1000
        lat_last = dt
        lat_min = min(lat_min, dt)
        lat_max = max(lat_max, dt)
        q_count += 1


# ==================================================
# MAIN
# ==================================================
def main():
    global q_count, q_start, q_rate, error_count
    global cycle_last, cycle_min, cycle_max

    io = SCHClient(H7_IP, H7_PORT)

    t_io = t_ui = t_blink = 0.0
    next_idn = 0.0
    blink = False

    connect_count = 0
    reconnect_count = 0
    start_time = time.time()

    ip0 = ip1 = 0
    op0 = op1 = 0
    last_op0 = last_op1 = None

    print("=== OP BLINK / STRESS TEST START ===")

    try:
        while True:
            if RUN_SECONDS and (time.time() - start_time) >= RUN_SECONDS:
                break

            if io.sock is None:
                if not io.connect():
                    time.sleep(RECONNECT_DELAY)
                    continue
                connect_count += 1
                if connect_count > 1:
                    reconnect_count += 1
                now = time.time()
                t_io = t_ui = next_idn = now
                last_op0 = last_op1 = None

            try:
                now = time.time()

                if now >= next_idn:
                    io.send(b"*IDN?\n")
                    io.recv_line()
                    next_idn = now + IDN_INTERVAL

                if now >= t_io:
                    t0 = time.perf_counter()

                    ip0 = io.read_ip(0)
                    ip1 = io.read_ip(1)

                    if now - t_blink >= BLINK_PERIOD:
                        t_blink = now
                        blink = not blink

                    op0, op1 = (0xFF, 0x00) if blink else (0x00, 0xFF)

                    if op0 != last_op0:
                        io.write_op(0, op0)
                        last_op0 = op0
                    if op1 != last_op1:
                        io.write_op(1, op1)
                        last_op1 = op1

                    dt = (time.perf_counter() - t0) * 1000
                    cycle_last = dt
                    cycle_min = min(cycle_min, dt)
                    cycle_max = max(cycle_max, dt)
                    t_io = now + IO_PERIOD

                if now - q_start >= 10.0:
                    q_rate = q_count / (now - q_start)
                    q_count = 0
                    q_start = now

                if now >= t_ui:
                    runtime = now - start_time
                    print("\033[H", end="")
                    print("==============================================")
                    print(" OP BLINK / STRESS TEST")
                    print("==============================================\n")
                    print("INPUT")
                    print(f" IP0 : {bits_spaced(ip0)}")
                    print(f" IP1 : {bits_spaced(ip1)}\n")
                    print("OUTPUT")
                    print(f" OP0 : {bits_spaced(op0)}")
                    print(f" OP1 : {bits_spaced(op1)}\n")
                    print("PERFORMANCE")
                    print(f" Query/sec  : {q_rate:8.1f}")
                    print(f" Latency ms : {lat_last:6.2f} (min {lat_min:.2f} / max {lat_max:.2f})")
                    print(f" Cycle  ms  : {cycle_last:6.2f} (min {cycle_min:.2f} / max {cycle_max:.2f})")
                    print("\nNETWORK")
                    print(f" Runtime    : {runtime:.1f} sec")
                    print(f" Connect    : {connect_count}")
                    print(f" Reconnect  : {reconnect_count}")
                    print(f" Errors     : {error_count}")
                    print("\n==============================================")
                    t_ui = now + UI_PERIOD

            except Exception as e:
                error_count += 1
                print("[ERR]", e)
                io.close()
                time.sleep(RECONNECT_DELAY)

    except KeyboardInterrupt:
        pass

    finally:
        # ปิดเอาต์พุตทุกช่องก่อนออกเสมอ
        print("\n" + "=" * 46)
        if io.sock is not None:
            try:
                io.write_op(0, 0x00)
                io.write_op(1, 0x00)
                print(" [OK] ปิดเอาต์พุตแล้ว OP0=0 OP1=0")
            except Exception as e:
                print(f" [!!] ปิดเอาต์พุตไม่สำเร็จ: {e} -> ไปตัดไฟเอง")
        io.close()
        rt = time.time() - start_time
        print(f" runtime {rt:.1f}s  connect={connect_count}  reconnect={reconnect_count}  errors={error_count}")
        print("=" * 46)


if __name__ == "__main__":
    main()
