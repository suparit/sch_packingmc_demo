# test-reports — ผลการทดสอบ


ชื่อไฟล์: `YYYY-MM-DD-<หัวข้อ>.md`

## เทมเพลต

```markdown
# Test Report — <หัวข้อ>
วันที่ / คนรัน / commit

## ขอบเขต
(ทดสอบอะไร **ไม่** ทดสอบอะไร)

## วิธีรัน
(คำสั่งจริงที่ copy ไปรันซ้ำได้)

## ผล
| ข้อทดสอบ | คาดหวัง | ได้จริง | ผ่าน |
|---|---|---|---|

## ข้อที่ไม่ผ่าน
(อาการ + ขั้นตอน reproduce + log จริง)

## ที่ต้องตรวจด้วยตา
(manual checklist — ระบุว่าใครต้องไปกดดู)
```

## กฎ

- **"compile ผ่าน" ไม่ใช่ "ผ่าน"** ต้องรันจริงถึงจะติ๊ก ✅
- แนบ log จริงที่เห็น ไม่ใช่บรรยายว่าน่าจะได้
- เทสต์ที่ fail = ผลงาน รายงานตรง ๆ **ห้ามแก้โค้ดที่กำลังทดสอบเพื่อให้เทสต์ผ่าน**

## Regression baseline

**baseline ปัจจุบัน: [`2026-08-04-regression.md`](2026-08-04-regression.md) — 32/32 ผ่าน**
(TCP 8766 ชุดละ 11 ข้อ + WebSocket 8765 ชุดละ 5 ข้อ × 2 gateway) **ห้ามให้ข้อไหนกลับมา fail**

> ⚠️ ผลรอบ 2026-07-27 ที่ `HANDOFF.md` อ้าง (10 ข้อ) เป็นของ**โฟลเดอร์เก่าก่อนย้าย repo**
> เทสต์ทั้ง 2 ไฟล์ fix path ไว้ตายตัวและ path นั้นไม่มีแล้ว → รันไม่ได้เลยตั้งแต่ย้าย
> แก้เป็น relative path เมื่อ 2026-08-04 รอบนี้จึงเป็นรอบแรกที่รันกับโค้ดใน repo นี้จริง

```bash
cd python_backend/tests
python test_hmi_link.py gateway_fsm.py
python test_hmi_link.py gateway_fsm_upgrad.py
python test_ws.py gateway_fsm.py
python test_ws.py gateway_fsm_upgrad.py
```
> ต้องไม่มี gateway ตัวอื่นรันค้างอยู่ก่อนรัน (พอร์ตชนกัน)

## ยังทดสอบไม่ได้ (พูดตรง ๆ อย่าแกล้งทำเป็นผ่าน)

- **UI บนจอ TouchGFX** — ส่ง input เข้าหน้าต่าง SDL จากสคริปต์ไม่ได้ ต้องให้คนกด ▶ Run Simulator
- **Rust bridge กับบอร์ดจริง** — ต้อง `cargo build` ใหม่ก่อน (พอร์ตเปลี่ยนเป็น 8767)
- **CSV export / CLEAR LOGS ผ่าน UART บนบอร์ดจริง** — ทดสอบผ่านแค่ TCP ตอน dev
