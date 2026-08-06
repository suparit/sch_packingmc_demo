// ==================================================================
// Rust I/O Layer — สะพานระหว่าง Python Gateway (TCP 8767) กับบอร์ด STM32 (Modbus TCP 502)
// ==================================================================
//
// บทบาทของไฟล์นี้
//   - เป็น "server" ที่ 127.0.0.1:8767 รอ gateway_fsm_upgrad.py (RUST_BRIDGE=1) ต่อเข้ามา
//   - เป็น "client" ต่อออกไปหาบอร์ดจริงที่ 192.168.0.100:502 (Modbus TCP)
//   ดูตารางพอร์ตฉบับเต็มที่ docs/specs/port_map.md
//
// สิ่งที่แก้รอบ 2026-08-04
// -----------------------
// 1) เดิมต่อบอร์ด "ครั้งเดียวตอน start" ถ้าต่อไม่ติดจะตกเข้าโหมดจำลองถาวร
//    ตอนนี้มี task เฝ้าสาย (board_link_supervisor) ลองใหม่ทุก 3 วินาที ครอบทั้ง 3 เคส:
//       ต่อไม่ติดตั้งแต่เริ่ม / หลุดกลางทาง / บอร์ดกลับมาแล้วต่อเองได้โดยไม่ต้องรีสตาร์ต
//    **ห้ามลองถี่กว่า 3 วินาที** ของเดิมฝั่ง Python เคยยิงใหม่ทุก 20 ms ตอนบอร์ดไม่ได้เสียบ
//    จน log ท่วมและกิน CPU
//
// 2) เดิมดูจาก log ไม่ออกเลยว่าเลข ip0 ที่ส่งกลับ Python มาจากเซนเซอร์จริงหรือเป็นค่าที่
//    Python ส่งมาเองแล้วสะท้อนกลับ (loopback) ตอนนี้ทุกบรรทัดที่มีค่า I/O ต้องขึ้นต้นด้วย
//       [REAL] = อ่านมาจากบอร์ดจริงผ่าน Modbus
//       [SIM]  = ค่าจำลอง/สะท้อนกลับ ไม่ได้แตะฮาร์ดแวร์เลย
//
// 3) การอ่าน/เขียนบอร์ดทุกจุดมี timeout กำกับ ของเดิม heartbeat ยิง "*IDN?" แล้ว await read
//    ทั้งที่ยัง "ถือ Mutex อยู่" — ถ้าบอร์ดไม่ตอบ (Modbus server มองว่าเฟรมนี้ผิดรูป) สะพานจะ
//    ค้างทั้งตัว Python จะไม่ได้รับคำตอบอีกเลย ตอนนี้เปลี่ยน heartbeat เป็นเฟรม Modbus
//    "Read Coils (0x01)" ซึ่งเป็นคำสั่งอ่านอย่างเดียว + มี timeout
//
// ตัวแปรสภาพแวดล้อม (ค่า default = พฤติกรรมเดิมทุกตัว)
//   STM32_ADDR     — พิกัดบอร์ด (default 192.168.0.100:502) ใช้ชี้ไป mock server ตอนทดสอบ
//   BRIDGE_ADDR    — พิกัดที่เปิดรอ Python (default 127.0.0.1:8767)
//   RUST_READ_ONLY — ตั้ง "1" แล้วจะ **ไม่ส่งคำสั่งเขียน coil (0x0F)** ลงบอร์ด ส่งแต่คำสั่งอ่าน
//                    ใช้ตอนอยากทดสอบกับบอร์ดจริงโดยไม่ไปแตะสถานะเอาต์พุตของมัน

use serde::{Deserialize, Serialize};
use std::env;
use std::io::{self, ErrorKind};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, OnceLock};
use std::time::{Duration, Instant};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::Mutex;
use tokio::time::timeout;

#[derive(Serialize, Deserialize, Debug, Clone)]
struct PythonSystemData {
    current_state: String,
    running: bool,
    op0: u8,
    ip0: u8,
    cycles: u32,
}

// พิกัด IP บอร์ดของนิวตามที่ตั้งไว้ในโค้ดตัวอย่างไฟกระพริบ
const STM32_IP_ADDR: &str = "192.168.0.100:502";
// 8766 ถูกจองไว้ให้จอ TouchGFX ต่อเข้า Python Gateway แล้ว (ดู python_backend/hmi_link.py)
// สะพานตัวนี้จึงอยู่ที่ 8767 — ตรงกับค่า RUST_PORT ใน gateway_fsm_upgrad.py
const PYTHON_BRIDGE_ADDR: &str = "127.0.0.1:8767";

/// จังหวะลองต่อบอร์ดใหม่ — ห้ามลดต่ำกว่านี้ (บทเรียนจากรอบก่อน: reconnect ทุก 20 ms)
const BOARD_RETRY_SEC: u64 = 3;
const BOARD_CONNECT_TIMEOUT: Duration = Duration::from_secs(2);
const BOARD_IO_TIMEOUT: Duration = Duration::from_millis(500);
/// เว้นช่วง log ค่า I/O อย่างน้อยเท่านี้ (Python ยิงเข้ามาทุก 20 ms = 50 ครั้ง/วิ)
const IO_LOG_MIN_INTERVAL: Duration = Duration::from_secs(5);
/// ต่อบอร์ดไม่ติดติด ๆ กัน ให้เตือนซ้ำทุก ๆ กี่รอบ (10 x 3 วิ = 30 วิ)
const RETRY_LOG_EVERY: u64 = 10;

/// true = ตอนนี้สายไปบอร์ดจริงใช้งานได้ → ตัวเลขที่ส่งกลับ Python เป็นของจริง
static BOARD_LINK_UP: AtomicBool = AtomicBool::new(false);

/// เวลาที่โปรเซสเริ่ม — ใช้พิมพ์ t=..s บนบรรทัดเหตุการณ์ของสาย จะได้ไล่ดูจังหวะ retry ได้
static START_TIME: OnceLock<Instant> = OnceLock::new();

fn uptime() -> String {
    let t0 = START_TIME.get_or_init(Instant::now);
    format!("t={:.1}s", t0.elapsed().as_secs_f64())
}

/// สายไปบอร์ด + เวลาที่คุยกับบอร์ดครั้งล่าสุด (ใช้ตัดสินว่าต้องยิง heartbeat ไหม)
struct BoardLink {
    stream: Option<TcpStream>,
    last_io: Instant,
}

type Link = Arc<Mutex<BoardLink>>;

/// ป้ายบอกที่มาของตัวเลขในบรรทัด log — กว้างเท่ากันทั้งสองแบบเพื่อให้อ่านเป็นคอลัมน์
fn tag() -> &'static str {
    if BOARD_LINK_UP.load(Ordering::Relaxed) {
        "[REAL]"
    } else {
        "[SIM] "
    }
}

/// เฟรม Modbus TCP "Read Coils (0x01)" อ่าน 8 บิตแรก — ถอดแบบจากฟังก์ชัน read_ip ของนิว
/// เป็นคำสั่ง **อ่านอย่างเดียว** ไม่เปลี่ยนค่าอะไรในบอร์ด จึงใช้เป็น heartbeat ได้ปลอดภัย
const MODBUS_READ_IP: [u8; 12] = [
    0x00, 0x00, 0x00, 0x00, 0x00, 0x06, 0x01, 0x01, 0x00, 0x00, 0x00, 0x08,
];

/// เฟรม Modbus TCP "Write Multiple Coils (0x0F)" — ถอดแบบจากฟังก์ชัน write_op ของนิว
/// ⚠️ นี่คือคำสั่ง **เขียน** ลงบอร์ดจริง ปิดได้ด้วย RUST_READ_ONLY=1
fn modbus_write_op(op0: u8) -> [u8; 14] {
    [
        0x00, 0x00, 0x00, 0x00, 0x00, 0x08, 0x01, 0x0F, 0x00, 0x40, 0x00, 0x08, 0x01, op0,
    ]
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

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    START_TIME.get_or_init(Instant::now);
    let board_addr = env::var("STM32_ADDR").unwrap_or_else(|_| STM32_IP_ADDR.to_string());
    let bridge_addr = env::var("BRIDGE_ADDR").unwrap_or_else(|_| PYTHON_BRIDGE_ADDR.to_string());
    let read_only = env::var("RUST_READ_ONLY").unwrap_or_default() == "1";

    println!("=========================================================");
    println!(" [Rust I/O Layer] SCH-IO Socket Bridge");
    println!("   Python FSM  : tcp://{bridge_addr}  (server, waiting for gateway_fsm_upgrad.py)");
    println!("   STM32 board : tcp://{board_addr}  (client, Modbus TCP)");
    println!("   reconnect   : every {BOARD_RETRY_SEC} s while the board is unreachable");
    if read_only {
        println!("   RUST_READ_ONLY=1 : coil write (0x0F) DISABLED - read-only frames only");
    }
    println!("=========================================================");
    println!(
        "[SIM]  starting in SIMULATED mode - board not connected yet. \
         Every value returned to Python is an echo of what Python sent."
    );

    // เปิดพอร์ตรอ Python "ก่อน" ไปยุ่งกับบอร์ด — ของเดิม connect บอร์ดก่อน bind ถ้าบอร์ด
    // ไม่ตอบ TCP จะค้างรอ SYN timeout ~20 วิ กว่า 8767 จะขึ้น Python ก็ต่อไม่ติดช่วงนั้น
    let listener = TcpListener::bind(&bridge_addr).await?;
    println!("[BRIDGE] listening for Python FSM core on tcp://{bridge_addr}");

    let link: Link = Arc::new(Mutex::new(BoardLink {
        stream: None,
        last_io: Instant::now(),
    }));

    // task เฝ้าสายไปบอร์ด: ต่อใหม่ทุก 3 วิ ตอนสายหลุด / เช็คชีพจรตอนสายว่าง
    let link_for_supervisor = Arc::clone(&link);
    let board_addr_for_supervisor = board_addr.clone();
    tokio::spawn(async move {
        board_link_supervisor(link_for_supervisor, board_addr_for_supervisor).await;
    });

    loop {
        let (socket, addr) = listener.accept().await?;
        println!("{} [BRIDGE] Python gateway connected from {addr}", tag());
        let link_for_conn = Arc::clone(&link);
        tokio::spawn(async move {
            if let Err(e) = handle_python_connection(socket, link_for_conn, read_only).await {
                println!("{} [BRIDGE] python connection closed: {e}", tag());
            } else {
                println!("{} [BRIDGE] python connection closed", tag());
            }
        });
    }
}

// ==================================================================
// เฝ้าสายไปบอร์ด — ทำงานตลอดอายุโปรเซส
// ==================================================================
async fn board_link_supervisor(link: Link, board_addr: String) {
    let mut fail_streak: u64 = 0;

    loop {
        let connected = { link.lock().await.stream.is_some() };

        if !connected {
            // --- เคส 1+3: ต่อไม่ติดตั้งแต่เริ่ม / บอร์ดเพิ่งกลับมา ---
            // connect นอก lock เพื่อไม่ให้ลูป 20 ms ฝั่ง Python ต้องรอ
            match timeout(BOARD_CONNECT_TIMEOUT, TcpStream::connect(&board_addr)).await {
                Ok(Ok(stream)) => {
                    let _ = stream.set_nodelay(true);
                    {
                        let mut guard = link.lock().await;
                        guard.stream = Some(stream);
                        guard.last_io = Instant::now();
                    }
                    BOARD_LINK_UP.store(true, Ordering::Relaxed);
                    fail_streak = 0;
                    println!(
                        "[REAL] BOARD LINK UP at {} - connected to STM32 at {board_addr}. \
                         ip0 from here on is a real sensor reading.",
                        uptime()
                    );
                }
                Ok(Err(e)) => {
                    fail_streak += 1;
                    log_connect_failure(&board_addr, fail_streak, &e.to_string());
                }
                Err(_) => {
                    fail_streak += 1;
                    log_connect_failure(&board_addr, fail_streak, "connect timed out");
                }
            }
        } else {
            // --- เคส 2: สายหลุดกลางทางแบบเงียบ ๆ ---
            // ยิง heartbeat เฉพาะตอนไม่มีทราฟฟิกจาก Python มาสักพัก จะได้ไม่ไปชนกับ
            // เฟรมตอบกลับของธุรกรรมปกติ (ทั้งสองทางใช้ Mutex ตัวเดียวกัน)
            let mut guard = link.lock().await;
            let idle = guard.last_io.elapsed() >= Duration::from_secs(BOARD_RETRY_SEC);
            if idle {
                if let Some(stream) = guard.stream.as_mut() {
                    match probe_board(stream).await {
                        Ok(()) => {
                            guard.last_io = Instant::now();
                        }
                        Err(e) => {
                            guard.stream = None;
                            mark_link_down(&e.to_string());
                        }
                    }
                }
            }
        }

        tokio::time::sleep(Duration::from_secs(BOARD_RETRY_SEC)).await;
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

/// heartbeat แบบอ่านอย่างเดียว — ใช้ยืนยันว่าสายยังใช้ได้จริง
async fn probe_board(stream: &mut TcpStream) -> io::Result<()> {
    stream.write_all(&MODBUS_READ_IP).await?;
    let mut buf = [0u8; 32];
    match timeout(BOARD_IO_TIMEOUT, stream.read(&mut buf)).await {
        Ok(Ok(0)) => Err(io::Error::new(ErrorKind::UnexpectedEof, "board closed the socket")),
        Ok(Ok(_)) => Ok(()),
        Ok(Err(e)) => Err(e),
        Err(_) => Err(io::Error::new(ErrorKind::TimedOut, "heartbeat timed out")),
    }
}

// ==================================================================
// สายฝั่ง Python (8767)
// ==================================================================
async fn handle_python_connection(
    mut stream: TcpStream,
    link: Link,
    read_only: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut buffer = [0u8; 1024];
    let mut last_log = Instant::now() - IO_LOG_MIN_INTERVAL; // ให้ log บรรทัดแรกทันที
    let mut last_ip0: i32 = -1;
    let mut last_from_board: Option<bool> = None;

    loop {
        let bytes_read = stream.read(&mut buffer).await?;
        if bytes_read == 0 {
            break;
        }

        let raw_data = String::from_utf8_lossy(&buffer[..bytes_read]);
        for json_chunk in raw_data.split('\n') {
            if json_chunk.trim().is_empty() {
                continue;
            }

            let sys_data = match serde_json::from_str::<PythonSystemData>(json_chunk) {
                Ok(v) => v,
                Err(_) => continue,
            };

            let (ip0, from_board) = exchange_with_board(&link, &sys_data, read_only).await;

            // ⚠️ รูปทรง JSON ที่ตอบกลับ Python ต้องคงเดิม: มีคีย์ "ip0" คีย์เดียว
            //    ถ้าจะเพิ่มคีย์บอกที่มา (เช่น "src") ต้องให้ integration แก้ protocol.md ก่อน
            let response = format!("{{\"ip0\":{ip0}}}\n");
            stream.write_all(response.as_bytes()).await?;

            // log ค่า I/O — พิมพ์เมื่อค่าเปลี่ยน / ที่มาเปลี่ยน / ครบรอบเวลา
            let changed = last_ip0 != ip0 as i32 || last_from_board != Some(from_board);
            if changed || last_log.elapsed() >= IO_LOG_MIN_INTERVAL {
                if from_board {
                    println!(
                        "[REAL] ip0=0x{ip0:02X} <- STM32 sensor | op0=0x{:02X} -> board{} | state={} cycles={}",
                        sys_data.op0,
                        if read_only { " (SKIPPED: read-only)" } else { "" },
                        sys_data.current_state,
                        sys_data.cycles
                    );
                } else {
                    println!(
                        "[SIM]  ip0=0x{ip0:02X} <- echo of Python's own value (NO board link) | op0=0x{:02X} not written | state={} cycles={}",
                        sys_data.op0, sys_data.current_state, sys_data.cycles
                    );
                }
                last_log = Instant::now();
                last_ip0 = ip0 as i32;
                last_from_board = Some(from_board);
            }
        }
    }
    Ok(())
}

/// คุยกับบอร์ดหนึ่งรอบ คืน (ค่า ip0, ค่านี้มาจากบอร์ดจริงหรือเปล่า)
/// ถ้าไม่มีสาย/สายพัง จะคืนค่าที่ Python ส่งมาเอง (loopback) พร้อม flag = false
async fn exchange_with_board(link: &Link, sys: &PythonSystemData, read_only: bool) -> (u8, bool) {
    let mut guard = link.lock().await;
    guard.last_io = Instant::now();

    let stream = match guard.stream.as_mut() {
        Some(s) => s,
        None => return (sys.ip0, false),
    };

    match board_transaction(stream, sys, read_only).await {
        Ok(ip0) => (ip0, true),
        Err(e) => {
            // สายพังกลางคัน: ทิ้งทันทีแล้วให้ supervisor ต่อใหม่ในอีก 3 วิ
            // (ไม่ใช้สายเดิมต่อ เพราะอาจมีเฟรมค้างในท่อจนอ่านเพี้ยน)
            guard.stream = None;
            mark_link_down(&e.to_string());
            (sys.ip0, false)
        }
    }
}

async fn board_transaction(
    stream: &mut TcpStream,
    sys: &PythonSystemData,
    read_only: bool,
) -> io::Result<u8> {
    if !read_only {
        // 1. สั่งเอาต์พุตลงบอร์ด (Write Multiple Coils)
        stream.write_all(&modbus_write_op(sys.op0)).await?;
        let mut ack_buf = [0u8; 12];
        match timeout(BOARD_IO_TIMEOUT, stream.read(&mut ack_buf)).await {
            Ok(Ok(0)) => return Err(io::Error::new(ErrorKind::UnexpectedEof, "board closed the socket")),
            Ok(Ok(_)) => {}
            Ok(Err(e)) => return Err(e),
            Err(_) => return Err(io::Error::new(ErrorKind::TimedOut, "write-ack timed out")),
        }
    }

    // 2. อ่านเซนเซอร์กลับ (Read Coils) — ไบต์ที่ 9 คือข้อมูลเซนเซอร์
    stream.write_all(&MODBUS_READ_IP).await?;
    let mut resp_buf = [0u8; 10];
    let n = match timeout(BOARD_IO_TIMEOUT, stream.read(&mut resp_buf)).await {
        Ok(Ok(n)) => n,
        Ok(Err(e)) => return Err(e),
        Err(_) => return Err(io::Error::new(ErrorKind::TimedOut, "sensor read timed out")),
    };
    if n == 0 {
        return Err(io::Error::new(ErrorKind::UnexpectedEof, "board closed the socket"));
    }
    if n < 10 {
        return Err(io::Error::new(
            ErrorKind::InvalidData,
            format!("short modbus reply ({n} bytes)"),
        ));
    }
    Ok(resp_buf[9])
}
