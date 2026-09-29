import fs from 'node:fs';
import path from 'node:path';
import { Readable } from 'node:stream';

// เสิร์ฟ .glb จาก cad/export/ ตรง ๆ ที่ /models/<ชื่อไฟล์> — ไม่ก๊อปโมเดล 26 MB มาไว้ซ้ำใน public/
// path มาจาก next.config.mjs (CAD_MODEL_DIR) — ไม่ใช้ process.cwd() เพราะเปลี่ยนตามโฟลเดอร์ที่รันคำสั่ง
export const runtime = 'nodejs';

const MODEL_DIR = path.resolve(process.env.CAD_MODEL_DIR);

export async function GET(_req, { params }) {
  const { name } = await params;
  const file = path.resolve(MODEL_DIR, name);
  // กัน path traversal (../) — อนุญาตเฉพาะไฟล์ .glb ที่อยู่ในโฟลเดอร์นี้จริง
  if (!file.startsWith(MODEL_DIR + path.sep) || !file.endsWith('.glb') || !fs.existsSync(file)) {
    return new Response('model not found', { status: 404 });
  }
  const { size } = fs.statSync(file);
  return new Response(Readable.toWeb(fs.createReadStream(file)), {
    headers: {
      'Content-Type': 'model/gltf-binary',
      'Content-Length': String(size),
      'Cache-Control': 'public, max-age=3600',
    },
  });
}
