import socket
import time
import os

# ==================================================
# CONFIG
# ==================================================
H7_IP   = "192.168.0.100"
H7_PORT = 502
UNIT_ID = 1

# ---- Timing (tuned for stability)
IDN_INTERVAL    = 1.0      # <= 1 Hz
LOOP_DELAY      = 0.02     # 20 ms
BLINK_PERIOD    = 0.3

SOCKET_TIMEOUT  = 0.5
RECONNECT_DELAY = 0.5

# ---- MODBUS MAP
IPBASE_ADDRESS = 0
OPBASE_ADDRESS = 64

# ==================================================
# GLOBAL OUTPUT IMAGE
# ==================================================
OP0 = 0x00
OP1 = 0x00

# ==================================================
# NETWORK HEALTH MONITOR
# ==================================================
connect_count = 0
reconnect_count = 0
last_disconnect_time = 0
start_time = time.time()

# ==================================================
# UTIL
# ==================================================
def bits_spaced(v: int) -> str:
    b = format(v, "08b")
    return " ".join(b[:4]) + " | " + " ".join(b[4:])

def hal_ms_to_hms(ms):
    ms = int(ms)
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02}:{m:02}:{s:02};{ms:03}"

# ==================================================
# CLIENT
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
            print("✅ Connected to H7")
            return True
        except Exception as e:
            print("❌ Connect failed:", e)
            self.sock = None
            return False

    def close(self):
        if self.sock:
            self.sock.close()
        self.sock = None
        print("🔁 Socket closed")

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

    # -------- READ INPUT
    def read_ip(self, bank):
        addr = IPBASE_ADDRESS + 8 * bank
        pkt = (
            b'\x00\x00\x00\x00\x00\x06' +
            UNIT_ID.to_bytes(1,'big') +
            b'\x01' +
            addr.to_bytes(2,'big') +
            b'\x00\x08'
        )
        self.send(pkt)
        resp = self.sock.recv(10)
        return resp[9]

    # -------- WRITE OUTPUT
    def write_op(self, bank, value):
        addr = OPBASE_ADDRESS + 8 * bank
        pkt = (
            b'\x00\x00\x00\x00\x00\x08' +
            UNIT_ID.to_bytes(1,'big') +
            b'\x0F' +
            addr.to_bytes(2,'big') +
            b'\x00\x08' +
            b'\x01' +
            value.to_bytes(1,'big')
        )
        self.send(pkt)
        self.sock.recv(12)

# ==================================================
# MAIN
# ==================================================
io = SCHClient(H7_IP, H7_PORT)

next_idn = 0.0
last_blink = 0.0
blink_state = False

# parsed info
station_id = "?"
fw_version = "?"
hal = 0

print("=== SCH IO PROCESS START ===")

while True:
    if io.sock is None:
        if not io.connect():
            time.sleep(RECONNECT_DELAY)
            continue

        connect_count += 1
        if connect_count > 1:
            reconnect_count += 1

        next_idn = time.time()

    try:
        now = time.time()

        # -------- HEARTBEAT (*IDN?)
        if now >= next_idn:
            io.send(b"*IDN?\n")

            line = io.recv_line().decode().strip()
            parts = line.split(';')

            for p in parts:
                if p.startswith("FW:"):
                    fw_version = p[3:]
                elif p.startswith("ID:"):
                    station_id = p[3:]
                elif p.startswith("T:"):
                    hal = int(p[2:])

            next_idn = now + IDN_INTERVAL

        # -------- READ INPUT
        ip0 = io.read_ip(0)
        ip1 = io.read_ip(1)

        # -------- RESET OUTPUT IMAGE
        OP0 = 0x00
        OP1 = 0x00

        # -------- FSM: BLINK
        if now - last_blink >= BLINK_PERIOD:
            last_blink = now
            blink_state = not blink_state

        if blink_state:
            OP0 = 0xFF
            OP1 = 0x00
        else:
            OP0 = 0x00
            OP1 = 0xFF

        # -------- WRITE OUTPUT
        io.write_op(0, OP0)
        io.write_op(1, OP1)

        # -------- MONITOR
        runtime = now - start_time

        if runtime > 0:
            reconn_rate = reconnect_count / runtime
        else:
            reconn_rate = 0

        # -------- DASHBOARD
        os.system("cls" if os.name == "nt" else "clear")

        print("==============================================")
        print(" SCH IO PROCESS  (LIVE OUTPUT)")
        print("==============================================\n")

        print("INPUT")
        print(f" IP0 : {bits_spaced(ip0)}")
        print(f" IP1 : {bits_spaced(ip1)}\n")

        print("OUTPUT")
        print(f" OP0 : {bits_spaced(OP0)}")
        print(f" OP1 : {bits_spaced(OP1)}\n")

        print("SYSTEM")
        print(f" Stage      : BLINK_TEST")
        print(f" Station    : {station_id}")
        print(f" FW Ver     : {fw_version}")
        print(f" Uptime     : {hal_ms_to_hms(hal)}")

        print("\nNETWORK")
        print(f" Runtime    : {runtime:.1f} sec")
        print(f" Connect    : {connect_count}")
        print(f" Reconnect  : {reconnect_count}")
        print(f" Reconn/sec : {reconn_rate:.5f}")

        print("\n==============================================")

        time.sleep(LOOP_DELAY)

    except Exception as e:
        print("❌ Error:", e)
        last_disconnect_time = time.time()
        io.close()
        time.sleep(RECONNECT_DELAY)
 
