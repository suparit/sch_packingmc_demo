"""
====================================================
IO BIT PROBE — ไล่หาว่าช่องบนบอร์ดตรงกับบิตไหนใน Modbus
====================================================
สั่งเอาต์พุตทีละบิต แล้วให้คนฟังเสียงคลิก/ดูไฟ เพื่อจับคู่
  "ช่องที่เขียนบนบอร์ด"  <->  "บิตใน Modbus"

ใช้โครงการเชื่อมต่อเดียวกับ op_blink_stress.py ซึ่งพิสูจน์แล้วว่า
รันที่ 10 ms ต่อเนื่อง 20 วินาทีโดยไม่หลุด (recv_exact + heartbeat 1 วิ)

----------------------------------------------------
คำเตือน
----------------------------------------------------
สคริปต์นี้สั่งเอาต์พุตจริง ถ้าโซลินอยด์ต่อลมอยู่ กระบอกสูบจะขยับ
-> ใช้ตอนถอดลมออกแล้ว หรือมั่นใจว่าปลอดภัย

ปิด gateway / START_FULL.bat ก่อนรัน

วิธีรัน
   01_DigitalTwin/.venv/Scripts/python.exe 01_DigitalTwin/tools/io_bit_probe.py
====================================================
"""

import os
import socket
import sys
import time

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

SOCKET_TIMEOUT = 0.5
IDN_INTERVAL = 0.5        # heartbeat — บอร์ดตัดการเชื่อมต่อถ้าเงียบนานเกิน ~3 วิ

OPBASE = 64
IPBASE = 0

PROBE_BANKS = [0]         # ธนาคารเอาต์พุตที่จะไล่ (0 = OP0 addr 64)
PROBE_BITS = [0, 1, 6, 7]  # บิตที่จะไล่ ใส่ range(8) ถ้าอยากไล่ครบ
ON_SECONDS = 2.0
OFF_SECONDS = 1.0


class SCHClient:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.sock = None
        self.tid = 0
        self.next_idn = 0.0

    def next_tid(self):
        self.tid = (self.tid + 1) & 0xFFFF
        return self.tid.to_bytes(2, "big")

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(SOCKET_TIMEOUT)
        self.sock.connect((self.ip, self.port))
        self.next_idn = time.time()
        return True

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
        """ส่ง heartbeat ถ้าถึงเวลา — ต้องเรียกบ่อยๆ ระหว่างรอ"""
        now = time.time()
        if now >= self.next_idn:
            self.sock.sendall(b"*IDN?\n")
            self.recv_line()
            self.next_idn = now + IDN_INTERVAL

    def read_bank(self, addr):
        pkt = (
            self.next_tid() + b"\x00\x00" + b"\x00\x06" +
            UNIT_ID.to_bytes(1, "big") + b"\x01" +
            addr.to_bytes(2, "big") + b"\x00\x08"
        )
        self.sock.sendall(pkt)
        return self.recv_exact(10)[9]

    def write_bank(self, addr, value):
        pkt = (
            self.next_tid() + b"\x00\x00" + b"\x00\x08" +
            UNIT_ID.to_bytes(1, "big") + b"\x0F" +
            addr.to_bytes(2, "big") + b"\x00\x08" +
            b"\x01" + value.to_bytes(1, "big")
        )
        self.sock.sendall(pkt)
        self.recv_exact(12)

    def wait(self, seconds, addr, value):
        """รอโดยยัง refresh เอาต์พุตและส่ง heartbeat ไปด้วย"""
        end = time.time() + seconds
        while time.time() < end:
            self.write_bank(addr, value)
            self.beat()
            time.sleep(0.1)


def main():
    io = SCHClient(H7_IP, H7_PORT)
    try:
        io.connect()
        io.beat()
        print("[OK] connected\n")

        print("สถานะอินพุตตอนนี้")
        print("  IP0 (addr %d) = %s" % (IPBASE, format(io.read_bank(IPBASE), "08b")))
        print("  IP1 (addr %d) = %s" % (IPBASE + 8, format(io.read_bank(IPBASE + 8), "08b")))
        io.beat()
        print()
        print("=" * 52)
        print(" เริ่มไล่บิตเอาต์พุต — ฟังเสียงคลิก / ดูไฟ")
        print("=" * 52)

        for bank in PROBE_BANKS:
            addr = OPBASE + 8 * bank
            for b in PROBE_BITS:
                val = 1 << b
                print("\n  >>> OP%d  bit %d   (value 0b%s)  เปิด %.1f วิ" %
                      (bank, b, format(val, "08b"), ON_SECONDS), flush=True)
                io.wait(ON_SECONDS, addr, val)
                io.write_bank(addr, 0)
                io.beat()
                print("      ปิดแล้ว", flush=True)
                io.wait(OFF_SECONDS, addr, 0)

        print("\n" + "=" * 52)

    except Exception as e:
        print("[ERR]", type(e).__name__, e)

    finally:
        try:
            if io.sock:
                io.write_bank(OPBASE, 0)
                io.write_bank(OPBASE + 8, 0)
                print(" [OK] ปิดเอาต์พุตทั้งหมดแล้ว")
        except Exception as e:
            print(" [!!] ปิดเอาต์พุตไม่สำเร็จ:", e)
        io.close()


if __name__ == "__main__":
    main()
