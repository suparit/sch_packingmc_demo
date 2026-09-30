import './globals.css';

export const metadata = {
  title: 'Digital Twin',
  description: 'SMD Reel Taping Machine — Digital Twin: แนะนำเครื่อง carrier tape และหน้าจำลองการทำงานแบบ real-time',
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#05070d',
};

export default function RootLayout({ children }) {
  return (
    <html lang="th">
      <head>
        {/* ฟอนต์จาก Google Fonts — ออฟไลน์ก็ยังใช้ฟอนต์ระบบแทนได้ ไม่พัง */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Noto+Sans+Thai:wght@400;500;600;700&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
