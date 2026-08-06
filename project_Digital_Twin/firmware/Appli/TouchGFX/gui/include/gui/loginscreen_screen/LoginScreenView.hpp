#ifndef LOGINSCREENVIEW_HPP
#define LOGINSCREENVIEW_HPP

#include <gui_generated/loginscreen_screen/LoginScreenViewBase.hpp>
#include <gui/loginscreen_screen/LoginScreenPresenter.hpp>
#include <touchgfx/widgets/ScalableImage.hpp>

class LoginScreenView : public LoginScreenViewBase
{
public:
    LoginScreenView();
    virtual ~LoginScreenView() {}
    virtual void setupScreen();
    virtual void tearDownScreen();

    // นับเวลาถอยหลังซ่อนกล่องแจ้งเตือน Incorrect PIN
    virtual void handleTickEvent();

protected:
    // 🔑 ตัวจัดการปุ่มกดทั้งหมด (BTN0-9, CLR, Delet, Unlok) ผูกด้วยโค้ดเพราะ Designer ไม่ได้ตั้ง Interaction ไว้
    touchgfx::Callback<LoginScreenView, const touchgfx::AbstractButtonContainer&> buttonCallback;
    void buttonClickHandler(const touchgfx::AbstractButtonContainer& src);

    // ช่องแสดง * ทั้ง 5 หลัก (ผูก buffer ของเราเองทับ wildcard เดิม)
    touchgfx::Unicode::UnicodeChar pinSlotBuffer[5][2];

    // 🚨 กล่องเด้งแจ้งเตือนรหัสผิด (ภาพ PINERROR.png)
    touchgfx::ScalableImage pinErrorToast;
    int toastCountdown = 0;

    char pinValue[6] = {0};   // รหัสที่กดค้างไว้ (สูงสุด 5 หลัก)

    void appendDigit(char digit);
    void backspaceDigit();
    void clearPin();
    void refreshPinSlots();
    void showPinError();
    void hidePinError();
};

#endif // LOGINSCREENVIEW_HPP
