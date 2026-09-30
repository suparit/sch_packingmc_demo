import json
import socket
import sys
import time

# ==========================================
# 📊 1. ตัวแปรเก็บข้อมูลสถิติจริง (Machine State)
# ==========================================
machine_state = {
    # Data หน้าแรก (MainScreen)
    "status": "RUNNING",
    "fsm_state": "SEAL_PROCESS",
    "alarm": "NONE",
    "heater_left": 189,
    "heater_right": 189,
    "heater_on": True,
    "cycle_time": 1.20,
    "pitch": 24,
    "actual": 152,
    "target": 200,
}

# Data หน้า 2 (ReportScreen)
ok_parts_count = 148
ng_parts_count = 4

alarm_logs_list = [
    "[14:15:02] HEATER OVERHEATED (209 C)",
    "[13:40:12] CARRIER TAPE EMPTY",
    "[11:05:44] EMERGENCY STOP PRESSED",
    "[09:20:10] SYSTEM INITIALIZED",
    "[08:00:00] POWER ON SYSTEM READY",
]

# ตัวอย่างข้อมูล Live SQL Transition Ledger (รูปแบบเดียวกับ backend จริง gateway_fsm.py)
ledger_rows_list = [
    "14:15:02 SEAL_PROCESS 1.52s AUTO #8 FRICTION",
    "14:15:01 COUNT_ACCUMULATE 0.40s AUTO #8 NORMAL",
    "14:15:00 COUNT_CHECK 0.50s AUTO #8 NORMAL",
    "14:14:59 COUNT_PROCESS 0.51s AUTO #8 NORMAL",
    "14:14:58 FEED_CARRIER 1.02s AUTO #8 NORMAL",
    "14:14:57 CHECK_TEMP 0.41s AUTO #8 NORMAL",
    "14:14:56 VISION 0.40s AUTO #8 NORMAL",
    "14:14:55 LOAD_PART 0.80s AUTO #8 NORMAL",
    "14:14:54 ALARM 0.50s AUTO #7 TRIPPED",
    "14:14:53 TAKEUP_REEL 1.01s AUTO #7 NORMAL",
]


def start_gateway_server(host="127.0.0.1", port=8766):
  server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  # ⚠️ mock ตัวนี้ใช้ทดสอบ GUI เดี่ยวๆ เท่านั้น ห้ามรันพร้อม python_backend/gateway_fsm.py (พอร์ต 8766 ชนกัน)
  # ใช้ SO_EXCLUSIVEADDRUSE บน Windows เพื่อให้ bind ซ้อนแล้ว error ทันที ไม่เงียบหาย
  if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
  else:
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

  try:
    server_socket.bind((host, port))
    server_socket.listen(5)
    # ⚡ ตั้งค่า Timeout ที่ตัว Server ป้องกันการค้าง ทำให้กด Ctrl+C ยกเลิกได้ทันที!
    server_socket.settimeout(1.0)
    print("==========================================")
    print(f"🚀 Python Gateway Running on {host}:{port}")
    print("   (Press Ctrl+C anytime to stop)")
    print("==========================================")
  except Exception as e:
    print(f"❌ Cannot start server on port {port}: {e}")
    sys.exit(1)

  while True:
    try:
      # ลองรอการเชื่อมต่อ
      try:
        conn, addr = server_socket.accept()
      except socket.timeout:
        continue  # ถ้านานเกิน 1 วินาทีแล้วไม่มีใครต่อเข้ามา ให้ลูปใหม่เพื่อเปิดโอกาสให้ดักจับ Ctrl+C

      conn.settimeout(1.0)
      data_bytes = conn.recv(1024)

      if data_bytes:
        raw_data = data_bytes.decode("utf-8").strip()
        print(f"📩 [Recv]: {raw_data}")

        # ----------------------------------------------------
        # 📥 1. คำสั่งหน้า 2 (ReportScreen)
        # ----------------------------------------------------
        if "REQ_REPORT_DATA" in raw_data:
          total = machine_state["actual"]
          ok = ok_parts_count
          ng = ng_parts_count
          yield_rate = round((ok / total) * 100, 1) if total > 0 else 0.0
          logs_text = "\n".join(alarm_logs_list)

          response = {
              "total": total,
              "ok": ok,
              "ng": ng,
              "yield": yield_rate,
              "log_text": logs_text,
              "ledger_text": "\n".join(ledger_rows_list),
          }
          # separators แบบไม่มีช่องว่าง ให้ตรงกับ parser ฝั่ง TouchGFX
          conn.sendall(json.dumps(response, separators=(",", ":")).encode("utf-8"))
          print(f"📤 [Sent Report]: {response}")

        elif "CLEAR_SQL_HISTORY" in raw_data:
          ledger_rows_list.clear()
          ledger_rows_list.append("NO SQL DATA YET")
          alarm_logs_list.clear()
          alarm_logs_list.append("[SYSTEM] SQL history cleared.")
          conn.sendall(json.dumps({"status": "cleared"}, separators=(",", ":")).encode("utf-8"))

        elif "EXPORT_CSV" in raw_data:
          conn.sendall(json.dumps({"status": "saved", "file": "report_mock_test.csv"}, separators=(",", ":")).encode("utf-8"))

        elif "CLEAR_ALARM_LOGS" in raw_data:
          alarm_logs_list.clear()
          alarm_logs_list.append("[SYSTEM] Alarm logs cleared.")
          conn.sendall(json.dumps({"status": "cleared"}, separators=(",", ":")).encode("utf-8"))

        # ----------------------------------------------------
        # 📥 2. คำสั่งหน้าแรก (MainScreen)
        # ----------------------------------------------------
        else:
          conn.sendall(json.dumps(machine_state).encode("utf-8"))

      conn.close()

    except KeyboardInterrupt:
      print("\n🛑 Gateway stopped by user (Ctrl+C)")
      break
    except ConnectionResetError:
      pass
    except Exception as e:
      print(f"⚠️ Error: {e}")

  server_socket.close()


if __name__ == "__main__":
  start_gateway_server()