import AnalyticsDashboard from '@/components/analytics/AnalyticsDashboard.jsx';

export const metadata = {
  title: 'Digital Twin · Analytics',
  description: 'วิเคราะห์ประสิทธิภาพการผลิต — เวลาเฉลี่ยต่อสเต็ป เวลารวมต่อรอบ และประวัติการเปลี่ยนสเต็ปล่าสุด',
};

export default function AnalyticsPage() {
  return <AnalyticsDashboard />;
}
