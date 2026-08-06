# ws_test_client.py
import websocket
import time
import json

try:
    ws = websocket.create_connection("ws://localhost:8765", timeout=5)
    ws.settimeout(1.0)
    print("Connected to ws://localhost:8765")
    for i in range(10):
        try:
            msg = ws.recv()   # จะ timeout เป็นครั้งคราวถ้าไม่มีข้อความ
            print("GOT:", msg)
        except websocket._exceptions.WebSocketTimeoutException:
            print("No message yet (timeout)")
        time.sleep(0.1)
    ws.close()
except Exception as e:
    print("CONNECT ERROR:", e)