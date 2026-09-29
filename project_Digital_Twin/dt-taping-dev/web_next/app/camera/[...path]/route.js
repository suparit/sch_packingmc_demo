// ตัวกลางไปแอปกล้อง HIKROBOT (03_Vision/ocr/app_vision_ocr.py · หน้า :5000) — 28 ก.ย. 2569
// เว็บดึงผ่าน /camera/... ของตัวเอง ไม่ยิง 127.0.0.1:5000 ตรง ๆ จากเบราว์เซอร์ เพราะ
//   · เปิดเว็บจากเครื่องอื่น / มือถือในวงเดียวกัน 127.0.0.1 จะชี้ไปที่เครื่องผู้ดูเอง ไม่ใช่เครื่องที่ต่อกล้อง
//   · แอปกล้องไม่ส่ง header CORS — fetch ข้าม origin จากหน้า :5173 จะถูกบล็อก
// เปิดเฉพาะเส้นที่การ์ดกล้องใช้ (GET สถานะ + ภาพ 2 ภาพ · POST ตั้งตำแหน่ง index) ที่เหลือ 404
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const CAMERA_URL = process.env.CAMERA_URL || 'http://127.0.0.1:5000';
const GET_PATHS = new Set(['api/status', 'roi.jpg', 'carrier.jpg', 'decision.jpg']); // decision.jpg = ภาพนิ่งที่ใช้ตัดสินล่าสุด
const POST_PATHS = new Set(['api/set_index']);
const TIMEOUT_MS = 2500;

async function forward(req, params, allowed, method) {
  const { path } = await params;
  const p = (path || []).join('/');
  if (!allowed.has(p)) return new Response('not found', { status: 404 });
  try {
    // ส่ง query ต่อด้วย — set_index?y=0..1 = แถวที่คลิกบนภาพ (28 ก.ย. 2569)
    const r = await fetch(`${CAMERA_URL}/${p}${new URL(req.url).search}`, { method, cache: 'no-store', signal: AbortSignal.timeout(TIMEOUT_MS) });
    return new Response(r.body, {
      status: r.status,
      headers: { 'Content-Type': r.headers.get('content-type') || 'application/octet-stream', 'Cache-Control': 'no-store' },
    });
  } catch {
    // แอปกล้องไม่ได้เปิด / ปิดไปแล้ว — การ์ดแสดง "กล้องไม่ได้เปิด"
    return Response.json({ offline: true }, { status: 503, headers: { 'Cache-Control': 'no-store' } });
  }
}

export function GET(req, ctx) {
  return forward(req, ctx.params, GET_PATHS, 'GET');
}

export function POST(req, ctx) {
  return forward(req, ctx.params, POST_PATHS, 'POST');
}
