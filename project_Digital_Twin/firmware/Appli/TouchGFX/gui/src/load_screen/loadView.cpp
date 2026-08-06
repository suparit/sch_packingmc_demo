#include <gui/load_screen/loadView.hpp>
#include <stdio.h>

// หน้าจอ TouchGFX เดินที่ 60 fps → 5 วินาที = 300 tick
// (อ้างอิงเดียวกับ toast แจ้งรหัสผิดใน LoginScreenView ที่ใช้ 150 tick = 2.5 วินาที)
static const int LOAD_DURATION_TICKS = 300;

loadView::loadView()
{

}

void loadView::setupScreen()
{
    loadViewBase::setupScreen();

    // Designer เรียก resizeToCurrentText() ทำให้กล่องกว้างเท่าข้อความตัวอย่าง "0 %"
    // พอขึ้น "100 %" จะโดนตัด เลยขยายไปทางขวา (ข้อความชิดซ้าย ขอบซ้ายคงที่)
    textArea1.setPosition(textArea1.getX(), textArea1.getY(),
                          textArea1.getWidth() + 60, textArea1.getHeight());

    // เริ่มนับใหม่ทุกครั้งที่เข้าหน้านี้ (Designer ตั้ง setValue(60) ไว้เป็นภาพตัวอย่าง)
    tickCounter = 0;
    lastPercent = -1;
    showPercent(0);
}

void loadView::tearDownScreen()
{
    loadViewBase::tearDownScreen();
}

// ⏱️ เดินแถบโหลดทีละ tick — ครบ 300 tick (5 วินาที) แล้วเข้าหน้า Login
void loadView::handleTickEvent()
{
    if (tickCounter >= LOAD_DURATION_TICKS)
    {
        return;   // โหลดจบแล้ว รอ framework สลับหน้าจอ
    }

    tickCounter++;

    int percent = (tickCounter * 100) / LOAD_DURATION_TICKS;
    if (percent > 100) percent = 100;
    showPercent(percent);

    if (tickCounter >= LOAD_DURATION_TICKS)
    {
        // gotoXxx ของ TouchGFX เป็นแบบ deferred (ตั้ง pendingScreenTransitionCallback)
        // framework จะสลับหน้าให้ตอนจบ tick จึงเรียกจากตรงนี้ได้ปลอดภัย
        //
        // ใช้ BlockTransition ไม่ใช่ NoTransition เพราะ Designer generate เมธอด goto
        // ให้เฉพาะ transition ที่มี Interaction ใช้งานจริงเท่านั้น — ทางเข้า LoginScreen
        // ที่มีอยู่คือปุ่ม Yes_logout บนหน้า logout ซึ่งตั้งเป็น ScreenTransitionBlock
        application().gotoLoginScreenScreenBlockTransition();
    }
}

// อัปเดตทั้งตัวเลขและแถบพร้อมกัน — วาดใหม่เฉพาะตอนเปอร์เซ็นต์เปลี่ยนจริง
void loadView::showPercent(int percent)
{
    if (percent == lastPercent)
    {
        return;
    }
    lastPercent = percent;

    boxProgress1.setValue(percent);   // setValue invalidate ให้เองอยู่แล้ว

    // Unicode::snprintf ไม่รองรับ %% จึงจัดข้อความด้วย snprintf ปกติก่อนแล้วแปลงเป็น Unicode
    char tmp[16];
    snprintf(tmp, sizeof(tmp), "%d %%", percent);
    Unicode::fromUTF8((const uint8_t*)tmp, textArea1Buffer, TEXTAREA1_SIZE);
    textArea1.invalidate();
}
