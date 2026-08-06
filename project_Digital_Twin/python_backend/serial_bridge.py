"""
serial_bridge.py — สะพานเชื่อมจอ HMI บนบอร์ด STM32H7S78-DK เข้ากับ Digital Twin

    [บอร์ด STM32] ←UART4/ST-LINK VCP→ [สคริปต์นี้] ←TCP 8766→ [gateway_fsm.py]

หน้าที่:
  1. รับ broadcast สถานะ FSM จาก gateway_fsm.py แล้วสตรีมลงบอร์ดทุก 100ms
     (จอ MainScreen บนบอร์ดจะแสดง state/ตัวนับ/อุณหภูมิ/Target/Pitch แบบ Real-time)
  2. รับคำสั่งจากปุ่มบนจอบอร์ด (START/STOP/RESET/SET_PARAMS) ส่งต่อให้ Gateway
  3. รับคำขอข้อมูลหน้า Report (REQ_REPORT_DATA ฯลฯ) ส่งต่อและตีคำตอบกลับลงบอร์ด

วิธีใช้:
    pip install pyserial
    python serial_bridge.py            # หา COM port ของ ST-LINK อัตโนมัติ
    python serial_bridge.py COM5       # หรือระบุพอร์ตเอง

ลำดับการรัน: gateway_fsm.py ก่อน → แล้วค่อยรันสคริปต์นี้ → เสียบบอร์ด
"""
import json
import socket
import sys
import threading
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[X] ยังไม่ได้ติดตั้ง pyserial - พิมพ์:  pip install pyserial")
    sys.exit(1)

# console ไทยเป็น cp874 — ถ้าไม่บังคับ utf-8 ตรงนี้ พอ redirect stdout
# (เช่นถูกเรียกจาก start_all.bat หรือเก็บ log ลงไฟล์) จะตายด้วย UnicodeEncodeError
# แล้วรายงานผิดเป็น "ต่อ gateway ไม่ได้" ทำให้ไล่บั๊กผิดทาง
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GATEWAY_ADDR = ("127.0.0.1", 8766)
BAUDRATE = 115200
DOWNLINK_INTERVAL = 0.1   # สตรีมสถานะลงบอร์ดทุก 100ms


def find_stlink_port():
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "") + " " + (p.manufacturer or "")
        if "STLink" in desc or "ST-Link" in desc or "STMicroelectronics" in desc:
            return p.device
    return None


def tcp_one_shot(payload_line, want_response=False, timeout=2.0):
    """เปิดสาย TCP ยิงคำสั่ง 1 บรรทัด (พฤติกรรมเดียวกับปุ่มบน Simulator)"""
    try:
        s = socket.create_connection(GATEWAY_ADDR, timeout=timeout)
        s.settimeout(timeout)
        s.sendall(payload_line + b"\n")
        if not want_response:
            s.close()
            return None
        chunks = []
        try:
            while True:
                d = s.recv(4096)
                if not d:
                    break
                chunks.append(d)
        except socket.timeout:
            pass
        s.close()
        return b"".join(chunks).strip()
    except Exception as e:
        print(f"⚠️ [TCP] ติดต่อ Gateway ไม่ได้: {e}")
        return None


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_stlink_port()
    if not port:
        print("❌ หา COM port ของ ST-LINK ไม่เจอ — เสียบสาย USB บอร์ดแล้วลองใหม่ หรือระบุเอง เช่น: python serial_bridge.py COM5")
        sys.exit(1)

    ser = serial.Serial(port, BAUDRATE, timeout=0.05)
    ser_lock = threading.Lock()
    print("=" * 56)
    print(f"🔗 [SERIAL BRIDGE] {port} @ {BAUDRATE} ↔ tcp://{GATEWAY_ADDR[0]}:{GATEWAY_ADDR[1]}")
    print("=" * 56)

    latest_state = [None]

    # ── เธรด 1: เกาะสาย Gateway รับ broadcast สถานะล่าสุดตลอดเวลา ──
    def monitor_gateway():
        while True:
            try:
                s = socket.create_connection(GATEWAY_ADDR, timeout=2)
                s.settimeout(2)
                print("✅ [TCP] เชื่อมต่อ Gateway สำเร็จ — เริ่มสตรีมสถานะลงบอร์ด")
                buf = b""
                while True:
                    d = s.recv(4096)
                    if not d:
                        break
                    buf += d
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if line.strip():
                            latest_state[0] = line.strip()
            except Exception:
                pass
            print("🔁 [TCP] หลุดจาก Gateway — ลองต่อใหม่ใน 2 วิ...")
            time.sleep(2)

    # ── เธรด 2: สตรีมสถานะล่าสุดลงบอร์ดทุก 100ms (throttle กัน UART ล้น) ──
    def downlink_to_board():
        while True:
            time.sleep(DOWNLINK_INTERVAL)
            line = latest_state[0]
            if line:
                try:
                    with ser_lock:
                        ser.write(line + b"\n")
                except Exception as e:
                    print(f"⚠️ [SERIAL] เขียนลงบอร์ดไม่ได้: {e}")

    threading.Thread(target=monitor_gateway, daemon=True).start()
    threading.Thread(target=downlink_to_board, daemon=True).start()

    # ── ลูปหลัก: อ่านคำสั่งจากบอร์ด แล้วส่งต่อให้ Gateway ──
    rx_buf = b""
    while True:
        try:
            data = ser.read(512)
        except Exception as e:
            print(f"❌ [SERIAL] อ่านพอร์ตไม่ได้ ({e}) — เช็คสาย USB แล้วรันใหม่")
            break

        if not data:
            continue
        rx_buf += data

        while b"\n" in rx_buf:
            line, rx_buf = rx_buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue

            try:
                text = line.decode("utf-8", errors="replace")
            except Exception:
                continue
            print(f"📩 [BOARD →] {text}")

            if b'"cmd"' in line:
                # คำขอข้อมูลหน้า Report — ต้องเอาคำตอบตีกลับลงบอร์ด
                resp = tcp_one_shot(line, want_response=True)
                if resp:
                    with ser_lock:
                        ser.write(resp + b"\n")
                    print(f"📤 [→ BOARD] response {len(resp)} bytes")
            elif b'"action"' in line:
                # คำสั่งปุ่มกด START/STOP/RESET/SET_PARAMS
                tcp_one_shot(line, want_response=False)
            # บรรทัดอื่นๆ (log จากบอร์ด) — แสดงเฉยๆ


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Serial bridge stopped by user")
