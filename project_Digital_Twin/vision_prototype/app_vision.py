import cv2
import numpy as np
import serial
import time
import json
from collections import deque
import websocket  
import threading
import queue

WEBSOCKET_URL = "ws://127.0.0.1:8765"
# If True: use simple presence detection (edge_presence_check) to drive DECISION
# in the FSM VISION step. Useful when you only need to know whether a part exists
# in the carrier (no template matching required).
PRESENCE_SENSOR_MODE = True
PRESENCE_DEBOUNCE = 0.5  # seconds of stable presence/absence before sending (shorter for responsiveness)

# =====================================================================
# 🛠️ TIER 0: AGNOSTIC SERIAL RECEIVER (ดึงภาพจากพอร์ต COM10)
# =====================================================================
class OpenMV_Serial_Receiver:
    def __init__(self, port='COM10'):
        self.ser = serial.Serial(port, baudrate=115200, timeout=0.5)
        self.ser.reset_input_buffer()
        print(f"Connected to OpenMV Stream on Port: {port}")
        
    def read_frame(self):
        try:
            size_bytes = self.ser.read(4)
            if len(size_bytes) < 4: return None
            size = int.from_bytes(size_bytes, 'little')
            if size <= 0 or size > 100000:
                self.ser.reset_input_buffer()
                return None
            jpeg_data = self.ser.read(size)
            if len(jpeg_data) < size: return None
            return cv2.imdecode(np.frombuffer(jpeg_data, np.uint8), cv2.IMREAD_COLOR)
        except Exception as e:
            self.ser.reset_input_buffer()
            return None

edge_history = deque(maxlen=5)
template_img = None
capture_notification = ""
notification_timeout = 0

# 🌐 อัปเดตสถานะผ่านกลไก Single-Shot (ดักฟังสเตปผ่านการ Ping ในระบบ)
fsm_current_state = "LOAD_CARRIER"
last_net_check_time = 0
ws_client = None
ws_send_lock = threading.Lock()
in_vision = False
fsm_step_allowed = False
ack_queue = queue.Queue()
ws_listener_thread = None
ws_listener_running = False
last_sync_time = 0.0

# ⏳ ระบบจับเวลา 5 วินาที
last_stable_decision = "NONE"   
decision_stable_start_time = 0 
has_sent_for_current_part = False 

# =====================================================================
# 📡 NETWORKING CORE (ยิงคำสั่งเชื่อมต่อแบบกระชับ รวดเร็ว ไม่แช่ค้าง)
# =====================================================================
def connect_gateway_ws():
    global ws_client
    try:
        if ws_client is None:
            ws_client = websocket.create_connection(WEBSOCKET_URL, timeout=0.5)
            ws_client.settimeout(0.1)
            print("✅ WebSocket connected to gateway")
            start_ws_listener()
        return ws_client
    except Exception as e:
        ws_client = None
        return None


def close_gateway_ws():
    global ws_client
    with ws_send_lock:
        if ws_client is not None:
            try:
                ws_client.close()
            except Exception:
                pass
            ws_client = None


def safe_ws_send(message):
    with ws_send_lock:
        ws = connect_gateway_ws()
        if ws is None:
            return False
        try:
            ws.send(message)
            return True
        except Exception as e:
            print(f"⚠️ [NET] Send failed: {e}")
            close_gateway_ws()
            return False


def sync_fsm_state_live():
    """ ดึงสถานะระบบปัจจุบันจาก FSM ผ่าน connection เดียวที่เปิดไว้ """
    global fsm_current_state, fsm_step_allowed
    try:
        ws = connect_gateway_ws()
        if ws is None:
            return
        # ask gateway to send a LIVE_SYNC update; the background listener
        # thread will receive and apply the state when it arrives. Do not
        # perform a blocking recv here to avoid contention with the listener.
        data = json.dumps({"action": "GET_STATE"})
        if safe_ws_send(data):
            print("[NET] Sent GET_STATE request")
        else:
            print("⚠️ [NET] GET_STATE send failed")
    except Exception:
        # keep previous state if anything goes wrong
        pass


def ws_listener():
    """Background thread that continuously reads websocket messages and
    updates FSM state and ACKs in real-time."""
    global ws_client, ws_listener_running, fsm_current_state, fsm_step_allowed, last_sync_time
    ws_listener_running = True
    while ws_listener_running:
        try:
            ws = connect_gateway_ws()
            if ws is None:
                time.sleep(0.1)
                continue
            raw = None
            try:
                raw = ws.recv()
            except Exception:
                # timeout or temporary recv failure
                time.sleep(0.01)
                continue

            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            mtype = msg.get("type") or msg.get("action")
            if mtype == "LIVE_SYNC":
                system = msg.get("system", {})
                f_state = system.get("current_state")
                if f_state:
                    fsm_current_state = f_state
                    fsm_step_allowed = bool(system.get('step_allowed', False))
                    last_sync_time = time.time()
                    print(f"[SYNC] FSM: {fsm_current_state} | step_allowed={fsm_step_allowed}")
                    print(f"[NET] Received LIVE_SYNC from gateway")
            elif mtype == "DECISION_ACK":
                # push ack into queue for sender to consume
                try:
                    ack_queue.put_nowait(msg)
                except Exception:
                    pass
            else:
                # ignore other messages
                pass
        except Exception:
            # on any unexpected exception, drop and try to reconnect
            close_gateway_ws()
            time.sleep(0.2)


def start_ws_listener():
    global ws_listener_thread, ws_listener_running
    if ws_listener_thread and ws_listener_thread.is_alive():
        return
    ws_listener_running = True
    ws_listener_thread = threading.Thread(target=ws_listener, daemon=True)
    ws_listener_thread.start()


def send_decision_to_gateway(status_string, meta=None, max_retries=3, ack_timeout=1.0):
    """ส่งผลการตัดสินและรอรับ ACK จาก gateway ก่อนยืนยันสำเร็จ
    จะลองส่งซ้ำ `max_retries` ครั้งหากไม่ได้รับ ACK หรือถูกปฏิเสธ
    """
    global ws_client
    decision_value = status_string.upper() == "PASS"
    payload = {"action": "DECISION", "value": decision_value}
    if meta:
        payload["meta"] = meta

    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            ws = connect_gateway_ws()
            if ws is None:
                time.sleep(0.2)
                continue

            # drain any stale ACKs before sending a new decision
            while True:
                try:
                    ack_queue.get_nowait()
                except queue.Empty:
                    break

            ws.send(json.dumps(payload))
            print(f"📡 [NETWORK SENT] Decision '{status_string}' attempt={attempt} meta={meta}")

            try:
                msg = ack_queue.get(timeout=ack_timeout)
            except queue.Empty:
                msg = None

            if msg and msg.get("type") == "DECISION_ACK":
                if msg.get("accepted"):
                    print(f"✅ [DECISION ACK] accepted on attempt={attempt}")
                    return True
                else:
                    print(f"❌ [DECISION ACK] rejected: {msg.get('reason')}")
                    return False

            print(f"⚠️ No ACK received for decision attempt={attempt}, retrying...")
            try:
                ws.close()
            except Exception:
                pass
            ws_client = None
            time.sleep(0.2)
        except Exception as e:
            print(f"⚠️ [NETWORK ERROR] send attempt failed: {e}")
            ws_client = None
            time.sleep(0.2)

    print(f"❌ [NETWORK FAILED] Decision '{status_string}' not ACKed after {max_retries} attempts")
    return False

# =====================================================================
# 🧠 TIER 1: PRESENCE CHECK
# =====================================================================
def edge_presence_check(roi_img):
    global edge_history
    gray_roi = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray_roi, (3, 3), 0)
    edges = cv2.Canny(blurred, 40, 120)
    current_pixels = np.sum(edges > 0)
    edge_history.append(current_pixels)
    return (int(np.mean(edge_history)) > 260), int(np.mean(edge_history))


# =====================================================================
# 🏁 MAIN RUNTIME PIPELINE (เสถียร 100% ภาพลื่นไหลสูงสุด)
# =====================================================================
if __name__ == "__main__":
    camera = OpenMV_Serial_Receiver(port='COM10')
    cv2.namedWindow("Main Camera Screen - OpenMV H7 Plus", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Target ROI (Pocket Area)", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Main Camera Screen - OpenMV H7 Plus", 640, 480)
    cv2.resizeWindow("Target ROI (Pocket Area)", 300, 200)

    ROI_X, ROI_Y, ROI_W, ROI_H = 120, 100, 40, 50 
    print("Interlocked Secure Mode Active. (Single Loop Pipeline)")

    connect_gateway_ws()

    try:
        while True:
            # 📡 คอยแอบเช็คสถานะจากเกตเวย์หลักทุก ๆ 100ms
            now_time = time.time()
            if now_time - last_net_check_time > 0.1:
                sync_fsm_state_live()
                last_net_check_time = now_time

            # detect entering/exiting VISION step so we reset per-part flags
            if fsm_current_state == "VISION":
                if not in_vision:
                    in_vision = True
                    has_sent_for_current_part = False
                    last_stable_decision = "NONE"
                    decision_stable_start_time = 0
            else:
                if in_vision:
                    in_vision = False
                    has_sent_for_current_part = False
                    last_stable_decision = "NONE"

            frame = camera.read_frame()
            if frame is None:
                time.sleep(0.001)
                continue
                
            f_h, f_w = frame.shape[:2]
            x, y = max(0, min(ROI_X, f_w - 10)), max(0, min(ROI_Y, f_h - 10))
            w, h = max(10, min(ROI_W, f_w - x)), max(10, min(ROI_H, f_h - y))

            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
            roi_frame = frame[y:y+h, x:x+w]

            is_present, edge_val = edge_presence_check(roi_frame)
            current_decision, status_reason, color = "NONE", "", (0, 165, 255)
            
            if not is_present:
                current_decision, status_reason, color = "FAIL", "EMPTY_POCKET", (0, 0, 255)
            else:
                if template_img is None:
                    status_reason = "Press 't' to capture valid part"
                else:
                    res = cv2.matchTemplate(roi_frame, template_img, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    if max_val > 0.75:
                        current_decision, status_reason, color = "PASS", f"MATCH: {max_val*100:.1f}%", (0, 255, 0)
                    else:
                        current_decision, status_reason, color = "FAIL", f"WRONG: {max_val*100:.1f}%", (0, 0, 255)
                        
            # ⏳ [ระบบ Handshaking ดักสเตปเครื่องจักร]
            if fsm_current_state == "VISION":
                # When PRESENCE_SENSOR_MODE is enabled, drive DECISION purely from
                # presence detection (is_present). Otherwise require template match.
                if PRESENCE_SENSOR_MODE:
                    current_decision = "PASS" if is_present else "FAIL"
                    status_reason = ("PRESENCE: PART DETECTED" if is_present else "PRESENCE: EMPTY")

                # Can we attempt to send a decision to the gateway? In presence mode
                # we don't require template_img; otherwise require template to be set.
                can_send = PRESENCE_SENSOR_MODE or (current_decision in ["PASS", "FAIL"] and template_img is not None)

                if can_send and fsm_step_allowed:
                    # debounce / stable-check before sending. Use a shorter debounce
                    # when in presence-sensor mode to make testing responsive.
                    debounce = PRESENCE_DEBOUNCE if PRESENCE_SENSOR_MODE else 5.0
                    if current_decision == last_stable_decision:
                        if not has_sent_for_current_part:
                            elapsed_time = time.time() - decision_stable_start_time
                            countdown = max(0, debounce - elapsed_time)

                            if countdown > 0:
                                status_reason += f" | FSM READY! Sending in {countdown:.1f}s"
                            else:
                                status_reason += " | SENDING..."
                                meta = {"reason": status_reason, "confidence": edge_val}
                                accepted = send_decision_to_gateway(current_decision, meta=meta)
                                if accepted:
                                    capture_notification = f"📡 Sent {current_decision} to FSM!"
                                else:
                                    capture_notification = f"⚠️ Decision NOT accepted"
                                notification_timeout = time.time() + 2.0
                                has_sent_for_current_part = True
                    else:
                        last_stable_decision = current_decision
                        decision_stable_start_time = time.time()
                        has_sent_for_current_part = False
            else:
                status_reason += f" | FSM State: {fsm_current_state} (Lock Engaged)"
                has_sent_for_current_part = False
                last_stable_decision = "NONE"

            cv2.putText(frame, f"STATUS: {current_decision}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            cv2.putText(frame, f"INFO: {status_reason}", (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            if time.time() < notification_timeout:
                cv2.putText(frame, capture_notification, (15, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            if time.time() - last_sync_time > 0.5:
                cv2.putText(frame, "NET: waiting for FSM sync...", (15, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            
            cv2.imshow("Main Camera Screen - OpenMV H7 Plus", frame)
            cv2.imshow("Target ROI (Pocket Area)", roi_frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break
            elif key == ord('t') and is_present:
                template_img = roi_frame.copy()
                capture_notification, notification_timeout = "📸 Template Memorized!", time.time() + 2.0
    finally:
        if ws_client is not None:
            try:
                ws_client.close()
            except Exception:
                pass
        cv2.destroyAllWindows()