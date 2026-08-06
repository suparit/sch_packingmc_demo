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

# 🎯 [จุดปรับจูนสเตปปัจจุบัน]: สับเป็น False ถาวร เพื่อปลดล็อกเข้าสู่โหมด Golden Template Matching
# ระบบจะหยุดใช้แค่เซ็นเซอร์เส้นขอบ แล้วเปลี่ยนมาคำนวณ % ความเหมือนของชิ้นงานจริงกับพาร์ทครูทันทีครับ
PRESENCE_SENSOR_MODE = False
PRESENCE_DEBOUNCE = 0.5  # ระยะเวลา (วินาที) ในการตรวจจับพาร์ทให้นิ่งก่อนดีดส่งสัญญานปลดล็อก

# =====================================================================
# 🛠️ TIER 0: AGNOSTIC SERIAL RECEIVER (ดึงภาพจากพอร์ต COM10)
# =====================================================================
class OpenMV_Serial_Receiver:
    def __init__(self, port='COM10'):
        self.ser = serial.Serial(port, baudrate=115200, timeout=0.5)
        self.ser.reset_input_buffer()
        print(f"🔌 [COM LINK] Connected to OpenMV Stream on Port: {port}")
        
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

fsm_current_state = "LOAD_CARRIER"
ws_client = None
ws_send_lock = threading.Lock()
in_vision = False
fsm_step_allowed = False
ack_queue = queue.Queue()
ws_listener_thread = None
ws_listener_running = False
last_sync_time = 0.0
last_net_check_time = 0.0  

last_stable_decision = "NONE"   
decision_stable_start_time = 0 
has_sent_for_current_part = False 

# =====================================================================
# 📡 NETWORKING CORE (จัดการเธรดเครือข่าย ป้องกันจอกล้องล็อกค้าง)
# =====================================================================
def connect_gateway_ws():
    global ws_client
    try:
        if ws_client is None:
            ws_client = websocket.create_connection(WEBSOCKET_URL, timeout=0.5)
            ws_client.settimeout(0.1)
            print("🌐 [NET CONNECT] WebSocket handshaked with Gateway Server.")
            start_ws_listener()
        return ws_client
    except Exception:
        ws_client = None
        return None

def close_gateway_ws():
    global ws_client
    with ws_send_lock:
        if ws_client is not None:
            try: ws_client.close()
            except Exception: pass
            ws_client = None

def safe_ws_send(message):
    with ws_send_lock:
        ws = connect_gateway_ws()
        if ws is None: return False
        try:
            ws.send(message)
            return True
        except Exception:
            close_gateway_ws()
            return False

def sync_fsm_state_live():
    try:
        ws = connect_gateway_ws()
        if ws is None: return
        data = json.dumps({"action": "GET_STATE"})
        safe_ws_send(data)
    except Exception: pass

def ws_listener():
    global ws_client, ws_listener_running, fsm_current_state, fsm_step_allowed, last_sync_time
    ws_listener_running = True
    last_logged_state = "" 
    
    while ws_listener_running:
        try:
            ws = connect_gateway_ws()
            if ws is None:
                time.sleep(0.1)
                continue
            raw = None
            try: raw = ws.recv()
            except Exception:
                time.sleep(0.01)
                continue

            if not raw: continue
            try: msg = json.loads(raw)
            except Exception: continue

            mtype = msg.get("type") or msg.get("action")
            if mtype == "LIVE_SYNC":
                system = msg.get("system", {})
                f_state = system.get("current_state")
                if f_state:
                    fsm_current_state = f_state
                    fsm_step_allowed = bool(system.get('step_allowed', False))
                    last_sync_time = time.time()
                    
                    if fsm_current_state != last_logged_state:
                        icon = "🚨" if fsm_current_state == "ALARM" else "🔄"
                        print(f"{icon} [FSM SYNC] Active State changed to -> {fsm_current_state} (Allowed={fsm_step_allowed})")
                        last_logged_state = fsm_current_state
                        
            elif mtype == "DECISION_ACK":
                try: ack_queue.put_nowait(msg)
                except Exception: pass
        except Exception:
            close_gateway_ws()
            time.sleep(0.2)

def start_ws_listener():
    global ws_listener_thread, ws_listener_running
    if ws_listener_thread and ws_listener_thread.is_alive(): return
    ws_listener_running = True
    ws_listener_thread = threading.Thread(target=ws_listener, daemon=True)
    ws_listener_thread.start()

def send_decision_to_gateway(status_string, meta=None, max_retries=3, ack_timeout=1.0):
    global ws_client
    decision_value = status_string.upper() == "PASS"
    payload = {"action": "DECISION", "value": decision_value}
    if meta: payload["meta"] = meta

    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            ws = connect_gateway_ws()
            if ws is None:
                time.sleep(0.2)
                continue
            while True:
                try: ack_queue.get_nowait()
                except queue.Empty: break

            ws.send(json.dumps(payload))
            try: msg = ack_queue.get(timeout=ack_timeout)
            except queue.Empty: msg = None

            if msg and msg.get("type") == "DECISION_ACK":
                if msg.get("accepted"):
                    print(f"🟩 [DECISION ACCEPTED] Status '{status_string}' transmitted successfully.")
                    return True
                else:
                    print(f"❌ [DECISION REJECTED] Gateway denied: {msg.get('reason')}")
                    return False
            time.sleep(0.2)
        except Exception:
            ws_client = None
            time.sleep(0.2)
    return False

def edge_presence_check(roi_img):
    global edge_history
    gray_roi = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray_roi, (3, 3), 0)
    edges = cv2.Canny(blurred, 40, 120)
    current_pixels = np.sum(edges > 0)
    edge_history.append(current_pixels)
    return (int(np.mean(edge_history)) > 260), int(np.mean(edge_history))

# =====================================================================
# 🏁 MAIN RUNTIME PIPELINE
# =====================================================================
if __name__ == "__main__":
    camera = OpenMV_Serial_Receiver(port='COM10')
    cv2.namedWindow("Main Camera Screen - OpenMV H7 Plus", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Target ROI (Pocket Area)", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Main Camera Screen - OpenMV H7 Plus", 640, 480)
    cv2.resizeWindow("Target ROI (Pocket Area)", 300, 200)

    ROI_X, ROI_Y, ROI_W, ROI_H = 120, 100, 40, 50 
    print("🛡️ [SECURITY CONFIG] Interlocked Secure Mode Active. (Template-Matching Pipeline Running)")

    connect_gateway_ws()

    try:
        while True:
            now_time = time.time()
            if now_time - last_net_check_time > 0.1:
                sync_fsm_state_live()
                last_net_check_time = now_time

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
                # 🛠️ [CORE LOGIC]: ตรรกะเปรียบเทียบหาความเหมือนเชิงพิกเซลด้วยคณิตศาสตร์
                if template_img is None:
                    status_reason = "Press 't' to capture valid part"
                else:
                    res = cv2.matchTemplate(roi_frame, template_img, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    
                    # เกณฑ์ตัดสินใจอ้างอิงหน้างานอุตสาหกรรม (เกณฑ์ความเหมือนดักจับของเสีย 75%)
                    if max_val > 0.75:
                        current_decision, status_reason, color = "PASS", f"MATCH: {max_val*100:.1f}%", (0, 255, 0)
                    else:
                        current_decision, status_reason, color = "FAIL", f"WRONG/FLIPPED: {max_val*100:.1f}%", (0, 0, 255)
                        
            if fsm_current_state == "VISION":
                # บังคับตัดสินตามผลลัพธ์คณิตศาสตร์ภาพ % Match (เนื่องจาก PRESENCE_SENSOR_MODE = False)
                if PRESENCE_SENSOR_MODE:
                    current_decision = "PASS" if is_present else "FAIL"
                    status_reason = ("PRESENCE: PART DETECTED" if is_present else "PRESENCE: EMPTY")

                can_send = PRESENCE_SENSOR_MODE or (current_decision in ["PASS", "FAIL"] and template_img is not None)

                if can_send and fsm_step_allowed:
                    debounce = PRESENCE_DEBOUNCE if PRESENCE_SENSOR_MODE else 1.0 # หน่วงเวลาสแกนพาร์ทครูให้นิ่งก่อน 1 วินาทีเพื่อความเสถียร
                    if current_decision == last_stable_decision:
                        if not has_sent_for_current_part:
                            elapsed_time = time.time() - decision_stable_start_time
                            countdown = max(0, debounce - elapsed_time)

                            if countdown > 0:
                                status_reason += f" | FSM READY! Sending in {countdown:.1f}s"
                            else:
                                status_reason += " | SENDING..."
                                meta = {"reason": status_reason, "confidence": edge_val if PRESENCE_SENSOR_MODE else float(max_val)}
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
            
            cv2.imshow("Main Camera Screen - OpenMV H7 Plus", frame)
            cv2.imshow("Target ROI (Pocket Area)", roi_frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break
            elif key == ord('t') and is_present:
                template_img = roi_frame.copy()
                capture_notification, notification_timeout = "📸 Template Memorized!", time.time() + 2.0
    finally:
        if ws_client is not None:
            try: ws_client.close()
            except Exception: pass
        cv2.destroyAllWindows()