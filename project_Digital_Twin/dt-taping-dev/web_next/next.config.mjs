import os from 'node:os';
import path from 'node:path';

// IPv4 ของเครื่องนี้ทุกวง (Wi-Fi / hotspot / LAN) — คิดใหม่ทุกครั้งที่เปิด dev server
// Next.js 16 บล็อกคำขอ dev (/_next/*) จาก origin ที่ไม่ใช่ localhost เป็นค่าเริ่มต้น
// ถ้าไม่ใส่ เปิดผ่าน http://<IP>:5173 แล้ว JS ฝั่งเบราว์เซอร์ไม่ทำงาน → ไม่มีโมเดล 3D ไม่มีปุ่ม
const lanHosts = Object.values(os.networkInterfaces())
  .flat()
  .filter((n) => n && n.family === 'IPv4' && !n.internal)
  .map((n) => n.address);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // three/drei เป็น ESM ล้วน — ให้ Next แปลงให้ตรงกันทั้ง dev และ build
  transpilePackages: ['three'],
  allowedDevOrigins: lanHosts,
  // โฟลเดอร์โมเดล CAD แบบ path เต็ม — คิดจากที่อยู่ของไฟล์นี้ ไม่ขึ้นกับว่ารัน next จากโฟลเดอร์ไหน
  env: {
    CAD_MODEL_DIR: path.resolve(import.meta.dirname, '../cad/export'),
  },
};

export default nextConfig;
