use serde::{Deserialize, Serialize};
use std::{
    env,
    sync::Arc,
    time::{Duration, Instant},
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    sync::Mutex,
    time::{sleep, timeout},
};

const DEFAULT_IO_HOST: &str = "192.168.0.100";
const DEFAULT_IO_PORT: u16 = 502;
const DEFAULT_BRIDGE_ADDR: &str = "127.0.0.1:8767";
const UNIT_ID: u8 = 1;

#[derive(Debug, Deserialize)]
struct GatewayState {
    #[serde(default)]
    op0: u8,
    #[serde(default)]
    op1: u8,
}

#[derive(Serialize)]
struct IoSnapshot {
    ip0: u8,
    ip1: u8,
    op0: u8,
    op1: u8,
    io_connected: bool,
    io_mode: &'static str,
    io_error: String,
}

struct BoardConnection {
    stream: TcpStream,
    last_identity: Instant,
}

type SharedBoard = Arc<Mutex<Option<BoardConnection>>>;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let host = env::var("H7_IP").unwrap_or_else(|_| DEFAULT_IO_HOST.to_string());
    let port = env::var("H7_PORT")
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .unwrap_or(DEFAULT_IO_PORT);
    let bind = env::var("RUST_BRIDGE_ADDR").unwrap_or_else(|_| DEFAULT_BRIDGE_ADDR.to_string());
    let display_outputs = env::var("IO_OUTPUT_MODE")
        .map(|value| value.eq_ignore_ascii_case("display"))
        .unwrap_or(false);
    let board_address = format!("{host}:{port}");

    let mode = if display_outputs {
        "display"
    } else {
        "monitor"
    };
    println!("[Rust I/O] {mode} bridge; board={board_address}; listen={bind}");
    let listener = TcpListener::bind(&bind).await?;
    let board: SharedBoard = Arc::new(Mutex::new(None));

    loop {
        let (client, peer) = listener.accept().await?;
        println!("[Rust I/O] gateway connected: {peer}");
        let board = Arc::clone(&board);
        let board_address = board_address.clone();
        tokio::spawn(async move {
            if let Err(error) = handle_gateway(client, board, &board_address, display_outputs).await
            {
                eprintln!("[Rust I/O] gateway disconnected: {error}");
            }
        });
    }
}

async fn handle_gateway(
    mut client: TcpStream,
    board: SharedBoard,
    board_address: &str,
    display_outputs: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut pending = Vec::<u8>::new();
    let mut read_buffer = [0_u8; 1024];

    loop {
        let count = client.read(&mut read_buffer).await?;
        if count == 0 {
            return Ok(());
        }
        pending.extend_from_slice(&read_buffer[..count]);

        while let Some(newline) = pending.iter().position(|byte| *byte == b'\n') {
            let line: Vec<u8> = pending.drain(..=newline).collect();
            let Ok(state) = serde_json::from_slice::<GatewayState>(&line) else {
                continue;
            };
            let snapshot = read_snapshot(&board, board_address, &state, display_outputs).await;
            client
                .write_all(serde_json::to_string(&snapshot)?.as_bytes())
                .await?;
            client.write_all(b"\n").await?;
        }
    }
}

async fn read_snapshot(
    board: &SharedBoard,
    address: &str,
    state: &GatewayState,
    display_outputs: bool,
) -> IoSnapshot {
    let mut board = board.lock().await;
    if board.is_none() {
        match timeout(Duration::from_secs(1), TcpStream::connect(address)).await {
            Ok(Ok(mut stream)) => {
                println!("[Rust I/O] connected to Modbus board: {address}");
                if let Err(error) = identify_sch_board(&mut stream).await {
                    *board = None;
                    return offline_snapshot(state.op0, state.op1, error.to_string());
                }
                sleep(Duration::from_millis(50)).await;
                *board = Some(BoardConnection {
                    stream,
                    last_identity: Instant::now(),
                });
            }
            Ok(Err(error)) => return offline_snapshot(state.op0, state.op1, error.to_string()),
            Err(_) => {
                return offline_snapshot(state.op0, state.op1, "connection timed out".to_string())
            }
        }
    }

    let result = async {
        let connection = board.as_mut().expect("connection set above");

        // SCH_XPLCV1 uses *IDN? as a connection heartbeat, but measurement
        // (2026-08-10) showed the board enforces a hard ~375ms session
        // timer starting from the last *IDN?, closing the socket regardless
        // of any Modbus traffic in between -- it is NOT a traffic-resetting
        // idle timeout. A once-per-second refresh (the original assumption)
        // is far too infrequent: the socket was dying before that gate ever
        // fired. Re-identify on every poll cycle instead, so the gap between
        // *IDN? and the next read stays ~50ms, safely under the ~375ms cliff.
        // 2026-08-11: confirmed by measurement that a failed identify always
        // happens at a ~374-376ms gap since the last one -- exactly the hard
        // session cliff above, not random flakiness. The failure mode was
        // the gateway's own poll cadence (0.25s sleep + round-trip) landing
        // right on top of that cliff, not this bridge or the board itself.
        let gap = connection.last_identity.elapsed();
        if let Err(error) = identify_sch_board(&mut connection.stream).await {
            eprintln!("[Rust I/O] identify failed after {gap:?} since last one (cliff is ~375ms)");
            return Err(io_stage_error("identify", error));
        }
        connection.last_identity = Instant::now();
        sleep(Duration::from_millis(50)).await;

        let stream = &mut connection.stream;
        let ip0 = read_coil_bank(stream, 0, 1)
            .await
            .map_err(|error| io_stage_error("read IP0", error))?;
        sleep(Duration::from_millis(20)).await;
        let ip1 = read_coil_bank(stream, 8, 2)
            .await
            .map_err(|error| io_stage_error("read IP1", error))?;
        sleep(Duration::from_millis(20)).await;
        let (op0, op1) = if display_outputs {
            // Show the real FSM output image on the board LEDs. The hardware
            // was verified to have no loads connected to these output banks.
            write_coil_bank(stream, 64, state.op0, 3)
                .await
                .map_err(|error| io_stage_error("write OP0", error))?;
            sleep(Duration::from_millis(20)).await;
            write_coil_bank(stream, 72, state.op1, 4)
                .await
                .map_err(|error| io_stage_error("write OP1", error))?;
            sleep(Duration::from_millis(20)).await;
            (state.op0, state.op1)
        } else {
            (state.op0, state.op1)
        };
        Ok::<(u8, u8, u8, u8), std::io::Error>((ip0, ip1, op0, op1))
    }
    .await;

    match result {
        Ok((ip0, ip1, op0, op1)) => IoSnapshot {
            ip0,
            ip1,
            op0,
            op1,
            io_connected: true,
            io_mode: if display_outputs {
                "display"
            } else {
                "monitor"
            },
            io_error: String::new(),
        },
        Err(error) => {
            eprintln!("[Rust I/O] board read failed: {error}");
            *board = None;
            offline_snapshot(state.op0, state.op1, error.to_string())
        }
    }
}

fn io_stage_error(stage: &str, error: std::io::Error) -> std::io::Error {
    std::io::Error::new(error.kind(), format!("{stage}: {error}"))
}

fn offline_snapshot(op0: u8, op1: u8, error: String) -> IoSnapshot {
    IoSnapshot {
        ip0: 0,
        ip1: 0,
        op0,
        op1,
        io_connected: false,
        io_mode: "monitor",
        io_error: error,
    }
}

async fn read_coil_bank(
    stream: &mut TcpStream,
    address: u16,
    transaction: u16,
) -> Result<u8, std::io::Error> {
    let request = [
        (transaction >> 8) as u8,
        transaction as u8,
        0,
        0,
        0,
        6,
        UNIT_ID,
        0x01, // Read Coils
        (address >> 8) as u8,
        address as u8,
        0,
        8,
    ];
    stream.write_all(&request).await?;

    // SCH_XPLCV1 returns the 10-byte bank response used by the project's
    // original diagnostic client. The actual bit image is byte 9.
    let mut response = [0_u8; 10];
    stream.read_exact(&mut response).await?;
    Ok(response[9])
}

async fn write_coil_bank(
    stream: &mut TcpStream,
    address: u16,
    value: u8,
    transaction: u16,
) -> Result<(), std::io::Error> {
    let request = [
        (transaction >> 8) as u8,
        transaction as u8,
        0,
        0,
        0,
        8,
        UNIT_ID,
        0x0F, // Write Multiple Coils
        (address >> 8) as u8,
        address as u8,
        0,
        8,
        1,
        value,
    ];
    stream.write_all(&request).await?;
    let mut response = [0_u8; 12];
    stream.read_exact(&mut response).await?;
    Ok(())
}

async fn identify_sch_board(stream: &mut TcpStream) -> Result<(), std::io::Error> {
    stream.write_all(b"*IDN?\n").await?;
    let mut reply = Vec::with_capacity(128);
    loop {
        let mut byte = [0_u8; 1];
        stream.read_exact(&mut byte).await?;
        if byte[0] == b'\n' {
            break;
        }
        if reply.len() >= 127 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "SCH identification response too long",
            ));
        }
        reply.push(byte[0]);
    }
    let identity = String::from_utf8_lossy(&reply);
    if !identity.contains("SCH_") {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "unexpected board identity",
        ));
    }
    println!("[Rust I/O] board identity: {identity}");
    Ok(())
}
