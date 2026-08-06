# firmware — โปรเจกต์ TouchGFX / STM32H7S78-DK

> ตรวจกับของจริงล่าสุด: **2026-08-03** (ทุกตัวเลขในหน้านี้วัดจาก `ls` จริง ไม่ใช่ประมาณ)

---

## 1. โฟลเดอร์นี้คืออะไร — "กระจกเงา" ไม่ใช่โปรเจกต์ที่ build ได้

`firmware/` เก็บ **เฉพาะไฟล์ที่เราเขียนเอง** ที่คัดออกมาจากโปรเจกต์ CubeIDE/TouchGFX ตัวเต็ม
เอาไว้ให้ git เห็น diff ของโค้ดเราโดยไม่ต้องแบกของ ST เข้ามาด้วย

**โฟลเดอร์นี้ build ไม่ได้** เพราะไม่มี `generated/`, `Drivers/`, `Middlewares/ST/touchgfx/`
ถ้าจะ build ต้องไป build ที่โปรเจกต์ตัวจริง (ดูข้อ 5)

**โปรเจกต์ตัวจริง (ยังอยู่นอก repo):**
```
E:\work-TE-Project\project_Digital_Twin\Digital-Twin-Taping Machine\NOXCORE\
```
> ⚠️ path มี **เว้นวรรค** ที่ `Digital-Twin-Taping Machine` — ต้องใส่ quote ทุกครั้ง
> และมันทำให้ build บางวิธีพังด้วย (ดูข้อ 5.3)

---

## 2. ทิศทางการ sync — **NOXCORE คือต้นทางความจริง (source of truth)**

```
   แก้ที่นี่                     copy ทางเดียว                เก็บประวัติที่นี่
┌──────────────────┐        ─────────────────►        ┌──────────────────┐
│  NOXCORE\        │                                  │  repo firmware\  │
│  (CubeIDE +      │        ◄── ห้ามย้อนทาง ──         │  (mirror)        │
│   TouchGFX       │            ยกเว้นกู้เครื่องใหม่        │                  │
│   Designer)      │                                  │                  │
└──────────────────┘                                  └──────────────────┘
```

**ทำไม NOXCORE ต้องเป็นต้นทาง**
1. **TouchGFX Designer เขียนทับ** — กด Save/Generate ทีไร Designer เขียน `NOXCORE.touchgfx`
   กับทั้งโฟลเดอร์ `generated/` ใหม่ทุกครั้ง ที่ repo ไม่มีโครงพวกนี้ Designer เปิดไม่ได้
2. **CubeMX เขียน `.ioc` ที่ NOXCORE** — และ regenerate `Appli/Core/` ตาม
3. **compile ได้ที่ NOXCORE ที่เดียว** — makefile ของ simulator อ้าง `generated/`, `assets/`,
   `config/` ซึ่งไม่ได้เอาเข้า repo

**ความเสี่ยงของทิศทางนี้ (ต้องรู้ไว้)**
| ความเสี่ยง | ผลที่เกิด | วิธีกัน |
|---|---|---|
| มีคนแก้ไฟล์ในสำเนาที่ `firmware/` | รอบ sync ถัดไปทับหาย **เงียบ ๆ** ไม่มี error | **ห้ามแก้ไฟล์ใน `firmware/`** ให้แก้ที่ NOXCORE เสมอ แล้ว sync ลงมา |
| ลืม sync ก่อน commit | git history ไม่ตรงกับโค้ดที่ใช้ build จริง | รัน "เช็ค drift" (ข้อ 4) ก่อน commit ทุกครั้ง |
| Designer regenerate แล้วชื่อ widget เปลี่ยน | โค้ดใน `gui/src/` ที่ sync ไปแล้วอ้างของเก่า | build ที่ NOXCORE ให้ผ่านก่อน แล้วค่อย sync |
| NOXCORE อยู่นอก repo → เครื่องพังคือหาย | เสีย `generated/`, `assets/` | `assets/` ควรเอาเข้า repo (ดูข้อ 3 ตาราง "ควรเพิ่ม") |

> ทิศทางย้อนกลับ (repo → NOXCORE) ใช้กรณีเดียว: **ตั้งเครื่องใหม่ / กู้ไฟล์ที่เผลอลบ**
> ต้องมีโปรเจกต์ NOXCORE ครบก่อนแล้วค่อยเอาไฟล์เราไปทับ

---

## 3. รายการที่เอาเข้า repo — ตรวจกับของจริงแล้ว

### 3.1 อยู่ใน repo แล้วตอนนี้ (commit `795aa86`)

| ไฟล์/โฟลเดอร์ ใน repo | ที่มาจริงใน NOXCORE | จำนวน | ขนาด |
|---|---|---|---|
| `Appli/TouchGFX/gui/src/**` | เหมือนกัน | 16 `.cpp` | 58.6 KB |
| `Appli/TouchGFX/gui/include/**` | เหมือนกัน | 18 `.hpp` | 25.1 KB |
| `Appli/Core/Src/uart_link.c` | เหมือนกัน | 1 | 5.1 KB |
| `Appli/Core/Inc/uart_link.h` | เหมือนกัน | 1 | 1.4 KB |
| `STM32H7S78-DK.ioc` | NOXCORE root | 1 | 37.7 KB |
| `backup_STM32H7S78-DK.ioc` | NOXCORE root | 1 | 37.7 KB |
| `Appli/TouchGFX/NOXCORE.touchgfx` | เหมือนกัน | 1 | 93.9 KB |
| `Appli/TouchGFX/ApplicationTemplate.touchgfx.part` | เหมือนกัน | 1 | 0.8 KB |
| **รวม** | | **40 ไฟล์** | **260.3 KB ≈ 0.25 MB** |

ทั้ง 40 ไฟล์ **byte-identical** กับ NOXCORE (ตรวจด้วย MD5 เมื่อ 2026-08-03) ไม่มี drift

### 3.2 จุดที่ README ฉบับก่อนเขียนผิด — แก้แล้ว

| README เก่าเขียนว่า | ของจริง |
|---|---|
| `Core/Src/uart_link.c`, `Core/Inc/uart_link.h` | ❌ ไม่มี `Core/` ที่ NOXCORE root — ที่ถูกคือ **`Appli/Core/Src/`** และ **`Appli/Core/Inc/`** |
| `*.ioc` (เหมือนมีไฟล์เดียว) | มี **2 ไฟล์** ที่ NOXCORE root และ **เนื้อในไม่เหมือนกัน** (MD5 ต่างกัน) `backup_*.ioc` คือ auto-backup ของ CubeMX → ปกติไม่ควร commit |
| `Appli/TouchGFX/*.touchgfx` | glob นี้ **ไม่จับ** `ApplicationTemplate.touchgfx.part` ซึ่งโปรเจกต์ต้องใช้ (ตอนนี้อยู่ใน repo แล้ว แต่ README เก่าไม่ได้ระบุ) |
| "ไม่เอา `generated/` เพราะ `.gitignore` แล้ว" | ❌ `.gitignore` ปัจจุบัน **ไม่ได้ ignore** `firmware/**/generated/` — ignore แค่ `firmware/**/generated/simulator/gcc/build/` ดูข้อ 6 |

### 3.3 ควรเพิ่มเข้ามาอีก (ยังไม่ได้เอาเข้า — รออนุมัติ)

| ไฟล์ | ทำไมถึงจำเป็น | ขนาด |
|---|---|---|
| `Appli/Core/Inc/stm32h7rsxx_hal_conf.h` | แก้เองเมื่อ 2026-07-24 เปิด `HAL_UART_MODULE_ENABLED` **ถ้าไม่มีไฟล์นี้ build ลงบอร์ดพัง** (uart_link.c เรียก HAL_UART ไม่ได้) | 18.0 KB |
| `Appli/TouchGFX/simulator/gcc/Makefile` | แก้เองเมื่อ 2026-07-22 ใส่ `ADDITIONAL_LIBRARIES := ws2_32` ให้ socket link ผ่าน | 1.1 KB |
| `Appli/TouchGFX/simulator/main.cpp` + `simulator/msvs/**` | entry point ของ simulator | 75.6 KB |
| `Appli/TouchGFX/config/**` (`gcc/app.mk`, `msvs/Application.props`) | makefile อ้างถึงตรง ๆ | 1.2 KB |
| `Appli/TouchGFX/assets/**` (images/fonts/texts) | **ไม่มีอันนี้ regenerate จาก `.touchgfx` ไม่ได้** — `.touchgfx` เก็บแค่ชื่อรูป ไม่ได้เก็บรูป | 5.66 MB |
| `Appli/TouchGFX/target/**` | ชั้น port ลงบอร์ด (`TouchGFXHAL.cpp`, `STM32TouchController.cpp`) ตอนนี้ยังเป็นของ ST ยังไม่ได้แก้ แต่ถ้าวันหนึ่งแก้ จะโดน `.gitignore` บล็อกเงียบ ๆ (ดูข้อ 6) | 18 ไฟล์ รวม 149 KB |
| `Appli/TouchGFX/application.config`, `target.config` | path ของ Designer/toolchain | 1.1 KB |

**ถ้าเอาชุดนี้เข้าทั้งหมด:** 84 ไฟล์ / **6.13 MB** (จาก 0.25 MB) — ที่บวมคือ `assets/` อย่างเดียว 5.66 MB
เป็นรูป PNG ของหน้าจอ ใหญ่สุด `HOME.png` 1.1 MB

### 3.4 ไม่เอาเข้าแน่นอน (วัดขนาดแล้ว)

| โฟลเดอร์ (ที่ NOXCORE) | ขนาดจริง | เหตุผล |
|---|---|---|
| `Boot/` | **449.9 MB** (`Boot/TouchGFX/build/bin/intflash.elf` ไฟล์เดียว 448.3 MB) | build artifact ล้วน |
| `Appli/TouchGFX/build/` | 262.5 MB | ผลลัพธ์การ build |
| `Appli/TouchGFX/generated/` | **142.3 MB** | Designer สร้างใหม่ได้ — ตัวใหญ่คือ `generated/images/src/image_*.cpp` ไฟล์ละ **19.3 MB** × 6 ไฟล์ |
| `Drivers/` | 12.7 MB | ST HAL |
| `Middlewares/` | 1.9 MB | ST middleware |
| `EWARM/`, `MDK-ARM/`, `STM32CubeIDE/`, `gcc/` | 1.07 MB รวม | ไฟล์ IDE เฉพาะเครื่อง |

---

## 4. ขั้นตอน sync จริง (คัดลอกไปใช้ได้เลย)

รันใน **PowerShell** ที่ไหนก็ได้

### 4.1 เช็ค drift ก่อน — repo ต่างจาก NOXCORE ตรงไหนบ้าง

```powershell
$repo = "E:\work-TE-Project\project_Digital_Twin\dt-taping-dev\firmware"
$nox  = "E:\work-TE-Project\project_Digital_Twin\Digital-Twin-Taping Machine\NOXCORE"
Get-ChildItem -LiteralPath $repo -Recurse -File |
  Where-Object { $_.Name -ne 'README.md' } | ForEach-Object {
    $rel = $_.FullName.Substring($repo.Length + 1)
    $src = Join-Path $nox $rel
    if (-not (Test-Path -LiteralPath $src)) { "NO-SRC : $rel" }
    elseif ((Get-FileHash -LiteralPath $_.FullName -Algorithm MD5).Hash -ne
            (Get-FileHash -LiteralPath $src        -Algorithm MD5).Hash) { "DIFFERS: $rel" }
  }
```
ไม่ printออกมาเลย = ตรงกันหมด

### 4.2 ดึงของใหม่จาก NOXCORE ลง repo (ทิศทางปกติ)

```powershell
$repo = "E:\work-TE-Project\project_Digital_Twin\dt-taping-dev\firmware"
$nox  = "E:\work-TE-Project\project_Digital_Twin\Digital-Twin-Taping Machine\NOXCORE"

# โฟลเดอร์ทั้งก้อน
robocopy "$nox\Appli\TouchGFX\gui" "$repo\Appli\TouchGFX\gui" /MIR /NFL /NDL /NJH /NJS

# ไฟล์เดี่ยว
$files = @(
  "Appli\Core\Src\uart_link.c",
  "Appli\Core\Inc\uart_link.h",
  "Appli\TouchGFX\NOXCORE.touchgfx",
  "Appli\TouchGFX\ApplicationTemplate.touchgfx.part",
  "STM32H7S78-DK.ioc"
)
foreach ($f in $files) {
  $dst = Join-Path $repo $f
  New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
  Copy-Item -LiteralPath (Join-Path $nox $f) -Destination $dst -Force
}
```
> `robocopy /MIR` **ลบไฟล์ปลายทางที่ต้นทางไม่มีแล้วด้วย** — ตั้งใจให้เป็นแบบนั้น
> เพื่อจับกรณีลบหน้าจอทิ้งใน Designer จะได้หายไปจาก repo ด้วย

### 4.3 ลำดับงานที่ถูกต้อง

1. แก้โค้ด **ที่ NOXCORE** (ผ่าน CubeIDE / Designer / editor)
2. build simulator ที่ NOXCORE ให้ผ่าน (ข้อ 5)
3. รัน 4.2 ดึงลง repo
4. รัน 4.1 ยืนยันว่าไม่เหลือ drift
5. commit เมื่อทดสอบผ่านแล้ว

---

## 5. build simulator จาก command line

### 5.1 คำสั่งเต็ม (ใช้ **Bash / Git Bash** ไม่ใช่ PowerShell — เป็น MinGW/msys)

```bash
export PATH="/e/TouchGFX/4.26.1/env/MinGW/bin:/e/TouchGFX/4.26.1/env/MinGW/msys/1.0/bin:$PATH"
export ADDITIONAL_LIBRARIES=ws2_32
cd "/e/work-TE-Project/project_Digital_Twin/Digital-Twin-Taping Machine/NOXCORE/Appli/TouchGFX"
make -r -f generated/simulator/gcc/Makefile -s build_executable
```
ผลลัพธ์ออกที่:
```
E:\work-TE-Project\project_Digital_Twin\Digital-Twin-Taping Machine\NOXCORE\Appli\TouchGFX\build\bin\simulator.exe
```

### 5.2 กฎที่พลาดแล้วเสียเวลา

- ใช้ target **`build_executable`** ไม่ใช่ `all` — `all` เรียกขั้น assets ที่ต้องใช้ ruby
  ซึ่งไม่ได้ติดตั้งบนเครื่องนี้ (Designer มี ruby ในตัว) ข้ามได้เพราะ assets generate ไว้แล้ว
  **จะต้องเปิด Designer เฉพาะตอนแก้ texts/images**
- ต้อง `export ADDITIONAL_LIBRARIES=ws2_32` เอง เพราะ flag `-r` ตัด export จาก Makefile แม่
  ไม่งั้น link ไม่ผ่าน (`undefined reference _imp__socket`)
- **ปิด `simulator.exe` ก่อน build** ไม่งั้น link ไม่ได้ (`Permission denied`)
  เช็คด้วย `Get-Process simulator -ErrorAction SilentlyContinue`

### 5.3 ⚠️ กับดักใหม่ — เว้นวรรคใน path ทำให้ Makefile ตัวห่อพัง

`Appli/TouchGFX/simulator/gcc/Makefile` (ตัวที่ TouchGFX Designer เรียกตอนกด ▶) มีบรรทัดนี้:
```make
ifneq ($(words $(makefile_path))$(words $(MAKEFILE_LIST)),11)
all clean assets:
$(error Spaces not allowed in path)
```
เพราะ path มีคำว่า `Digital-Twin-Taping Machine` มันเลยตายทันที — ยืนยันแล้ว 2026-08-03:
```
$ make -f simulator/gcc/Makefile -n all
simulator/gcc/Makefile:20: *** Spaces not allowed in path.  Stop.
```
**ทางออกที่ใช้อยู่:** ข้ามตัวห่อ ยิงเข้า `generated/simulator/gcc/Makefile` ตรง ๆ (คำสั่งข้อ 5.1)
ตัวที่ generate ไม่มี guard นี้ และ build ผ่านทั้งที่ path มีเว้นวรรค

**อาการที่ user เจอจริง 2026-08-04** — กด Generate Code ใน Designer:
```
Generate        -> Done
Generate Assets -> make -f simulator/gcc/Makefile assets -j8
                   simulator/gcc/Makefile:20: *** Spaces not allowed in path.  Stop.
                -> Failed
Failed
```
ทั้ง pipeline ขึ้น `Failed` และ **`generated/` ไม่ถูกเขียนทับเลย** (ยังเป็นของ 27 ก.ค.)
Designer เขียนแค่ `NOXCORE.touchgfx` ไฟล์เดียว

### 5.3.1 ทางที่ลองแล้ว **ไม่ได้ผล** — อย่าเสียเวลาซ้ำ

**Junction / symlink ชื่อไม่มีเว้นวรรคชี้เข้าโปรเจกต์ → ใช้ไม่ได้**
```bash
cmd /c mklink /J E:\NOXCORE_build "E:\...\Digital-Twin-Taping Machine\NOXCORE"
cd /e/NOXCORE_build/Appli/TouchGFX && make -f simulator/gcc/Makefile -n assets
# simulator/gcc/Makefile:20: *** Spaces not allowed in path.  Stop.   <- ยังตายเหมือนเดิม
```
เพราะบรรทัด 11 ของ Makefile ใช้ `$(abspath ...)` ซึ่ง**คลี่ junction กลับเป็น path จริง**
ที่มีเว้นวรรค แล้ว `$(words ...)` ที่บรรทัด 18 นับได้ > 1 คำ → เข้าเงื่อนไข error

**ปิด guard ทิ้ง → ไม่ควรทำ** guard มีเหตุผลจริง GNU make จัดการ path ที่มีเว้นวรรคไม่ได้
ปิดไปก็จะไปพังขั้นถัดไปแทน และ Designer regenerate ทับได้ทุกเมื่อ

### 5.3.2 ทางแก้จริงทางเดียว — ย้ายโปรเจกต์ไป path ไม่มีเว้นวรรค

**ยังไม่ได้ทำ** — user เลือก "ส่งงานก่อน ค่อยย้าย" (2026-08-04)

ย้ายภายในไดรฟ์ `E:` เดียวกัน = **rename ระดับ filesystem เสร็จในไม่กี่วินาที ไม่ใช่ copy**
(วัดแล้ว 1,740 ไฟล์ / 0.98 GB)

```powershell
# 1) ปิด TouchGFX Designer + CubeIDE + simulator.exe ให้หมดก่อน ไม่งั้นย้ายไม่ได้
Get-Process TouchGFXDesigner*,simulator,stm32* -ErrorAction SilentlyContinue

# 2) ย้าย
Move-Item -LiteralPath "E:\work-TE-Project\project_Digital_Twin\Digital-Twin-Taping Machine\NOXCORE" `
          -Destination "E:\work-TE-Project\NOXCORE"

# 3) เปิด Designer จาก path ใหม่ แล้วกด Generate Code ซ้ำ (คราวนี้ผ่าน)
```
**หลังย้ายต้องแก้ path ที่อ้างถึงใน:** ข้อ 1, 4.1, 4.2, 5.1 ของไฟล์นี้ · `docs/specs/port_map.md` ·
กติกาของ repo (ต้องให้ผู้ดูแล repo แก้) · worklog เก่าปล่อยไว้ได้ เป็นบันทึกตามจริง

### 5.3.3 เช็คก่อนตกใจ — Designer re-save เปล่า ๆ ไม่ใช่ของค้าง

`generated/` เก่ากว่า `.touchgfx` **ไม่ได้แปลว่ามีของค้างรอ generate เสมอ** Designer เขียน
`.touchgfx` ใหม่ทุกครั้งที่ Save แม้ไม่ได้แก้อะไร (และเปลี่ยน LF เป็น CRLF ด้วย)

เทียบเนื้อหาจริงก่อน — **ต้องใส่ `--strip-trailing-cr` ไม่งั้นเห็นต่างทั้งไฟล์**
```bash
cd /e/work-TE-Project/project_Digital_Twin/dt-taping-dev
git show HEAD:firmware/Appli/TouchGFX/NOXCORE.touchgfx > /tmp/repo.json
diff --strip-trailing-cr /tmp/repo.json \
  "/e/work-TE-Project/project_Digital_Twin/Digital-Twin-Taping Machine/NOXCORE/Appli/TouchGFX/NOXCORE.touchgfx"
```
ผลจริง 2026-08-04: **ต่าง 0 บรรทัด** ทั้งที่ `.touchgfx` มี timestamp ใหม่กว่า `generated/` 8 วัน
→ การเซฟรอบ 31 ก.ค. และ 4 ส.ค. เป็น re-save เปล่า `generated/` ของ 27 ก.ค. **ถูกต้องแล้ว**
และ simulator ที่ build จากมันครบสมบูรณ์ ไม่ได้ขาดอะไร

> ผลข้างเคียงอีกข้อ: **ปุ่ม ▶ Run Simulator ใน Designer อาจกดไม่ติดจาก path นี้**
> ถ้าเจอ ให้ build ด้วย 5.1 แล้วดับเบิลคลิก `build\bin\simulator.exe` เอง

---

## 6. `.gitignore` — ที่ยังขาด (ต้องให้เซสชัน/user แก้)

ตรวจด้วย `git check-ignore -v` เมื่อ 2026-08-03 เจอ 2 ปัญหา

### 6.1 รูรั่ว — ของหนักยัง commit ได้อยู่

`git check-ignore` บอกว่า path พวกนี้ **ยัง trackable**:
`firmware/Appli/TouchGFX/generated/**` (142 MB), `firmware/Drivers/**` (12.7 MB),
`firmware/Middlewares/**`, `firmware/.mxproject`, `firmware/backup_*.ioc`

บรรทัดที่เสนอให้เพิ่ม:
```gitignore
# ===== TouchGFX / STM32 — ของที่ generate ใหม่ได้ ห้ามเข้า repo =====
firmware/**/generated/
firmware/Drivers/
firmware/Middlewares/
firmware/Boot/
firmware/EWARM/
firmware/MDK-ARM/
firmware/STM32CubeIDE/
firmware/gcc/components.mk
firmware/.mxproject
firmware/**/backup_*.ioc
firmware/**/*_backup.touchgfx
*.bin
*.hex
*.lst
*.su
*.d
```

### 6.2 false positive — กฎของ Rust ไปบังโค้ดฝั่งบอร์ด

```
$ git check-ignore -v firmware/Appli/TouchGFX/target/TouchGFXHAL.cpp
.gitignore:19:target/   firmware/Appli/TouchGFX/target/TouchGFXHAL.cpp
```
บรรทัด `target/` (ตั้งใจไว้ให้ Rust) เป็น pattern ไม่ผูก path → บัง
`firmware/Appli/TouchGFX/target/` ซึ่งเป็น **ชั้น port ลงบอร์ดจริง** ไปด้วย
ตอนนี้ยังไม่เจ็บเพราะไฟล์ในนั้นยังเป็นของ ST ล้วน แต่ถ้าวันไหนแก้ `TouchGFXHAL.cpp`
แล้ว commit มันจะหายเงียบ ๆ

บรรทัดที่เสนอ — แก้ให้ผูก path แล้วเปิดทางกลับให้ TouchGFX:
```gitignore
rust_bridge/target/
!firmware/Appli/TouchGFX/target/
```

---

## 7. ไฟล์หลักที่ต้องรู้จัก

| ไฟล์ (ใต้ `firmware/`) | ทำอะไร |
|---|---|
| `Appli/TouchGFX/gui/src/model/Model.cpp` | ประตูข้อมูลทั้งหมด — Simulator ต่อ **TCP 127.0.0.1:8766**, บอร์ดจริงเรียก `uart_link.h` |
| `Appli/TouchGFX/gui/src/load_screen/loadView.cpp` | หน้า splash (แถบโหลด 0-100% ใน 5 วิ) |
| `Appli/TouchGFX/gui/src/mainscreen_screen/MainScreenView.cpp` | Start/Stop/Reset + keypad + overlay PASS/NG ของสเต็ป VISION (ไฟล์ใหญ่สุด 17.2 KB) |
| `Appli/TouchGFX/gui/src/settingsscreen_screen/SettingsScreenView.cpp` | keypad 10 ช่อง + ปุ่ม SAVE PARAMS |
| `Appli/TouchGFX/gui/src/reportscreen_screen/ReportScreenView.cpp` | หน้ารายงาน + SQL ledger real-time |
| `Appli/TouchGFX/gui/src/loginscreen_screen/LoginScreenView.cpp` | Login PIN 5 หลัก |
| `Appli/Core/Src/uart_link.c` | UART4 (TX=PD1, RX=PD0 → ST-LINK VCP) — **self-contained**: ทำ MSP init + `UART4_IRQHandler` เองในไฟล์เดียว ไม่ต้องแตะ `main.c` |

**หน้าจอในโปรเจกต์ 7 หน้า** (จาก `NOXCORE.touchgfx`, TouchGFX 4.26.1):
`load`, `LoginScreen`, `MainScreen`, `ReportScreen`, `SettingsScreen`, `Maintenence`, `logout`

---

## 8. กับดัก TouchGFX

สรุปกับดักที่เคยเจอ:
`bind()` ต้องเติมเองใน Presenter / `goto...NoTransition()` หายเพราะไม่มี Interaction /
`resizeToCurrentText()` ล็อกความกว้างกล่อง / `Unicode::snprintf` ไม่รับ `%%` /
`KP_X` ชนกับ `wincrypt.h` / `SOCKET sock` ต้องอยู่ใน `#if WIN32`
