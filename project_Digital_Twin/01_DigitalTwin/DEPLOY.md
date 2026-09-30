# Deployment prerequisites

## Software-only PC

1. ติดตั้ง Python 3.10+ แบบ 64-bit หรือระบุ executable ที่ใช้งานได้
2. สร้าง environment ภายใน project เท่านั้น:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_python.ps1
   ```

   ถ้า `py`/`python` ไม่อยู่บน PATH ให้ระบุ executable โดยตรง เช่น `-Python "C:\path\to\python.exe"` Wrapper ตั้ง UTF-8 และปิด pip progress เฉพาะ process เพื่อรองรับ checkout path ที่มีอักษรไทย โดยไม่เปลี่ยน system settings

3. ตรวจ installation:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 check
   ```

   Acceptance: Python version แสดงผล, `websockets=17.0.1`, `pip check` ผ่าน, GLB ทุกไฟล์ valid และ launcher รายงานสถานะพอร์ต 8765/8766/8767/8000

4. เริ่มและหยุด:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 start
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 status
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 stop
   ```

   หรือดับเบิลคลิก `start_demo.bat` (เรียก `run_demo.ps1 start -OpenBrowser` ให้อัตโนมัติ) และ `stop_demo.bat` เพื่อหยุด — ทั้งสองเป็น thin wrapper รอบสคริปต์เดียวกันด้านบน ไม่ใช่ทางลัดที่แยกออกไปเปิด process เอง

Launcher เก็บ PID และ start-time identity ใน `.digital-twin-run.json` (ignored by Git) และหยุดเฉพาะ process ที่มันเริ่ม หากพอร์ตถูกใช้อยู่จะ fail closed โดยไม่ kill owner — **ห้ามใช้ `taskkill /F /IM python.exe`** เพื่อหยุดระบบ เพราะมันฆ่า python process อื่นที่ไม่เกี่ยวข้องในเครื่องด้วย ใช้ `stop_demo.bat` หรือ `run_demo.ps1 stop` แทนเสมอ

## Rust development prerequisite

ติดตั้ง Rust stable ผ่าน rustup แล้วตรวจ/build:

```powershell
cargo --version
cargo check --locked --manifest-path .\rust_bridge\Cargo.toml
cargo test --locked --manifest-path .\rust_bridge\Cargo.toml
cargo build --locked --manifest-path .\rust_bridge\Cargo.toml
```

Rust runtime ไม่ใช่ software-only smoke test เพราะพยายามเชื่อม STM32 ที่ `192.168.0.100:502` ก่อนเปิด listener 8767

## TouchGFX/STM32 build prerequisite

- TouchGFX 4.26.1 (เครื่องนี้: `C:\TouchGFX\4.26.1`)
- STM32CubeIDE 2.1.1 / GNU Tools for STM32 14.3.1 (เครื่องนี้: `C:\ST\STM32CubeIDE_2.1.1`)
- Ruby global ไม่จำเป็น: TouchGFX มี Ruby 3.0.2 bundled ใน `env\MinGW\msys\1.0\Ruby30-x64\bin`
- Firmware source (`Appli`, `Boot`, `gcc`, ...) อยู่ใน project พี่น้อง `Wab\02_HMI_Firmware\`, **ไม่ได้อยู่ใต้ `01_DigitalTwin\`** — `build_firmware.ps1` อ้างอิงไปที่นั่นโดยอัตโนมัติผ่าน relative path

ใช้ `build_firmware.ps1 firmware` หรือ `simulator` เมื่อ generated assets เป็นปัจจุบัน ใช้ target ลงท้าย `-assets` เฉพาะเมื่อแก้ text/image/video และต้อง regenerate จริง Wrapper ตั้ง PATH ชั่วคราวเฉพาะ process และคืนค่าเดิมเมื่อจบ

Wrapper ไม่มีคำสั่ง flash, programmer หรือเปลี่ยน network settings

## Hardware additions

- Serial HMI: ติดตั้ง ST-LINK VCP driver, ตรวจ COM port และ UART 115200 8-N-1
- Rust/Modbus: ต่อ isolated Ethernet ไป STM32 `192.168.0.100:502`; การกำหนด static IP ของ PC ต้องได้รับอนุมัติแยกต่างหาก
- Flash/program firmware: ต้องได้รับอนุมัติแยกต่างหากและไม่รวมใน run/build scripts นี้

## หมายเหตุสำหรับ PC เครื่องใหม่ (first-time setup)

- เสียบสาย USB บอร์อง (ช่อง ST-LINK) — Windows 10/11 ลงไดรเวอร์ VCP ให้เองตอนเสียบครั้งแรก ถ้า COM port ไม่ขึ้นใน Device Manager ให้ลง STM32CubeProgrammer หรือ STSW-LINK009 หนึ่งครั้ง
- รหัสปลดล็อกจอบอร์ด (HMI keypad): `12345` — แก้ได้เฉพาะใน firmware source แล้วต้อง build/flash ใหม่เท่านั้น
- **ห้ามดับเบิลคลิกเปิด `cad/index1.html` ตรงๆ** โมเดล 3D จะไม่ขึ้น (ดำ) เพราะเบราว์เซอร์บล็อกการโหลดผ่าน `file://` ต้องเข้าผ่าน `http://127.0.0.1:8000/index1.html` ที่ launcher เปิดให้เท่านั้น
- ก๊อป project ไปเครื่องใหม่ไม่จำเป็นต้องเอา `rust_bridge/target/` ไปด้วย (ไฟล์ build เก่า ไม่จำเป็น, `cargo build` จะสร้างใหม่ให้)

ดู startup/shutdown และ acceptance checklist ใน `RUNBOOK.md`
