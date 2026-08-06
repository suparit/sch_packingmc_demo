import websocket
import json
import sys

def send_decision(value):
    try:
        ws = websocket.create_connection("ws://localhost:8765", timeout=3)
        decision_value = str(value).upper() == "PASS"
        payload = json.dumps({"action": "DECISION", "value": decision_value})
        ws.send(payload)
        print(f"Sent DECISION: {value}")
        ws.close()
    except Exception as e:
        print("Error sending decision:", e)

if __name__ == '__main__':
    val = sys.argv[1] if len(sys.argv) > 1 else 'PASS'
    send_decision(val)
