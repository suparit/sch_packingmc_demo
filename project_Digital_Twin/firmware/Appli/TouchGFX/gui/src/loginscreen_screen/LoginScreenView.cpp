#include <gui/loginscreen_screen/LoginScreenView.hpp>
#include <images/BitmapDatabase.hpp>
#include <touchgfx/Color.hpp>
#include <string.h>

// 🔑 รหัสผ่านที่ถูกต้อง (5 หลัก) — แก้ตรงนี้ที่เดียวถ้าต้องการเปลี่ยนรหัส
static const char CORRECT_PIN[] = "12345";

// สีช่อง * : ยังไม่กด = เทาจาง, กดแล้ว = น้ำเงินเข้ม
static const uint8_t PIN_EMPTY_R = 185, PIN_EMPTY_G = 192, PIN_EMPTY_B = 205;
static const uint8_t PIN_FILL_R  = 22,  PIN_FILL_G  = 51,  PIN_FILL_B  = 127;

LoginScreenView::LoginScreenView()
    : buttonCallback(this, &LoginScreenView::buttonClickHandler)
{

}

void LoginScreenView::setupScreen()
{
    LoginScreenViewBase::setupScreen();

    // 1. ผูก buffer ของเราเองเข้ากับช่อง * ทั้ง 5 (Designer ไม่ได้เปิด wildcard buffer ไว้)
    touchgfx::TextAreaWithOneWildcard* slots[5] = { &textArea1, &textArea2, &textArea3, &textArea4, &textArea5 };
    for (int i = 0; i < 5; i++) {
        pinSlotBuffer[i][0] = '*';
        pinSlotBuffer[i][1] = 0;
        slots[i]->setWildcard(pinSlotBuffer[i]);
    }

    // 2. ผูก action ให้ปุ่มทุกตัวด้วยโค้ด
    BTN0.setAction(buttonCallback);
    BTN1.setAction(buttonCallback);
    BTN2.setAction(buttonCallback);
    BTN3.setAction(buttonCallback);
    BTN4.setAction(buttonCallback);
    BTN5.setAction(buttonCallback);
    BTN6.setAction(buttonCallback);
    BTN7.setAction(buttonCallback);
    BTN8.setAction(buttonCallback);
    BTN9.setAction(buttonCallback);
    CLR.setAction(buttonCallback);
    Delet.setAction(buttonCallback);
    Unlok.setAction(buttonCallback);

    // 3. กล่องเด้งแจ้งเตือนรหัสผิด (ซ่อนไว้ก่อน) วางกลางจอใต้ช่องกรอกรหัส
    pinErrorToast.setBitmap(touchgfx::Bitmap(BITMAP_PINERROR_ID));
    pinErrorToast.setPosition(220, 195, 360, 70);
    pinErrorToast.setScalingAlgorithm(touchgfx::ScalableImage::NEAREST_NEIGHBOR);
    pinErrorToast.setVisible(false);
    add(pinErrorToast);

    // 4. เริ่มต้นด้วยรหัสว่าง
    clearPin();
}

void LoginScreenView::tearDownScreen()
{
    LoginScreenViewBase::tearDownScreen();
}

// ⏱️ ซ่อนกล่องแจ้งเตือนอัตโนมัติหลังแสดงครบ ~2.5 วินาที (150 tick ที่ 60fps)
void LoginScreenView::handleTickEvent()
{
    if (toastCountdown > 0)
    {
        toastCountdown--;
        if (toastCountdown == 0)
        {
            hidePinError();
        }
    }
}

void LoginScreenView::buttonClickHandler(const touchgfx::AbstractButtonContainer& src)
{
    // กดปุ่มไหนก็ตาม ให้เก็บกล่องแจ้งเตือนเก่าก่อน
    hidePinError();

    if      (&src == &BTN0) appendDigit('0');
    else if (&src == &BTN1) appendDigit('1');
    else if (&src == &BTN2) appendDigit('2');
    else if (&src == &BTN3) appendDigit('3');
    else if (&src == &BTN4) appendDigit('4');
    else if (&src == &BTN5) appendDigit('5');
    else if (&src == &BTN6) appendDigit('6');
    else if (&src == &BTN7) appendDigit('7');
    else if (&src == &BTN8) appendDigit('8');
    else if (&src == &BTN9) appendDigit('9');
    else if (&src == &CLR)  clearPin();
    else if (&src == &Delet) backspaceDigit();
    else if (&src == &Unlok)
    {
        // ✅ ครบ 5 หลักและถูกต้อง → เข้าหน้า MainScreen
        if (strlen(pinValue) == 5 && strcmp(pinValue, CORRECT_PIN) == 0)
        {
            application().gotoMainScreenScreenNoTransition();
        }
        else
        {
            // ❌ รหัสผิด (หรือยังกดไม่ครบ 5 ตัว) → เด้ง Incorrect PIN แล้วล้างช่อง
            showPinError();
            clearPin();
        }
    }
}

void LoginScreenView::appendDigit(char digit)
{
    int len = (int)strlen(pinValue);
    if (len < 5)
    {
        pinValue[len] = digit;
        pinValue[len + 1] = '\0';
        refreshPinSlots();
    }
}

void LoginScreenView::backspaceDigit()
{
    int len = (int)strlen(pinValue);
    if (len > 0)
    {
        pinValue[len - 1] = '\0';
        refreshPinSlots();
    }
}

void LoginScreenView::clearPin()
{
    pinValue[0] = '\0';
    refreshPinSlots();
}

// วาดช่อง * ทั้ง 5: หลักที่กดแล้วเป็นสีน้ำเงินเข้ม หลักที่ยังว่างเป็นสีเทาจาง
void LoginScreenView::refreshPinSlots()
{
    int len = (int)strlen(pinValue);
    touchgfx::TextAreaWithOneWildcard* slots[5] = { &textArea1, &textArea2, &textArea3, &textArea4, &textArea5 };
    for (int i = 0; i < 5; i++)
    {
        if (i < len)
        {
            slots[i]->setColor(touchgfx::Color::getColorFromRGB(PIN_FILL_R, PIN_FILL_G, PIN_FILL_B));
        }
        else
        {
            slots[i]->setColor(touchgfx::Color::getColorFromRGB(PIN_EMPTY_R, PIN_EMPTY_G, PIN_EMPTY_B));
        }
        slots[i]->invalidate();
    }
}

void LoginScreenView::showPinError()
{
    pinErrorToast.setVisible(true);
    pinErrorToast.invalidate();
    toastCountdown = 150;
}

void LoginScreenView::hidePinError()
{
    if (pinErrorToast.isVisible())
    {
        pinErrorToast.setVisible(false);
        pinErrorToast.invalidate();
    }
    toastCountdown = 0;
}
