// ==================================================================
// ส่วนตรรกะล้วน (ไม่มี I/O) — แยกออกมาเพื่อให้ `cargo test` ทดสอบได้โดยไม่ต้องมีบอร์ด/ซ็อกเก็ต
// ==================================================================
//
// อ้างอิงสัญญา
//   docs/specs/protocol.md ข้อ 9       — สาย 8767 Python <-> Rust (framing, feed_cmd, idempotent, รายงาน)
//   docs/specs/board_protocol.md 9, 11 — เฟรม Modbus ของบอร์ด (TID 00 00 คงที่, อ่านไบต์ดิบ, ตรวจ fc)

use serde_json::Value;

// ------------------------------------------------------------------
// เฟรม Modbus TCP (board_protocol.md ข้อ 9)
// ------------------------------------------------------------------

/// 🔴 Transaction ID ต้องเป็น `00 00` คงที่ทุกเฟรม ห้ามนับขึ้น (board_protocol.md 9.3 ข้อ 4 / 9.3.1)
/// TID ที่นับขึ้นไปชน 0x2A0A (`*\n`) ปลุก text parser ในพอร์ต 502 — ตัวเดียวกับที่ `*RST` รีบูตบอร์ด
pub const TID: [u8; 2] = [0x00, 0x00];
pub const UNIT_ID: u8 = 0x01;
pub const FC_READ_COILS: u8 = 0x01;
pub const FC_WRITE_COILS: u8 = 0x0F;

/// ความยาวเฟรมตอบที่ **วัดได้จริง** — ห้ามเชื่อฟิลด์ length ของบอร์ด (board_protocol.md 9.3 ข้อ 1)
pub const READ_REPLY_LEN: usize = 10;
pub const WRITE_ACK_LEN: usize = 12;
/// ไบต์ที่เป็นค่าอินพุตในเฟรมตอบ 0x01 (board_protocol.md 9.2 / 9.3 ข้อ 2)
pub const READ_DATA_INDEX: usize = 9;
/// ไบต์ function code ในเฟรมตอบ — ต้องเท่ากับ fc ที่ส่งไป (board_protocol.md 11 ข้อ 10)
pub const REPLY_FC_INDEX: usize = 7;

/// coil address ของแผ่นเอาต์พุต (board_protocol.md 9.1 / 9.1.1)
pub const OP0_COIL_ADDR: u16 = 64; // แผ่น 1 — ไฟสถานะ FSM
pub const OP1_COIL_ADDR: u16 = 72; // แผ่น 2 — โซลินอยด์ A/B (bit0/1) + PUL มอเตอร์ feed (bit4)

/// bit 4 ของ op1 = PUL ของไดรเวอร์มอเตอร์ feed — เป็นของ Rust คนเดียว (protocol.md 9.6)
pub const PUL_BIT: u8 = 0x10;

/// "Read Coils (0x01)" 8 บิตเริ่ม address 0 = อินพุตจริง `ip0` · อ่านอย่างเดียว ใช้เป็น heartbeat ได้
pub const MODBUS_READ_IP: [u8; 12] = [
    TID[0], TID[1], 0x00, 0x00, 0x00, 0x06, UNIT_ID, FC_READ_COILS, 0x00, 0x00, 0x00, 0x08,
];

/// "Write Multiple Coils (0x0F)" เต็มแผ่น 8 บิต
pub fn modbus_write_bank(addr: u16, value: u8) -> [u8; 14] {
    let [hi, lo] = addr.to_be_bytes();
    [
        TID[0], TID[1], 0x00, 0x00, 0x00, 0x08, UNIT_ID, FC_WRITE_COILS, hi, lo, 0x00, 0x08, 0x01,
        value,
    ]
}

/// ไบต์ที่เขียนลง addr 72 — **คำนวณที่นี่ที่เดียว** (protocol.md 9.6)
///   `(op1_จาก_Python & 0xEF) | (PUL_สูง ? 0x10 : 0x00)`
/// bit 4 จาก Python ถูก mask ทิ้งเสมอ (defense in depth — Python ไม่ควรตั้งมาอยู่แล้ว)
pub fn compose_op1(python_op1: u8, pul_high: bool) -> u8 {
    (python_op1 & !PUL_BIT) | if pul_high { PUL_BIT } else { 0 }
}

// ------------------------------------------------------------------
// รายงาน feed (protocol.md 9.4)
// ------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FeedState {
    Idle,
    Running,
    Done,
    Aborted,
    Error,
}

impl FeedState {
    pub fn as_str(self) -> &'static str {
        match self {
            FeedState::Idle => "idle",
            FeedState::Running => "running",
            FeedState::Done => "done",
            FeedState::Aborted => "aborted",
            FeedState::Error => "error",
        }
    }
}

/// รหัส error ของ `feed.err` — ตารางใน protocol.md 9.4 ห้ามเพิ่มเองโดยไม่ผ่าน integration
pub mod err {
    pub const BOARD_DOWN: &str = "board_down";
    pub const READ_ONLY: &str = "read_only";
    pub const BAD_PULSES: &str = "bad_pulses";
    pub const BAD_HALF_MS: &str = "bad_half_ms";
    pub const ACK_TIMEOUT: &str = "ack_timeout";
    pub const ACK_BAD_FC: &str = "ack_bad_fc";
    pub const IO_ERROR: &str = "io_error";
}

#[derive(Debug, Clone, PartialEq)]
pub struct FeedReport {
    pub id: u32,
    pub state: FeedState,
    pub sent: u32,
    pub total: u32,
    pub err: &'static str,
}

impl FeedReport {
    pub fn idle() -> Self {
        FeedReport { id: 0, state: FeedState::Idle, sent: 0, total: 0, err: "" }
    }
    pub fn running(id: u32, total: u32) -> Self {
        FeedReport { id, state: FeedState::Running, sent: 0, total, err: "" }
    }
    pub fn error(id: u32, total: u32, sent: u32, code: &'static str) -> Self {
        FeedReport { id, state: FeedState::Error, sent, total, err: code }
    }
    pub fn to_json(&self) -> String {
        // err เป็นรหัสคงที่จากโมดูล err เท่านั้น (ASCII ไม่มีเครื่องหมายคำพูด) จึง format ตรงได้
        format!(
            "{{\"id\":{},\"state\":\"{}\",\"sent\":{},\"total\":{},\"err\":\"{}\"}}",
            self.id,
            self.state.as_str(),
            self.sent,
            self.total,
            self.err
        )
    }
}

/// บรรทัดคำตอบ Rust -> Python (protocol.md 9.4) — ลำดับคีย์ตามตัวอย่างในสเปก ปิดด้วย `\n`
pub fn response_line(ip0: u8, board: bool, feed: &FeedReport) -> String {
    format!("{{\"ip0\":{ip0},\"board\":{board},\"feed\":{}}}\n", feed.to_json())
}

// ------------------------------------------------------------------
// ตัดสินคำสั่ง feed_cmd (protocol.md 9.2 + 9.3)
// ------------------------------------------------------------------

pub const PULSES_MIN: u64 = 1;
pub const PULSES_MAX: u64 = 1000;
pub const HALF_MS_MIN: f64 = 0.0;
pub const HALF_MS_MAX: f64 = 50.0;

#[derive(Debug, Clone, PartialEq)]
pub enum FeedDecision {
    /// `feed_cmd` ผิดรูปจนไม่รู้ว่าเป็น id ไหน (ไม่ใช่อ็อบเจกต์ / id หาย / id < 1) → ข้ามทั้งคำสั่ง + log
    Malformed(&'static str),
    /// id เดิม ไม่ได้สั่ง abort (หรือ abort ของ id ที่จบไปแล้ว) → ไม่ทำอะไร
    Duplicate,
    /// id เดิม + abort + feed ยัง running → หยุดตามข้อ 9.5 ข้อ 5
    AbortRunning,
    /// id ใหม่ แต่ feed เดิมยัง running → **ไม่รับ** (Python ห้ามทำแบบนี้) · last_id ไม่เปลี่ยน
    RejectBusy { id: u32 },
    /// id ใหม่ จบทันที (aborted ก่อนเริ่ม / error ตรวจไม่ผ่าน) · last_id = id
    Finish(FeedReport),
    /// id ใหม่ ผ่านทุกด่าน → ส่งให้ task เจ้าของสายบอร์ดเริ่มส่งพัลส์ · last_id = id
    Start { id: u32, pulses: u32, half_ms: f64 },
}

/// ตัดสิน `feed_cmd` หนึ่งบรรทัด ตามกติกา idempotent ต่อสาย (protocol.md 9.3)
///
/// * `last_id`  — id ล่าสุดที่สายนี้รับไว้ (`None` = สายใหม่ยังไม่เคยรับ)
/// * `current`  — สถานะ feed ของ `last_id` ตอนนี้
/// * `read_only` / `board_up` — ใช้ตรวจก่อนเริ่ม feed ใหม่เท่านั้น
pub fn decide_feed(
    cmd: &Value,
    last_id: Option<u32>,
    current: &FeedReport,
    read_only: bool,
    board_up: bool,
) -> FeedDecision {
    let obj = match cmd.as_object() {
        Some(o) => o,
        None => return FeedDecision::Malformed("feed_cmd is not an object"),
    };
    let id = match obj.get("id").and_then(Value::as_u64) {
        Some(v) if v >= 1 && v <= u32::MAX as u64 => v as u32,
        _ => return FeedDecision::Malformed("feed_cmd.id missing or not an integer >= 1"),
    };
    // abort: ไม่มีคีย์ / null = false · bool ตามค่า · ชนิดอื่น (เช่น 1, "yes") = ถือว่า abort
    // (ปลอดภัยไว้ก่อน: คำสั่งที่ตั้งใจหยุดแต่ส่งผิดชนิด ต้องหยุด ไม่ใช่เดินต่อ)
    let abort = match obj.get("abort") {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(_) => true,
    };
    let running = current.state == FeedState::Running;

    if Some(id) == last_id {
        return if abort && running {
            FeedDecision::AbortRunning
        } else {
            FeedDecision::Duplicate
        };
    }

    // id ใหม่
    if running {
        return FeedDecision::RejectBusy { id };
    }

    let pulses = parse_pulses(obj.get("pulses"));
    if abort {
        // จบทันทีเป็น aborted sent 0 (ไม่ต้องตรวจอย่างอื่น — ไม่มีอะไรขยับ)
        return FeedDecision::Finish(FeedReport {
            id,
            state: FeedState::Aborted,
            sent: 0,
            total: pulses.unwrap_or(0),
            err: "",
        });
    }
    let pulses = match pulses {
        Some(p) => p,
        None => return FeedDecision::Finish(FeedReport::error(id, 0, 0, err::BAD_PULSES)),
    };
    let half_ms = match parse_half_ms(obj.get("half_ms")) {
        Some(h) => h,
        None => return FeedDecision::Finish(FeedReport::error(id, pulses, 0, err::BAD_HALF_MS)),
    };
    if read_only {
        return FeedDecision::Finish(FeedReport::error(id, pulses, 0, err::READ_ONLY));
    }
    if !board_up {
        return FeedDecision::Finish(FeedReport::error(id, pulses, 0, err::BOARD_DOWN));
    }
    FeedDecision::Start { id, pulses, half_ms }
}

/// `pulses` ต้องเป็นจำนวนเต็ม 1–1000 (ทศนิยม/สตริง/ลบ = ผิด)
pub fn parse_pulses(v: Option<&Value>) -> Option<u32> {
    match v.and_then(Value::as_u64) {
        Some(p) if (PULSES_MIN..=PULSES_MAX).contains(&p) => Some(p as u32),
        _ => None,
    }
}

/// `half_ms` ไม่มีคีย์ = 0 · ต้องเป็นตัวเลข 0–50 · **ไม่ clamp** — ค่าผิดต้องเห็น (protocol.md 9.2)
/// `null` / สตริง / bool ถือว่า "ไม่ใช่ตัวเลข"
pub fn parse_half_ms(v: Option<&Value>) -> Option<f64> {
    match v {
        None => Some(0.0),
        Some(Value::Number(n)) => match n.as_f64() {
            Some(h) if h.is_finite() && (HALF_MS_MIN..=HALF_MS_MAX).contains(&h) => Some(h),
            _ => None,
        },
        Some(_) => None,
    }
}

// ------------------------------------------------------------------
// framing แบบ line-buffered (protocol.md 9.1)
// ------------------------------------------------------------------

/// สะสมไบต์จาก TCP แล้วตัดทีละ `\n` · เศษท้ายเก็บไว้รอบหน้า · คืนทุกบรรทัดตามลำดับ (ห้ามทิ้งบรรทัดที่มี abort)
///
/// กันหน่วยความจำบวม: ถ้าสะสมเกิน `max_line` โดยไม่เจอ `\n` จะทิ้งก้อนนั้นทั้งหมด
/// จนกว่าจะเจอ `\n` ถัดไป (resync) แล้วนับไว้ใน `dropped`
pub struct LineBuffer {
    buf: Vec<u8>,
    max_line: usize,
    discarding: bool,
    pub dropped: u64,
}

impl LineBuffer {
    pub fn new(max_line: usize) -> Self {
        LineBuffer { buf: Vec::with_capacity(1024), max_line, discarding: false, dropped: 0 }
    }

    /// ป้อนก้อนไบต์ที่อ่านได้ คืนบรรทัดสมบูรณ์ (ไม่รวม `\n` / `\r` ท้าย)
    pub fn push(&mut self, data: &[u8]) -> Vec<Vec<u8>> {
        let mut out = Vec::new();
        for &b in data {
            if b == b'\n' {
                if self.discarding {
                    self.discarding = false;
                } else {
                    let mut line = std::mem::take(&mut self.buf);
                    if line.last() == Some(&b'\r') {
                        line.pop();
                    }
                    out.push(line);
                }
                continue;
            }
            if self.discarding {
                continue;
            }
            self.buf.push(b);
            if self.buf.len() > self.max_line {
                self.buf.clear();
                self.discarding = true;
                self.dropped += 1;
            }
        }
        out
    }

    /// ไบต์ที่ค้างรอ `\n` อยู่ตอนนี้ (ใช้ในเทสต์)
    #[cfg(test)]
    pub fn pending_len(&self) -> usize {
        self.buf.len()
    }
}

// ==================================================================
// unit tests — `cargo test`
// ==================================================================
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // ---------- เฟรม ----------

    #[test]
    fn frames_use_constant_tid_zero() {
        assert_eq!(&MODBUS_READ_IP[0..2], &[0, 0]);
        for addr in [OP0_COIL_ADDR, OP1_COIL_ADDR] {
            for v in [0x00u8, 0x10, 0xFF, 0x2A] {
                let f = modbus_write_bank(addr, v);
                assert_eq!(&f[0..2], &[0, 0], "TID ต้อง 00 00 เสมอ");
            }
        }
    }

    #[test]
    fn write_frame_matches_board_protocol() {
        // board_protocol.md 9.1.1: 00 00 | 00 00 | 00 08 | 01 | 0F | 00 48 | 00 08 | 01 | <op1>
        assert_eq!(
            modbus_write_bank(72, 0x13),
            [0, 0, 0, 0, 0, 8, 1, 0x0F, 0x00, 0x48, 0, 8, 1, 0x13]
        );
        // 9.1: addr 64 = 00 40
        assert_eq!(modbus_write_bank(64, 0x08)[8..10], [0x00, 0x40]);
        // 9.2: 00 00 | 00 00 | 00 06 | 01 | 01 | 00 00 | 00 08
        assert_eq!(MODBUS_READ_IP, [0, 0, 0, 0, 0, 6, 1, 1, 0, 0, 0, 8]);
    }

    // ---------- op1 composition (9.6) ----------

    #[test]
    fn op1_masks_python_bit4_and_adds_pul() {
        assert_eq!(compose_op1(0x00, false), 0x00);
        assert_eq!(compose_op1(0x00, true), 0x10);
        // bit 0/1 (โซลินอยด์) คงอยู่ทั้งขอบขึ้นและขอบลง
        assert_eq!(compose_op1(0x03, true), 0x13);
        assert_eq!(compose_op1(0x03, false), 0x03);
        // bit 4 จาก Python ถูก mask ทิ้งเสมอ — ตอนไม่มี feed PUL ต้องต่ำ
        assert_eq!(compose_op1(0x10, false), 0x00);
        assert_eq!(compose_op1(0xFF, false), 0xEF);
        assert_eq!(compose_op1(0xFF, true), 0xFF);
    }

    // ---------- parse ----------

    #[test]
    fn half_ms_range_no_clamp() {
        assert_eq!(parse_half_ms(None), Some(0.0));
        assert_eq!(parse_half_ms(Some(&json!(0))), Some(0.0));
        assert_eq!(parse_half_ms(Some(&json!(5))), Some(5.0));
        assert_eq!(parse_half_ms(Some(&json!(2.5))), Some(2.5));
        assert_eq!(parse_half_ms(Some(&json!(50))), Some(50.0));
        assert_eq!(parse_half_ms(Some(&json!(50.001))), None);
        assert_eq!(parse_half_ms(Some(&json!(51))), None);
        assert_eq!(parse_half_ms(Some(&json!(-1))), None);
        assert_eq!(parse_half_ms(Some(&json!(-0.1))), None);
        assert_eq!(parse_half_ms(Some(&json!("5"))), None);
        assert_eq!(parse_half_ms(Some(&json!(null))), None);
        assert_eq!(parse_half_ms(Some(&json!(true))), None);
    }

    #[test]
    fn pulses_range() {
        assert_eq!(parse_pulses(Some(&json!(1))), Some(1));
        assert_eq!(parse_pulses(Some(&json!(1000))), Some(1000));
        assert_eq!(parse_pulses(Some(&json!(0))), None);
        assert_eq!(parse_pulses(Some(&json!(1001))), None);
        assert_eq!(parse_pulses(Some(&json!(-5))), None);
        assert_eq!(parse_pulses(Some(&json!(115.5))), None);
        assert_eq!(parse_pulses(Some(&json!("115"))), None);
        assert_eq!(parse_pulses(None), None);
    }

    // ---------- idempotency (9.3) ----------

    fn start(id: u32, pulses: u32, half_ms: f64) -> FeedDecision {
        FeedDecision::Start { id, pulses, half_ms }
    }

    #[test]
    fn new_id_starts_then_duplicates_are_ignored() {
        let cmd = json!({"id": 1, "pulses": 115, "half_ms": 5, "abort": false});
        let idle = FeedReport::idle();
        assert_eq!(decide_feed(&cmd, None, &idle, false, true), start(1, 115, 5.0));
        // หลังรับแล้ว last_id = 1 · ซ้ำกี่ครั้งก็ไม่เริ่มใหม่ ทั้งตอน running และตอนจบแล้ว
        let running = FeedReport::running(1, 115);
        let done = FeedReport { id: 1, state: FeedState::Done, sent: 115, total: 115, err: "" };
        for cur in [&running, &done] {
            for _ in 0..100 {
                assert_eq!(decide_feed(&cmd, Some(1), cur, false, true), FeedDecision::Duplicate);
            }
        }
        // id ใหม่หลังจบ → เริ่มใหม่
        let cmd2 = json!({"id": 2, "pulses": 114, "half_ms": 5});
        assert_eq!(decide_feed(&cmd2, Some(1), &done, false, true), start(2, 114, 5.0));
    }

    #[test]
    fn half_ms_missing_means_zero() {
        let cmd = json!({"id": 3, "pulses": 10});
        assert_eq!(decide_feed(&cmd, None, &FeedReport::idle(), false, true), start(3, 10, 0.0));
    }

    #[test]
    fn abort_rules() {
        let running = FeedReport::running(7, 115);
        let abort7 = json!({"id": 7, "pulses": 115, "abort": true});
        assert_eq!(decide_feed(&abort7, Some(7), &running, false, true), FeedDecision::AbortRunning);
        // abort ของ id ที่จบแล้ว = ไม่ทำอะไร
        let done = FeedReport { id: 7, state: FeedState::Done, sent: 115, total: 115, err: "" };
        assert_eq!(decide_feed(&abort7, Some(7), &done, false, true), FeedDecision::Duplicate);
        // abort ของ id ใหม่ = จบทันที aborted sent 0 (แม้บอร์ดไม่อยู่ / read-only)
        let abort8 = json!({"id": 8, "pulses": 50, "abort": true});
        assert_eq!(
            decide_feed(&abort8, Some(7), &done, true, false),
            FeedDecision::Finish(FeedReport {
                id: 8,
                state: FeedState::Aborted,
                sent: 0,
                total: 50,
                err: ""
            })
        );
        // abort ชนิดผิด → ถือว่า abort (ปลอดภัยไว้ก่อน)
        let weird = json!({"id": 7, "abort": 1});
        assert_eq!(decide_feed(&weird, Some(7), &running, false, true), FeedDecision::AbortRunning);
        // abort null = false
        let null_abort = json!({"id": 7, "abort": null});
        assert_eq!(decide_feed(&null_abort, Some(7), &running, false, true), FeedDecision::Duplicate);
    }

    #[test]
    fn new_id_while_running_is_rejected() {
        let running = FeedReport::running(4, 115);
        let cmd = json!({"id": 5, "pulses": 115, "half_ms": 5});
        assert_eq!(
            decide_feed(&cmd, Some(4), &running, false, true),
            FeedDecision::RejectBusy { id: 5 }
        );
    }

    #[test]
    fn validation_errors_and_order() {
        let idle = FeedReport::idle();
        let e = |id, total, code| FeedDecision::Finish(FeedReport::error(id, total, 0, code));
        assert_eq!(
            decide_feed(&json!({"id": 1, "pulses": 0}), None, &idle, false, true),
            e(1, 0, err::BAD_PULSES)
        );
        assert_eq!(
            decide_feed(&json!({"id": 1, "pulses": 1001}), None, &idle, false, true),
            e(1, 0, err::BAD_PULSES)
        );
        assert_eq!(
            decide_feed(&json!({"id": 1, "pulses": 10, "half_ms": 51}), None, &idle, false, true),
            e(1, 10, err::BAD_HALF_MS)
        );
        assert_eq!(
            decide_feed(&json!({"id": 1, "pulses": 10, "half_ms": -1}), None, &idle, false, true),
            e(1, 10, err::BAD_HALF_MS)
        );
        assert_eq!(
            decide_feed(&json!({"id": 1, "pulses": 10, "half_ms": "5"}), None, &idle, false, true),
            e(1, 10, err::BAD_HALF_MS)
        );
        // ลำดับ: pulses → half_ms → read_only → board
        assert_eq!(
            decide_feed(&json!({"id": 1, "pulses": 10, "half_ms": 5}), None, &idle, true, false),
            e(1, 10, err::READ_ONLY)
        );
        assert_eq!(
            decide_feed(&json!({"id": 1, "pulses": 10, "half_ms": 5}), None, &idle, false, false),
            e(1, 10, err::BOARD_DOWN)
        );
        assert_eq!(
            decide_feed(&json!({"id": 1, "pulses": 10, "half_ms": 99}), None, &idle, true, false),
            e(1, 10, err::BAD_HALF_MS)
        );
    }

    #[test]
    fn malformed_feed_cmd() {
        let idle = FeedReport::idle();
        for bad in [json!(5), json!("x"), json!({"pulses": 5}), json!({"id": 0}), json!({"id": -1}), json!({"id": "3"})] {
            assert!(matches!(
                decide_feed(&bad, None, &idle, false, true),
                FeedDecision::Malformed(_)
            ));
        }
    }

    #[test]
    fn response_line_shape() {
        let r = FeedReport { id: 12, state: FeedState::Running, sent: 57, total: 115, err: "" };
        assert_eq!(
            response_line(0, true, &r),
            "{\"ip0\":0,\"board\":true,\"feed\":{\"id\":12,\"state\":\"running\",\"sent\":57,\"total\":115,\"err\":\"\"}}\n"
        );
        let parsed: Value = serde_json::from_str(response_line(3, false, &FeedReport::idle()).trim()).unwrap();
        assert_eq!(parsed["feed"]["state"], "idle");
        assert_eq!(parsed["board"], false);
        assert_eq!(parsed["ip0"], 3);
    }

    // ---------- framing (9.1) ----------

    #[test]
    fn two_lines_in_one_chunk() {
        let mut lb = LineBuffer::new(1024);
        let lines = lb.push(b"{\"a\":1}\n{\"b\":2}\n");
        assert_eq!(lines, vec![b"{\"a\":1}".to_vec(), b"{\"b\":2}".to_vec()]);
        assert_eq!(lb.pending_len(), 0);
    }

    #[test]
    fn line_split_across_chunks_is_kept() {
        let mut lb = LineBuffer::new(1024);
        assert!(lb.push(b"{\"feed_cmd\":{\"id\":1,").is_empty());
        assert!(lb.push(b"\"abort\":tr").is_empty());
        let lines = lb.push(b"ue}}\r\n{\"x\"");
        assert_eq!(lines, vec![b"{\"feed_cmd\":{\"id\":1,\"abort\":true}}".to_vec()]);
        assert_eq!(lb.pending_len(), 4);
        assert_eq!(lb.push(b":1}\n"), vec![b"{\"x\":1}".to_vec()]);
    }

    #[test]
    fn overlong_line_is_dropped_and_resyncs() {
        let mut lb = LineBuffer::new(8);
        assert!(lb.push(b"0123456789abcdef").is_empty());
        assert_eq!(lb.dropped, 1);
        let lines = lb.push(b"tail\nok\n");
        assert_eq!(lines, vec![b"ok".to_vec()]);
    }
}
