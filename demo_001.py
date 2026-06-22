import socket
import time

# ==================================================
# CONFIG
# ==================================================
H7_IP   = "192.168.0.100"
H7_PORT = 502
UNIT_ID = 1

# ---- Timing (stress mode)
IO_PERIOD    = 0.01     # 10 ms (ลองกดลง)
UI_PERIOD    = 0.5
BLINK_PERIOD = 0.05

SOCKET_TIMEOUT  = 0.5
RECONNECT_DELAY = 0.5

IPBASE = 0
OPBASE = 64

# ==================================================
# GLOBAL PERF
# ==================================================
q_count = 0
q_start = time.time()
q_rate  = 0.0

lat_last = 0.0
lat_min  = 9999.0
lat_max  = 0.0

cycle_last = 0.0
cycle_min  = 9999.0
cycle_max  = 0.0

error_count = 0

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
        self.tid = 0

    def next_tid(self):
        self.tid = (self.tid + 1) & 0xFFFF
        return self.tid.to_bytes(2, 'big')

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(SOCKET_TIMEOUT)
            self.sock.connect((self.ip, self.port))
            print("✅ Connected")
            return True
        except Exception as e:
            print("❌ Connect fail:", e)
            self.sock = None
            return False

    def close(self):
        if self.sock:
            self.sock.close()
        self.sock = None
        print("🔁 Socket closed")

    def send(self, data):
        self.sock.sendall(data)

    def recv_exact(self, n):
        buf = b''
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise RuntimeError("Socket closed")
            buf += chunk
        return buf

    # ---------------------------
    # MODBUS READ
    # ---------------------------
    def read_ip(self, bank):
        global q_count, lat_last, lat_min, lat_max

        addr = IPBASE + 8 * bank

        pkt = (
            self.next_tid() +
            b'\x00\x00' +
            b'\x00\x06' +
            UNIT_ID.to_bytes(1,'big') +
            b'\x01' +
            addr.to_bytes(2,'big') +
            b'\x00\x08'
        )

        self.send(pkt)

        t0 = time.perf_counter()
        resp = self.recv_exact(10)
        dt = (time.perf_counter() - t0) * 1000

        # latency stat
        lat_last = dt
        lat_min  = min(lat_min, dt)
        lat_max  = max(lat_max, dt)

        q_count += 1

        return resp[9]

    # ---------------------------
    # MODBUS WRITE
    # ---------------------------
    def write_op(self, bank, value):
        global q_count, lat_last, lat_min, lat_max

        addr = OPBASE + 8 * bank

        pkt = (
            self.next_tid() +
            b'\x00\x00' +
            b'\x00\x08' +
            UNIT_ID.to_bytes(1,'big') +
            b'\x0F' +
            addr.to_bytes(2,'big') +
            b'\x00\x08' +
            b'\x01' +
            value.to_bytes(1,'big')
        )

        self.send(pkt)

        t0 = time.perf_counter()
        self.recv_exact(12)
        dt = (time.perf_counter() - t0) * 1000

        lat_last = dt
        lat_min  = min(lat_min, dt)
        lat_max  = max(lat_max, dt)

        q_count += 1

# ==================================================
# MAIN
# ==================================================
io = SCHClient(H7_IP, H7_PORT)

t_io = 0
t_ui = 0
t_blink = 0

blink = False

connect_count = 0
reconnect_count = 0
start_time = time.time()

ip0 = ip1 = 0
op0 = op1 = 0
last_op0 = None
last_op1 = None

print("=== STRESS TEST START ===")

while True:

    if io.sock is None:
        if not io.connect():
            time.sleep(RECONNECT_DELAY)
            continue

        connect_count += 1
        if connect_count > 1:
            reconnect_count += 1

        now = time.time()
        t_io = t_ui = now

    try:
        now = time.time()

        # ==================================================
        # IO LOOP (MEASURE CYCLE)
        # ==================================================
        if now >= t_io:
            #global cycle_last, cycle_min, cycle_max

            t0 = time.perf_counter()

            ip0 = io.read_ip(0)
            ip1 = io.read_ip(1)

            if now - t_blink >= BLINK_PERIOD:
                t_blink = now
                blink = not blink

            if blink:
                op0, op1 = 0xFF, 0x00
            else:
                op0, op1 = 0x00, 0xFF

            if op0 != last_op0:
                io.write_op(0, op0)
                last_op0 = op0

            if op1 != last_op1:
                io.write_op(1, op1)
                last_op1 = op1

            dt = (time.perf_counter() - t0) * 1000

            cycle_last = dt
            cycle_min  = min(cycle_min, dt)
            cycle_max  = max(cycle_max, dt)

            t_io = now + IO_PERIOD

        # ==================================================
        # PERF CALC (10s window)
        # ==================================================
        if now - q_start >= 10.0:
            elapsed = now - q_start
            q_rate = q_count / elapsed

            q_count = 0
            q_start = now

        # ==================================================
        # UI
        # ==================================================
        if now >= t_ui:
            runtime = now - start_time
            reconn_rate = reconnect_count / runtime if runtime > 0 else 0

            print("\033[H", end="")

            print("==============================================")
            print(" STRESS TEST (MODBUS IO)")
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
            print(f" Reconn/sec : {reconn_rate:.5f}")
            print(f" Errors     : {error_count}")

            print("\n==============================================")

            t_ui = now + UI_PERIOD

    except Exception as e:
        error_count += 1
        print("❌ Error:", e)
        io.close()
        time.sleep(RECONNECT_DELAY)
