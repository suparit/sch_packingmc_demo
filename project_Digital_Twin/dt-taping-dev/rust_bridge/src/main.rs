// ==================================================================
// Rust I/O Layer — สะพานระหว่าง Python Gateway (TCP 8767) กับบอร์ด STM32 (Modbus TCP 502)
// ==================================================================
//
// บทบาทของไฟล์นี้
//   - เป็น "server" ที่ 127.0.0.1:8767 รอ gateway_fsm_upgrad.py (RUST_BRIDGE=1) ต่อเข้ามา
//   - เป็น "client" ต่อออกไปหาบอร์ดจริงที่ 192.168.0.100:502 (Modbus TCP)
//   - (2026-09-24) เป็น **ผู้สร้างพัลส์มอเตอร์ feed คนเดียว** ตามคำสั่ง `feed_cmd` จาก gateway
//   สัญญาสาย 8767: docs/specs/protocol.md ข้อ 9 · สัญญาสาย 502: docs/specs/board_protocol.md
//   ตารางพอร์ต: docs/specs/port_map.md · ส่วนตรรกะล้วน (เฟรม/parse/idempotent/framing) อยู่ที่ logic.rs
//
// โครงสร้าง (รอบ 2026-09-24 — protocol.md 9.7)
// -------------------------------------------
//   [handler สาย Python] ×N  --อัปเดต "สถานะที่ต้องการ" (op0, op1, คำสั่ง feed)-->  [Shared]
//                            <--ตอบทันทีจาก cache (ip0, board, feed)-------------  [Shared]
//   [board_owner] task เดียว เป็นเจ้าของสาย 502 คนเดียว: อ่าน Shared แล้วเขียน/อ่านบอร์ด
//                 ตอนไม่มี feed : ต่อ 1 บรรทัดของ Python → op0 → op1 → อ่าน ip0 (เหมือนเดิม)
//                 ตอน feed      : ขอบขึ้น/ขอบลงบน addr 72 + แทรก op0/ip0 ตามเวลา ทุก ≤ 20 ms
//                 ไม่มี Python  : heartbeat อ่านอย่างเดียวทุก 100 ms (เดิม 3 วิ → บอร์ดตัดสายวนทุก 3 วิ)
//   handler **ไม่เคย await บอร์ด** → ESTOP/abort จาก Python ไม่ติดคิวหลัง feed
//
// หลักความปลอดภัย
//   - op1 ที่ลง addr 72 คำนวณที่เดียว: compose_op1() = (op1_Python & 0xEF) | PUL · bit 4 จาก Python ทิ้งเสมอ
//   - abort: เช็คก่อนขอบขึ้นทุกครั้ง · ขอบขึ้นออกไปแล้วต้องส่งขอบลงให้จบ → หยุดภายใน ≤ 1 พัลส์ PUL ค้างต่ำ
//   - สาย Python หลุดระหว่าง feed → abort ทันที
//   - สายบอร์ดพังกลาง feed → error + ทิ้งสาย (ห้าม resync) · พอต่อใหม่ได้ เขียน op1 (bit4 = 0) ก่อนอย่างอื่น
//   - ทุกเฟรม TID 00 00 · อ่าน ack ครบ 12 ไบต์ (read_exact) + ตรวจ fc ที่ไบต์ index 7 · มี timeout ทุกเฟรม
//
// ประวัติ 2026-08-04 (ยังคงอยู่)
//   - ต่อบอร์ดใหม่ทุก 3 วินาทีเมื่อหลุด (ห้ามถี่กว่านี้ — บทเรียน reconnect ทุก 20 ms)
//   - ทุกบรรทัด log ที่มีค่า I/O ขึ้นต้น [REAL] (มาจากบอร์ด) / [SIM] (สะท้อนค่าที่ Python ส่งมา)
//   - ทุกการอ่าน/เขียนบอร์ดมี timeout
//
// ตัวแปรสภาพแวดล้อม
//   BOARD_ADDR / STM32_ADDR — พิกัดบอร์ด (default 192.168.0.100:502) · BOARD_ADDR ชนะถ้าตั้งทั้งคู่
//                             ใช้ชี้ไป mock server (127.0.0.1) ตอนทดสอบ
//   BRIDGE_ADDR             — พิกัดที่เปิดรอ Python (default 127.0.0.1:8767)
//   RUST_READ_ONLY=1        — ไม่ส่งคำสั่งเขียน coil (0x0F) เลย · feed_cmd ตอบ error `read_only`

mod logic;

use logic::{
    compose_op1, decide_feed, err, modbus_write_bank, response_line, FeedDecision, FeedReport,
    FeedState, LineBuffer, FC_READ_COILS, FC_WRITE_COILS, MODBUS_READ_IP, OP0_COIL_ADDR,
    OP1_COIL_ADDR, PUL_BIT, READ_DATA_INDEX, READ_REPLY_LEN, REPLY_FC_INDEX, WRITE_ACK_LEN,
};
use serde::Deserialize;
use std::collections::HashMap;
use std::env;
use std::io::{self, ErrorKind};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, MutexGuard, OnceLock};
use std::time::{Duration, Instant};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::Notify;
use tokio::time::{sleep_until, timeout};

/// บรรทัดจาก Python (protocol.md 9.2) — ไม่ได้ `deny_unknown_fields` ตั้งใจให้ข้ามคีย์เกินได้ (9.8)
#[derive(Deserialize, Debug, Clone)]
struct PythonSystemData {
    current_state: String,
    #[allow(dead_code)]
    running: bool,
    op0: u8,
    // แผ่นเอาต์พุตที่ 2 (coil addr 72) — serde(default) กัน gateway รุ่นเก่าที่ไม่มีคีย์นี้ → 0
    #[serde(default)]
    op1: u8,
    ip0: u8,
    cycles: u32,
    /// คำสั่ง feed — เก็บเป็น Value ดิบ แล้วตรวจเองใน logic::decide_feed
    /// (ถ้าให้ serde ตรวจชนิด `half_ms: "5"` จะทำทั้งบรรทัด parse ไม่ผ่าน แทนที่จะตอบ `bad_half_ms`)
    #[serde(default)]
    feed_cmd: Option<serde_json::Value>,
}

// พิกัด IP บอร์ดของนิวตามที่ตั้งไว้ในโค้ดตัวอย่างไฟกระพริบ
const STM32_IP_ADDR: &str = "192.168.0.100:502";
// 8766 ถูกจองไว้ให้จอ TouchGFX ต่อเข้า Python Gateway แล้ว (ดู python_backend/hmi_link.py)
// สะพานตัวนี้จึงอยู่ที่ 8767 — ตรงกับค่า RUST_PORT ใน gateway_fsm_upgrad.py
const PYTHON_BRIDGE_ADDR: &str = "127.0.0.1:8767";

/// จังหวะลองต่อบอร์ดใหม่ — ห้ามลดต่ำกว่านี้ (บทเรียน reconnect ทุก 20 ms + บอร์ดต่อรัว ๆ ไม่ติด ~4 วิ)
const BOARD_RETRY_SEC: u64 = 3;
const BOARD_CONNECT_TIMEOUT: Duration = Duration::from_secs(2);
/// timeout ต่อ 1 เฟรม+คำตอบ (protocol.md 9.4 `ack_timeout`)
const BOARD_IO_TIMEOUT: Duration = Duration::from_millis(500);
/// heartbeat ตอนไม่มีทราฟฟิก — บอร์ดตัดสายเมื่อเงียบ ~200 ms (board_protocol.md 7, 11 ข้อ 2 ให้ ≤ 150 ms)
const HEARTBEAT_GAP: Duration = Duration::from_millis(100);
/// ระหว่าง feed แทรกเขียน op0 + อ่าน ip0 ทุกเท่านี้ (สเปก ≤ 30 ms — เผื่อเวลาเฟรมพัลส์ที่ค้างอยู่ ~4 ms)
const FEED_INTERLEAVE: Duration = Duration::from_millis(20);
/// ช่วงท้ายของการรอที่วน yield แทน sleep (ดู wait_until) — กิน CPU ≤ ~1.5 ms ต่อขอบ เฉพาะตอน feed
const SPIN_MARGIN: Duration = Duration::from_micros(1500);
/// ความยาวบรรทัดสูงสุดจาก Python (สเปก ≤ 1 KB — เผื่อ 16 เท่า เกินนี้ทิ้งแล้ว resync ที่ `\n` ถัดไป)
const MAX_PY_LINE: usize = 16 * 1024;
/// เว้นช่วง log ค่า I/O อย่างน้อยเท่านี้ (Python ยิงเข้ามาทุก 20 ms = 50 ครั้ง/วิ)
const IO_LOG_MIN_INTERVAL: Duration = Duration::from_secs(5);
/// ต่อบอร์ดไม่ติดติด ๆ กัน ให้เตือนซ้ำทุก ๆ กี่รอบ (10 x 3 วิ = 30 วิ)
const RETRY_LOG_EVERY: u64 = 10;

/// true = ตอนนี้สายไปบอร์ดจริงใช้งานได้ → ตัวเลขที่ส่งกลับ Python เป็นของจริง (= คีย์ `board`)
static BOARD_LINK_UP: AtomicBool = AtomicBool::new(false);

/// เวลาที่โปรเซสเริ่ม — ใช้พิมพ์ t=..s บนบรรทัดเหตุการณ์ของสาย
static START_TIME: OnceLock<Instant> = OnceLock::new();

fn uptime() -> String {
    let t0 = START_TIME.get_or_init(Instant::now);
    format!("t={:.3}s", t0.elapsed().as_secs_f64())
}

/// ป้ายบอกที่มาของตัวเลขในบรรทัด log — กว้างเท่ากันทั้งสองแบบเพื่อให้อ่านเป็นคอลัมน์
fn tag() -> &'static str {
    if BOARD_LINK_UP.load(Ordering::Relaxed) {
        "[REAL]"
    } else {
        "[SIM] "
    }
}

// ==================================================================
// สถานะร่วมระหว่าง handler ของ Python กับ task เจ้าของสายบอร์ด
// ==================================================================

/// งาน feed หนึ่งครั้งที่ handler ส่งให้ board_owner
struct FeedJob {
    conn: u64,
    id: u32,
    total: u32,
    half_ms: f64,
    /// handler ตั้ง true เมื่อได้ abort / สาย Python หลุด — board_owner เช็คก่อนขอบขึ้นทุกครั้ง
    abort: Arc<AtomicBool>,
}

#[derive(Default)]
struct Shared {
    /// ค่าล่าสุดที่ Python ต้องการ (บรรทัดล่าสุดจากสายไหนก็ได้ — เหมือนของเดิม)
    op0: u8,
    /// op1 ของ Python ที่ mask bit 4 ทิ้งแล้ว
    op1_base: u8,
    /// จำนวนสาย Python ที่ต่ออยู่ — 0 = ไม่เขียนเอาต์พุต ทำแค่ heartbeat
    clients: u32,
    /// งาน feed ที่รอ board_owner หยิบ
    pending: Option<FeedJob>,
    /// สายไหนเป็นเจ้าของ feed ที่กำลังส่งพัลส์อยู่ (board_owner ตั้ง/ล้าง)
    active_conn: Option<u64>,
    /// รายงาน feed ต่อสาย Python (protocol.md 9.3 "สถานะต่อ 1 สาย")
    reports: HashMap<u64, FeedReport>,
    /// ip0 ล่าสุดที่อ่านจากบอร์ดจริง
    ip0: u8,
}

struct Bridge {
    st: Mutex<Shared>,
    /// ปลุก board_owner: มีบรรทัดใหม่จาก Python / มีงาน feed / abort / สายปิด
    wake: Notify,
    read_only: bool,
}

impl Bridge {
    fn lock(&self) -> MutexGuard<'_, Shared> {
        // critical section สั้นมากและไม่มี await ข้างใน — ถ้า poison ก็ใช้ข้อมูลต่อได้
        self.st.lock().unwrap_or_else(|e| e.into_inner())
    }

    /// อัปเดตรายงานของ feed (conn, id) — ถ้าสายปิดไปแล้วหรือ id ไม่ตรง (เก่า) จะไม่ทำอะไร
    fn update_report(&self, conn: u64, id: u32, f: impl FnOnce(&mut FeedReport)) {
        let mut s = self.lock();
        if let Some(r) = s.reports.get_mut(&conn) {
            if r.id == id {
                f(r);
            }
        }
    }
}

// ==================================================================
// main
// ==================================================================

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    START_TIME.get_or_init(Instant::now);
    raise_windows_timer_resolution();

    let board_addr = env::var("BOARD_ADDR")
        .or_else(|_| env::var("STM32_ADDR"))
        .unwrap_or_else(|_| STM32_IP_ADDR.to_string());
    let bridge_addr = env::var("BRIDGE_ADDR").unwrap_or_else(|_| PYTHON_BRIDGE_ADDR.to_string());
    let read_only = env::var("RUST_READ_ONLY").unwrap_or_default() == "1";

    println!("=========================================================");
    println!(" [Rust I/O Layer] SCH-IO Socket Bridge  (feed pulse generator: protocol.md 9)");
    println!("   Python FSM  : tcp://{bridge_addr}  (server, waiting for gateway_fsm_upgrad.py)");
    println!("   STM32 board : tcp://{board_addr}  (client, Modbus TCP)");
    println!("   reconnect   : every {BOARD_RETRY_SEC} s while the board is unreachable");
    println!(
        "   heartbeat   : read-only 0x01 every {} ms when no Python traffic",
        HEARTBEAT_GAP.as_millis()
    );
    if read_only {
        println!("   RUST_READ_ONLY=1 : coil write (0x0F) DISABLED - read-only frames only, feed_cmd -> error read_only");
    }
    println!("=========================================================");
    println!(
        "[SIM]  starting in SIMULATED mode - board not connected yet. \
         Every value returned to Python is an echo of what Python sent."
    );

    // เปิดพอร์ตรอ Python "ก่อน" ไปยุ่งกับบอร์ด — ถ้าบอร์ดไม่ตอบ TCP จะไม่ทำให้ 8767 ขึ้นช้า
    let listener = TcpListener::bind(&bridge_addr).await?;
    println!("[BRIDGE] listening for Python FSM core on tcp://{bridge_addr}");

    let bridge = Arc::new(Bridge {
        st: Mutex::new(Shared::default()),
        wake: Notify::new(),
        read_only,
    });

    // task เดียวที่เป็นเจ้าของสายบอร์ด (protocol.md 9.7 "ผู้เขียนบอร์ดคนเดียว")
    let b = Arc::clone(&bridge);
    tokio::spawn(async move { board_owner(b, board_addr).await });

    static NEXT_CONN: AtomicU64 = AtomicU64::new(1);
    loop {
        let (socket, addr) = listener.accept().await?;
        let conn = NEXT_CONN.fetch_add(1, Ordering::Relaxed);
        println!("{} [BRIDGE] Python gateway connected from {addr} (conn #{conn}) at {}", tag(), uptime());
        let b = Arc::clone(&bridge);
        tokio::spawn(async move {
            match handle_python_connection(socket, &b, conn).await {
                Ok(()) => println!("{} [BRIDGE] python connection #{conn} closed at {}", tag(), uptime()),
                Err(e) => println!("{} [BRIDGE] python connection #{conn} closed: {e} at {}", tag(), uptime()),
            }
        });
    }
}

/// Windows ตั้งความละเอียด timer ไว้ ~15.6 ms โดยปริยาย → sleep 5 ms จะกลายเป็น ~15 ms
/// ทำให้ `half_ms` เพี้ยนและแทรก op0 ไม่ทันรอบ 30 ms · ขอ 1 ms ตลอดอายุโปรเซส (คืนเองเมื่อโปรเซสจบ)
#[cfg(windows)]
fn raise_windows_timer_resolution() {
    #[link(name = "winmm")]
    extern "system" {
        fn timeBeginPeriod(u_period: u32) -> u32;
    }
    // SAFETY: เรียก API ของระบบด้วยค่าคงที่ ไม่มี pointer
    let rc = unsafe { timeBeginPeriod(1) };
    if rc != 0 {
        println!("[BRIDGE] warning: timeBeginPeriod(1) failed (rc={rc}) - half_ms timing may be coarse");
    }

    // Windows 11: โปรเซสที่ไม่มีหน้าต่างที่ผู้ใช้เห็น (เช่นรันแบบ stdout ถูก redirect) โดน power throttling
    // → ระบบ "เพิกเฉย" คำขอ timeBeginPeriod ได้ และลด QoS (EcoQoS) — วัดจริงกับ mock: half_ms 5 ตกจาก ~97 เหลือ ~46
    // พัลส์/วิ และช่วงห่าง op0 เกิน 30 ms · ขอปิด throttling 2 ข้อนี้สำหรับโปรเซสนี้ (ไม่มีผลบน Windows 10 รุ่นเก่า)
    #[repr(C)]
    struct ProcessPowerThrottlingState {
        version: u32,
        control_mask: u32,
        state_mask: u32,
    }
    #[link(name = "kernel32")]
    extern "system" {
        fn GetCurrentProcess() -> *mut std::ffi::c_void;
        fn SetProcessInformation(
            process: *mut std::ffi::c_void,
            class: i32,
            info: *mut std::ffi::c_void,
            size: u32,
        ) -> i32;
    }
    const PROCESS_POWER_THROTTLING: i32 = 4; // PROCESS_INFORMATION_CLASS::ProcessPowerThrottling
    const THROTTLING_EXECUTION_SPEED: u32 = 0x1;
    const THROTTLING_IGNORE_TIMER_RESOLUTION: u32 = 0x4;
    let mut st = ProcessPowerThrottlingState {
        version: 1,
        control_mask: THROTTLING_EXECUTION_SPEED | THROTTLING_IGNORE_TIMER_RESOLUTION,
        state_mask: 0, // 0 = ปิด throttling ทั้งสองข้อ (เคารพ timer resolution เสมอ)
    };
    // SAFETY: ส่ง pointer ไปยัง struct บน stack ที่มีชีวิตตลอดการเรียก พร้อมขนาดที่ถูกต้อง
    let ok = unsafe {
        SetProcessInformation(
            GetCurrentProcess(),
            PROCESS_POWER_THROTTLING,
            &mut st as *mut _ as *mut std::ffi::c_void,
            std::mem::size_of::<ProcessPowerThrottlingState>() as u32,
        )
    };
    if ok == 0 {
        println!("[BRIDGE] note: SetProcessInformation(power throttling off) not supported on this Windows - timer may be coarse when the window is hidden");
    }
}

#[cfg(not(windows))]
fn raise_windows_timer_resolution() {}

// ==================================================================
// สายฝั่ง Python (8767) — ห้าม await บอร์ดในนี้เด็ดขาด
// ==================================================================

/// สถานะต่อสาย Python (protocol.md 9.3)
struct ConnState {
    conn: u64,
    last_id: Option<u32>,
    /// ธง abort ของ feed ที่สายนี้สั่งไว้ล่าสุด
    abort_flag: Option<Arc<AtomicBool>>,
    last_py_ip0: u8,
    // --- log ---
    last_log: Instant,
    last_logged: Option<(u8, bool, u8, u8)>,
    last_warn: HashMap<&'static str, Instant>,
}

impl ConnState {
    /// เตือนแบบจำกัดความถี่ (ครั้งแรก + ทุก 5 วิ ต่อหัวข้อ) — Python ส่งซ้ำทุก 20 ms
    fn warn(&mut self, key: &'static str, msg: impl FnOnce() -> String) {
        let due = self
            .last_warn
            .get(key)
            .map_or(true, |t| t.elapsed() >= IO_LOG_MIN_INTERVAL);
        if due {
            println!("{} [BRIDGE] WARN conn #{}: {}", tag(), self.conn, msg());
            self.last_warn.insert(key, Instant::now());
        }
    }
}

async fn handle_python_connection(stream: TcpStream, br: &Arc<Bridge>, conn: u64) -> io::Result<()> {
    let _ = stream.set_nodelay(true);
    {
        let mut s = br.lock();
        s.clients += 1;
        s.reports.insert(conn, FeedReport::idle());
    }
    let mut cs = ConnState {
        conn,
        last_id: None,
        abort_flag: None,
        last_py_ip0: 0,
        last_log: Instant::now() - IO_LOG_MIN_INTERVAL,
        last_logged: None,
        last_warn: HashMap::new(),
    };

    let result = python_io_loop(stream, br, &mut cs).await;

    // --- สายปิด (ปกติหรือ error) : abort feed ของสายนี้ทันที + ลืม id (protocol.md 9.3 ข้อ 3) ---
    let was_running = {
        let mut s = br.lock();
        s.clients = s.clients.saturating_sub(1);
        let running = s
            .reports
            .remove(&conn)
            .map_or(false, |r| r.state == FeedState::Running);
        running
    };
    if let Some(flag) = cs.abort_flag.take() {
        if was_running && !flag.swap(true, Ordering::SeqCst) {
            println!(
                "{} FEED id={} ABORT requested: python link #{conn} lost during feed at {}",
                tag(),
                cs.last_id.unwrap_or(0),
                uptime()
            );
        }
        flag.store(true, Ordering::SeqCst);
    }
    br.wake.notify_one();
    result
}

async fn python_io_loop(mut stream: TcpStream, br: &Arc<Bridge>, cs: &mut ConnState) -> io::Result<()> {
    let mut lines = LineBuffer::new(MAX_PY_LINE);
    let mut chunk = [0u8; 4096];
    let mut out = String::with_capacity(512);
    let mut dropped_seen = 0u64;

    loop {
        let n = stream.read(&mut chunk).await?;
        if n == 0 {
            return Ok(());
        }
        out.clear();
        // ประมวลทุกบรรทัดตามลำดับ (ห้ามทิ้งบรรทัดที่มี abort) — ตอบ 1 บรรทัดต่อ 1 บรรทัด
        for line in lines.push(&chunk[..n]) {
            if let Some(resp) = process_line(&line, br, cs) {
                out.push_str(&resp);
            }
        }
        if lines.dropped != dropped_seen {
            dropped_seen = lines.dropped;
            cs.warn("overlong", || format!("dropped a line longer than {MAX_PY_LINE} bytes"));
        }
        if !out.is_empty() {
            stream.write_all(out.as_bytes()).await?;
        }
    }
}

/// ประมวล 1 บรรทัดจาก Python แล้วคืนบรรทัดคำตอบ (ไม่มี await — ตอบจาก cache ทันที)
fn process_line(line: &[u8], br: &Arc<Bridge>, cs: &mut ConnState) -> Option<String> {
    let text = String::from_utf8_lossy(line);
    let text = text.trim();
    if text.is_empty() {
        return None;
    }

    let sys = match serde_json::from_str::<PythonSystemData>(text) {
        Ok(v) => Some(v),
        Err(e) => {
            let preview: String = text.chars().take(80).collect();
            cs.warn("bad_json", || format!("unparseable line ({e}): {preview}"));
            None
        }
    };

    if let Some(sys) = &sys {
        cs.last_py_ip0 = sys.ip0;
        if sys.op1 & PUL_BIT != 0 {
            cs.warn("op1_bit4", || {
                format!(
                    "Python sent op1=0x{:02X} with bit 4 (PUL) set - masked off, PUL belongs to rust_bridge (protocol.md 9.6)",
                    sys.op1
                )
            });
        }
        {
            let mut s = br.lock();
            s.op0 = sys.op0;
            s.op1_base = compose_op1(sys.op1, false);
        }
        if let Some(cmd) = sys.feed_cmd.as_ref().filter(|v| !v.is_null()) {
            handle_feed_cmd(cmd, br, cs);
        }
        br.wake.notify_one();
    }

    // --- คำตอบจาก cache ---
    let board = BOARD_LINK_UP.load(Ordering::Relaxed);
    let (ip0_board, report) = {
        let s = br.lock();
        (s.ip0, s.reports.get(&cs.conn).cloned().unwrap_or_else(FeedReport::idle))
    };
    let ip0 = if board { ip0_board } else { cs.last_py_ip0 };

    if let Some(sys) = &sys {
        log_io(cs, sys, ip0, board, br.read_only);
    }
    Some(response_line(ip0, board, &report))
}

fn handle_feed_cmd(cmd: &serde_json::Value, br: &Arc<Bridge>, cs: &mut ConnState) {
    let current = br
        .lock()
        .reports
        .get(&cs.conn)
        .cloned()
        .unwrap_or_else(FeedReport::idle);
    let board_up = BOARD_LINK_UP.load(Ordering::Relaxed);

    match decide_feed(cmd, cs.last_id, &current, br.read_only, board_up) {
        FeedDecision::Duplicate => {}
        FeedDecision::Malformed(why) => {
            let preview: String = cmd.to_string().chars().take(80).collect();
            cs.warn("feed_malformed", || format!("ignored feed_cmd ({why}): {preview}"));
        }
        FeedDecision::AbortRunning => {
            if let Some(flag) = &cs.abort_flag {
                if !flag.swap(true, Ordering::SeqCst) {
                    println!(
                        "{} FEED id={} ABORT requested by Python (sent {}/{}) at {}",
                        tag(),
                        current.id,
                        current.sent,
                        current.total,
                        uptime()
                    );
                    br.wake.notify_one();
                }
            }
        }
        FeedDecision::RejectBusy { id } => {
            cs.warn("feed_busy", || {
                format!(
                    "feed_cmd id={id} NOT accepted: id={} is still running (Python must wait for a final state)",
                    current.id
                )
            });
        }
        FeedDecision::Finish(rep) => {
            println!(
                "{} FEED id={} {} pulses={} err='{}' (not started) at {}",
                tag(),
                rep.id,
                rep.state.as_str().to_uppercase(),
                rep.total,
                rep.err,
                uptime()
            );
            cs.last_id = Some(rep.id);
            cs.abort_flag = None;
            if let Some(r) = br.lock().reports.get_mut(&cs.conn) {
                *r = rep;
            }
        }
        FeedDecision::Start { id, pulses, half_ms } => {
            let flag = Arc::new(AtomicBool::new(false));
            let accepted = {
                let mut s = br.lock();
                // มี feed ของสายอื่นค้างอยู่ (ไม่ควรเกิด — ระบบมี gateway ตัวเดียว) → ไม่รับเหมือน RejectBusy
                let busy_other = s.pending.is_some() || s.active_conn.map_or(false, |c| c != cs.conn);
                if busy_other {
                    false
                } else {
                    s.pending = Some(FeedJob {
                        conn: cs.conn,
                        id,
                        total: pulses,
                        half_ms,
                        abort: Arc::clone(&flag),
                    });
                    if let Some(r) = s.reports.get_mut(&cs.conn) {
                        *r = FeedReport::running(id, pulses);
                    }
                    true
                }
            };
            if accepted {
                cs.last_id = Some(id);
                cs.abort_flag = Some(flag);
                br.wake.notify_one();
            } else {
                cs.warn("feed_busy_other", || {
                    format!("feed_cmd id={id} NOT accepted: another Python connection owns the feed motor right now")
                });
            }
        }
    }
}

/// log ค่า I/O — พิมพ์เมื่อค่าเปลี่ยน / ที่มาเปลี่ยน / ครบรอบเวลา
fn log_io(cs: &mut ConnState, sys: &PythonSystemData, ip0: u8, board: bool, read_only: bool) {
    let key = (ip0, board, sys.op0, sys.op1);
    if cs.last_logged == Some(key) && cs.last_log.elapsed() < IO_LOG_MIN_INTERVAL {
        return;
    }
    if board {
        println!(
            "[REAL] ip0=0x{ip0:02X} <- STM32 sensor | op0=0x{:02X} op1=0x{:02X} -> board{} | state={} cycles={}",
            sys.op0,
            compose_op1(sys.op1, false),
            if read_only { " (SKIPPED: read-only)" } else { "" },
            sys.current_state,
            sys.cycles
        );
    } else {
        println!(
            "[SIM]  ip0=0x{ip0:02X} <- echo of Python's own value (NO board link) | op0=0x{:02X} op1=0x{:02X} not written | state={} cycles={}",
            sys.op0, sys.op1, sys.current_state, sys.cycles
        );
    }
    cs.last_log = Instant::now();
    cs.last_logged = Some(key);
}

// ==================================================================
// เจ้าของสายบอร์ด — task เดียวตลอดอายุโปรเซส
// ==================================================================

/// ความผิดพลาดของสายบอร์ด → รหัส `feed.err` (protocol.md 9.4)
#[derive(Debug)]
enum BoardErr {
    Timeout,
    BadFc(u8),
    Closed,
    Io(io::Error),
}

impl BoardErr {
    fn code(&self) -> &'static str {
        match self {
            BoardErr::Timeout => err::ACK_TIMEOUT,
            BoardErr::BadFc(_) => err::ACK_BAD_FC,
            BoardErr::Closed => err::BOARD_DOWN,
            BoardErr::Io(e) => match e.kind() {
                ErrorKind::ConnectionReset
                | ErrorKind::ConnectionAborted
                | ErrorKind::BrokenPipe
                | ErrorKind::UnexpectedEof => err::BOARD_DOWN,
                _ => err::IO_ERROR,
            },
        }
    }
}

impl std::fmt::Display for BoardErr {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BoardErr::Timeout => write!(f, "reply timed out"),
            BoardErr::BadFc(fc) => write!(f, "reply fc=0x{fc:02X} (text parser output in the Modbus stream?)"),
            BoardErr::Closed => write!(f, "board closed the socket"),
            BoardErr::Io(e) => write!(f, "{e}"),
        }
    }
}

/// ส่ง 1 เฟรมแล้วอ่านคำตอบ **ครบ N ไบต์** (read_exact) + ตรวจ fc ที่ index 7 · ทั้งหมดอยู่ใต้ timeout เดียว
/// เฟรมกับคำตอบเป็นหน่วยเดียว — ไม่มีใครแทรกได้เพราะ board_owner เป็นเจ้าของสายคนเดียว
async fn transact<const N: usize>(
    stream: &mut TcpStream,
    frame: &[u8],
    expect_fc: u8,
) -> Result<[u8; N], BoardErr> {
    let io = async {
        stream.write_all(frame).await?;
        let mut buf = [0u8; N];
        stream.read_exact(&mut buf).await?;
        Ok::<_, io::Error>(buf)
    };
    match timeout(BOARD_IO_TIMEOUT, io).await {
        Err(_) => Err(BoardErr::Timeout),
        Ok(Err(e)) if e.kind() == ErrorKind::UnexpectedEof => Err(BoardErr::Closed),
        Ok(Err(e)) => Err(BoardErr::Io(e)),
        Ok(Ok(buf)) if buf[REPLY_FC_INDEX] != expect_fc => Err(BoardErr::BadFc(buf[REPLY_FC_INDEX])),
        Ok(Ok(buf)) => Ok(buf),
    }
}

async fn write_bank(stream: &mut TcpStream, addr: u16, value: u8) -> Result<(), BoardErr> {
    transact::<WRITE_ACK_LEN>(stream, &modbus_write_bank(addr, value), FC_WRITE_COILS)
        .await
        .map(|_| ())
}

async fn read_ip0(stream: &mut TcpStream) -> Result<u8, BoardErr> {
    transact::<READ_REPLY_LEN>(stream, &MODBUS_READ_IP, FC_READ_COILS)
        .await
        .map(|b| b[READ_DATA_INDEX])
}

fn mark_link_down(reason: &str) {
    if BOARD_LINK_UP.swap(false, Ordering::Relaxed) {
        println!(
            "[SIM]  BOARD LINK LOST ({}) at {} -> falling back to loopback. \
             ip0 sent back to Python is now a SIMULATED echo, not a sensor reading. \
             Retrying every {}s.",
            reason,
            uptime(),
            BOARD_RETRY_SEC
        );
    }
}

fn log_connect_failure(addr: &str, fail_streak: u64, reason: &str) {
    // ครั้งแรกบอกให้ครบ หลังจากนั้นเตือนซ้ำทุก 30 วิ ไม่งั้น log ท่วมตอนไม่ได้เสียบบอร์ด
    if fail_streak == 1 {
        println!(
            "[SIM]  board {addr} unreachable ({reason}) at {} - staying in SIMULATED mode, \
             retrying every {BOARD_RETRY_SEC}s",
            uptime()
        );
    } else if fail_streak % RETRY_LOG_EVERY == 0 {
        println!(
            "[SIM]  board {addr} still unreachable after {fail_streak} tries ({reason}) at {} - \
             every value going back to Python is SIMULATED",
            uptime()
        );
    }
}

/// งาน feed ที่รออยู่แต่ส่งไม่ได้ (ไม่มีสายบอร์ด / read-only) → จบเป็น error ทันที
fn fail_pending(br: &Bridge, code: &'static str) {
    let job = br.lock().pending.take();
    if let Some(job) = job {
        println!("{} FEED id={} ERROR err='{code}' (not started) at {}", tag(), job.id, uptime());
        br.update_report(job.conn, job.id, |r| *r = FeedReport::error(job.id, job.total, 0, code));
    }
}

async fn board_owner(br: Arc<Bridge>, board_addr: String) {
    let mut stream: Option<TcpStream> = None;
    let mut next_connect = Instant::now();
    let mut fail_streak: u64 = 0;
    // สายพังระหว่างที่ PUL อาจค้างสูง → ต่อใหม่ได้แล้วต้องเขียน op1 (bit4 = 0) ก่อนอย่างอื่น
    let mut pul_maybe_high = false;
    let mut last_io = Instant::now();
    // เวลาที่เขียน op0 ครั้งล่าสุด — ส่งต่อเข้า/ออก run_feed เพื่อให้ช่วงห่างของ op0 ต่อเนื่องข้ามรอยต่อ
    // รอบปกติ ↔ feed (เดิมเริ่มนับใหม่ตอนเริ่ม feed → ช่องว่างตรงรอยต่อ ~45 ms เกินสเปก 30 ms)
    let mut last_op0 = Instant::now();

    loop {
        // ---------------- ไม่มีสาย: ต่อใหม่ทุก 3 วิ ----------------
        let Some(s) = stream.as_mut() else {
            fail_pending(&br, err::BOARD_DOWN);
            if Instant::now() < next_connect {
                // รอถึงเวลาต่อใหม่ แต่ตื่นได้เมื่อมีงาน feed เข้ามา เพื่อตอบ board_down ทันที
                tokio::select! {
                    _ = sleep_until(next_connect.into()) => {}
                    _ = br.wake.notified() => {}
                }
                continue;
            }
            match timeout(BOARD_CONNECT_TIMEOUT, TcpStream::connect(&board_addr)).await {
                Ok(Ok(mut s)) => {
                    let _ = s.set_nodelay(true);
                    fail_streak = 0;
                    // ปลดค้างของ PUL ก่อนประกาศว่าสายใช้ได้
                    if pul_maybe_high && !br.read_only {
                        let base = br.lock().op1_base;
                        match write_bank(&mut s, OP1_COIL_ADDR, compose_op1(base, false)).await {
                            Ok(()) => {
                                println!(
                                    "[REAL] PUL forced LOW after reconnect (op1=0x{:02X} -> addr {OP1_COIL_ADDR}) at {}",
                                    compose_op1(base, false),
                                    uptime()
                                );
                                pul_maybe_high = false;
                            }
                            Err(e) => {
                                println!("[SIM]  reconnect: could not force PUL low ({e}) - retrying in {BOARD_RETRY_SEC}s");
                                next_connect = Instant::now() + Duration::from_secs(BOARD_RETRY_SEC);
                                continue;
                            }
                        }
                    }
                    stream = Some(s);
                    last_io = Instant::now();
                    BOARD_LINK_UP.store(true, Ordering::Relaxed);
                    println!(
                        "[REAL] BOARD LINK UP at {} - connected to STM32 at {board_addr}. \
                         ip0 from here on is a real sensor reading.",
                        uptime()
                    );
                }
                Ok(Err(e)) => {
                    fail_streak += 1;
                    log_connect_failure(&board_addr, fail_streak, &e.to_string());
                    next_connect = Instant::now() + Duration::from_secs(BOARD_RETRY_SEC);
                }
                Err(_) => {
                    fail_streak += 1;
                    log_connect_failure(&board_addr, fail_streak, "connect timed out");
                    next_connect = Instant::now() + Duration::from_secs(BOARD_RETRY_SEC);
                }
            }
            continue;
        };

        // ---------------- มีสาย ----------------
        if br.read_only {
            fail_pending(&br, err::READ_ONLY); // กันไว้อีกชั้น (handler ตอบ read_only ไปก่อนแล้ว)
        }
        let job = {
            let mut st = br.lock();
            let job = st.pending.take();
            if let Some(j) = &job {
                st.active_conn = Some(j.conn);
            }
            job
        };

        let just_fed = job.is_some();
        let result = if let Some(job) = job {
            let r = run_feed(s, &br, &job, &mut last_op0).await;
            br.lock().active_conn = None;
            if r.is_err() {
                pul_maybe_high = true;
            }
            last_io = Instant::now();
            r
        } else {
            let clients = br.lock().clients;
            if clients > 0 {
                // มี Python: 1 รอบ = op0 → op1 → อ่าน ip0 (เหมือนของเดิม ต่อ 1 บรรทัดของ Python)
                let t = Instant::now();
                let r = io_cycle(s, &br, !br.read_only).await;
                if r.is_ok() && !br.read_only {
                    last_op0 = t;
                }
                last_io = Instant::now();
                r
            } else if last_io.elapsed() >= HEARTBEAT_GAP {
                // ไม่มี Python: heartbeat อ่านอย่างเดียว เลี้ยงสายไม่ให้บอร์ดตัดที่ ~200 ms
                let r = read_ip0(s).await.map(|v| br.lock().ip0 = v);
                last_io = Instant::now();
                r
            } else {
                Ok(())
            }
        };

        if let Err(e) = result {
            // error ของสายบอร์ด → ทิ้งสาย ห้าม resync ในสายเดิม (board_protocol.md 11 ข้อ 10)
            stream = None;
            mark_link_down(&e.to_string());
            next_connect = Instant::now() + Duration::from_secs(BOARD_RETRY_SEC);
            continue;
        }

        // รอบรรทัดถัดไปของ Python / งาน feed / ถึงรอบ heartbeat
        // (เพิ่งจบ feed → ทำรอบปกติทันที ไม่รอบรรทัดถัดไป — op0/op1/ip0 ไม่เว้นช่วงตรงรอยต่อ)
        let has_pending = br.lock().pending.is_some();
        if !has_pending && !just_fed {
            tokio::select! {
                _ = br.wake.notified() => {}
                _ = sleep_until((last_io + HEARTBEAT_GAP).into()) => {}
            }
        }
    }
}

/// รอบปกติ: เขียน op0 + op1 (PUL ต่ำ) แล้วอ่าน ip0
async fn io_cycle(s: &mut TcpStream, br: &Bridge, write: bool) -> Result<(), BoardErr> {
    let (op0, op1_base) = {
        let st = br.lock();
        (st.op0, st.op1_base)
    };
    if write {
        write_bank(s, OP0_COIL_ADDR, op0).await?;
        write_bank(s, OP1_COIL_ADDR, compose_op1(op1_base, false)).await?;
    }
    let ip0 = read_ip0(s).await?;
    br.lock().ip0 = ip0;
    Ok(())
}

/// แทรกระหว่าง feed: เขียน op0 ล่าสุด + อ่าน ip0 (op1 ไปกับเฟรมพัลส์ทุกเฟรมอยู่แล้ว)
async fn interleave(s: &mut TcpStream, br: &Bridge) -> Result<(), BoardErr> {
    let op0 = br.lock().op0;
    write_bank(s, OP0_COIL_ADDR, op0).await?;
    let ip0 = read_ip0(s).await?;
    br.lock().ip0 = ip0;
    Ok(())
}

/// รอจนถึง `deadline` — ระหว่างรอแทรก op0/ip0 ตามเวลา และ (ถ้าให้ `abort`) หยุดรอทันทีเมื่อถูกสั่ง abort
/// คืน `Ok(true)` = ถูก abort ระหว่างรอ
async fn wait_until(
    s: &mut TcpStream,
    br: &Bridge,
    deadline: Instant,
    last_inter: &mut Instant,
    abort: Option<&AtomicBool>,
) -> Result<bool, BoardErr> {
    loop {
        if abort.map_or(false, |a| a.load(Ordering::SeqCst)) {
            return Ok(true);
        }
        // แทรกก่อนเช็ค deadline → half_ms = 0 (ไม่มีช่วงรอ) ก็ยังแทรกครบตามเวลา
        if last_inter.elapsed() >= FEED_INTERLEAVE {
            *last_inter = Instant::now();
            interleave(s, br).await?;
            continue;
        }
        let now = Instant::now();
        if now >= deadline {
            return Ok(false);
        }
        let wake_at = deadline.min(*last_inter + FEED_INTERLEAVE);
        // timer ของ tokio ละเอียด 1 ms และปัดขึ้น → ถ้า sleep ตรงถึงเป้าจะเลยไป ~1–2 ms ทุกขอบ
        // (half_ms 5 จะช้ากว่า tools/feed_pulse_test.py ที่ user วัดความเร็วไว้) → sleep ถึงก่อนเป้า
        // SPIN_MARGIN แล้ววน yield ช่วงท้าย · เงื่อนไข "ไม่เร็วกว่าเป้า" ยังคงอยู่เพราะวนเช็ค now >= deadline
        let remaining = wake_at.saturating_duration_since(now);
        if remaining <= SPIN_MARGIN {
            tokio::task::yield_now().await;
            continue;
        }
        let sleep_to = wake_at - SPIN_MARGIN;
        if abort.is_some() {
            tokio::select! {
                _ = sleep_until(sleep_to.into()) => {}
                _ = br.wake.notified() => {}   // abort / บรรทัดใหม่ — วนกลับไปเช็คธง
            }
        } else {
            sleep_until(sleep_to.into()).await;
        }
    }
}

/// ส่งพัลส์ตาม protocol.md 9.5
///   1 พัลส์ = addr 72 `base|0x10` → ack → รอ half → `base` → ack → sent += 1
///   ขอบถัดไปไม่เร็วกว่า t_เริ่มส่งขอบก่อนหน้า + half_ms (เวลาไป-กลับซ้อนอยู่ในช่วงรอ เหมือน tools/feed_pulse_test.py)
///   abort เช็คก่อนขอบขึ้นทุกครั้ง · ขอบขึ้นออกไปแล้วส่งขอบลงให้จบเสมอ
/// คืน Err เมื่อสายบอร์ดพัง (รายงาน error ไปแล้วในนี้) — ผู้เรียกทิ้งสาย
async fn run_feed(
    s: &mut TcpStream,
    br: &Bridge,
    job: &FeedJob,
    last_op0: &mut Instant,
) -> Result<(), BoardErr> {
    let half = Duration::from_secs_f64(job.half_ms / 1000.0);
    let t0 = Instant::now();
    println!(
        "[REAL] FEED id={} START pulses={} half_ms={} at {}",
        job.id,
        job.total,
        job.half_ms,
        uptime()
    );

    let mut sent: u32 = 0;
    let mut next_rise = t0;
    let mut last_inter = *last_op0;
    let mut max_ack = Duration::ZERO;
    // ช่วงห่างระหว่างขอบที่สั้นที่สุดที่เกิดจริง (วัดจากเวลาเริ่มส่งเฟรม) — ต้อง >= half_ms เสมอ (9.5 ข้อ 4)
    let mut min_edge_gap = Duration::MAX;
    let mut prev_fall: Option<Instant> = None;

    let outcome: Result<FeedState, BoardErr> = async {
        loop {
            if sent >= job.total {
                return Ok(FeedState::Done);
            }
            // ---- รอถึงเวลาขอบขึ้น (abort ได้) ----
            if wait_until(s, br, next_rise, &mut last_inter, Some(&job.abort)).await? {
                return Ok(FeedState::Aborted);
            }
            if job.abort.load(Ordering::SeqCst) {
                return Ok(FeedState::Aborted);
            }
            // ---- ขอบขึ้น ----
            let base = br.lock().op1_base;
            let t_rise = Instant::now();
            if let Some(pf) = prev_fall {
                min_edge_gap = min_edge_gap.min(t_rise - pf);
            }
            write_bank(s, OP1_COIL_ADDR, compose_op1(base, true)).await?;
            max_ack = max_ack.max(t_rise.elapsed());
            // ---- ครึ่งคาบสูง (ไม่ตัดด้วย abort — ขอบลงต้องออกเสมอ) ----
            wait_until(s, br, t_rise + half, &mut last_inter, None).await?;
            // ---- ขอบลง ----
            let base = br.lock().op1_base;
            let t_fall = Instant::now();
            min_edge_gap = min_edge_gap.min(t_fall - t_rise);
            prev_fall = Some(t_fall);
            write_bank(s, OP1_COIL_ADDR, compose_op1(base, false)).await?;
            max_ack = max_ack.max(t_fall.elapsed());
            sent += 1;
            br.update_report(job.conn, job.id, |r| r.sent = sent);
            next_rise = t_fall + half;
        }
    }
    .await;
    *last_op0 = last_inter;

    let secs = t0.elapsed().as_secs_f64();
    let rate = if secs > 0.0 { sent as f64 / secs } else { 0.0 };
    match outcome {
        Ok(state) => {
            br.update_report(job.conn, job.id, |r| {
                r.sent = sent;
                r.state = state;
                r.err = "";
            });
            let word = if state == FeedState::Done { "DONE (pulses sent in full)" } else { "ABORTED" };
            println!(
                "[REAL] FEED id={} {word} sent={sent}/{} in {secs:.3}s = {rate:.1} pulses/s, max ack {:.1} ms, min edge gap {:.2} ms (half_ms {}), PUL low at {}",
                job.id,
                job.total,
                max_ack.as_secs_f64() * 1000.0,
                if min_edge_gap == Duration::MAX { 0.0 } else { min_edge_gap.as_secs_f64() * 1000.0 },
                job.half_ms,
                uptime()
            );
            Ok(())
        }
        Err(e) => {
            let code = e.code();
            br.update_report(job.conn, job.id, |r| {
                *r = FeedReport::error(job.id, job.total, sent, code);
            });
            println!(
                "[REAL] FEED id={} ERROR err='{code}' ({e}) sent={sent}/{} after {secs:.3}s - dropping board link, PUL may be HIGH until reconnect at {}",
                job.id,
                job.total,
                uptime()
            );
            Err(e)
        }
    }
}
