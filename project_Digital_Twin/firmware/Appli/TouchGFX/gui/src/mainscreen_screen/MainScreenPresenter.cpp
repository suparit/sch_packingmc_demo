#include <gui/mainscreen_screen/MainScreenView.hpp>
#include <gui/mainscreen_screen/MainScreenPresenter.hpp>

MainScreenPresenter::MainScreenPresenter(MainScreenView& v)
    : view(v)
{

}

void MainScreenPresenter::activate()
{

}

void MainScreenPresenter::deactivate()
{

}

// 🟢 รับข้อมูลจาก Model แล้วส่งต่อให้ view
void MainScreenPresenter::onWebDataUpdated(int pieces, const char* stateName, int temp,
                                           const char* statusText, const char* alarmText,
                                           int target, int pitch)
{
    view.updateDataFromWeb(pieces, stateName, temp, statusText, alarmText, target, pitch);
}

// 🎥 gateway หยุดรอ operator ที่สเต็ป VISION → ให้ view เด้ง/ปิด overlay ปุ่ม PASS/NG
void MainScreenPresenter::onVisionGateChanged(bool waitingForOperator)
{
    view.updateVisionGate(waitingForOperator);
}