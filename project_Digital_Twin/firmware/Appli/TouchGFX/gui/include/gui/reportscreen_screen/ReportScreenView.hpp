#ifndef REPORTSCREENVIEW_HPP
#define REPORTSCREENVIEW_HPP

#include <gui_generated/reportscreen_screen/ReportScreenViewBase.hpp>
#include <gui/reportscreen_screen/ReportScreenPresenter.hpp>

class ReportScreenView : public ReportScreenViewBase
{
public:
    ReportScreenView();
    virtual ~ReportScreenView() {}
    virtual void setupScreen();
    virtual void tearDownScreen();

    // 🟢 Real-time: ดึงข้อมูลรายงานใหม่อัตโนมัติทุกๆ 2 วินาที
    virtual void handleTickEvent();

    // 🟢 Event Handlers ปุ่มกด (override virtual function ที่ Designer generate ไว้ใน ViewBase
    //    ชื่อต้องตรงกับ Interaction ใน Designer: btnRefreshClicked / btnClearClicked / btnSaveClicked)
    virtual void btnRefreshClicked();
    virtual void btnClearClicked();
    virtual void btnSaveClicked();

    // 🟢 ฟังก์ชันอัปเดตข้อมูลบน UI
    void updateReportData(int total, int ok, int ng, float yieldRate);
    void updateAlarmLogText(const char* logText);

protected:
    int tickCounter = 0;
};

#endif // REPORTSCREENVIEW_HPP
