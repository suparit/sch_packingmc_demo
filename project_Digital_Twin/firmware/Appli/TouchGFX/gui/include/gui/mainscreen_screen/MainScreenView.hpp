#ifndef MAINSCREENVIEW_HPP
#define MAINSCREENVIEW_HPP

#include <gui_generated/mainscreen_screen/MainScreenViewBase.hpp>
#include <gui/mainscreen_screen/MainScreenPresenter.hpp>
#include <touchgfx/widgets/Box.hpp>
#include <touchgfx/widgets/ScalableImage.hpp>
#include <touchgfx/widgets/TextAreaWithWildcard.hpp>
#include <touchgfx/mixins/ClickListener.hpp>

class MainScreenView : public MainScreenViewBase
{
public:
    MainScreenView();
    virtual ~MainScreenView() {}
    virtual void setupScreen();
    virtual void tearDownScreen();

    // ฟังก์ชันอัปเดตข้อมูลบน UI (target/pitch ซิงค์สองทางกับเว็บ 3D Twin)
    virtual void updateDataFromWeb(int pieces, const char* stateName, int temp,
                                   const char* statusText, const char* alarmText,
                                   int target, int pitch);

    // Event Handlers ปุ่มกด
    virtual void btnStartClicked();
    virtual void btnStopClicked();
    virtual void btnResetClicked();

    // 🔢 ปุ่มดินสอ: เปิดแป้นพิมพ์ตัวเลข (Interaction ใน Designer เรียกชื่อพวกนี้)
    virtual void btnTargetEditClicked();
    virtual void btnPitchEditClicked();

    // 🎥 gateway หยุดรอ operator ที่สเต็ป VISION → เด้ง/ปิด overlay ปุ่ม PASS/NG
    virtual void updateVisionGate(bool waitingForOperator);

protected:
    // ============ แป้นพิมพ์ตัวเลข (ภาพ KEYPAD.png + จุดกดล่องหน) ============
    enum KeypadMode { KEYPAD_NONE = 0, KEYPAD_TARGET, KEYPAD_PITCH };

    touchgfx::Box keypadDim;                                // ฉากหลังมืด กันกดทะลุไปโดนปุ่มข้างล่าง
    touchgfx::ScalableImage keypadImg;                      // ภาพแป้นพิมพ์
    touchgfx::TextAreaWithOneWildcard keypadDisplay;        // ช่องแสดงเลขที่กำลังพิมพ์
    touchgfx::Unicode::UnicodeChar keypadDisplayBuffer[8];
    touchgfx::ClickListener<touchgfx::Box> keyHits[12];     // index 0-9 = เลข, 10 = C, 11 = OK
    touchgfx::ClickListener<touchgfx::Box> keyClose;        // ปุ่ม X ปิดแป้น
    touchgfx::Callback<MainScreenView, const touchgfx::Box&, const touchgfx::ClickEvent&> keypadCallback;
    void keypadClickHandler(const touchgfx::Box& src, const touchgfx::ClickEvent& evt);

    int keypadMode = KEYPAD_NONE;
    char keypadValue[6] = {0};      // เลขที่พิมพ์ค้างไว้ (สูงสุด 4 หลัก)
    int lastTargetPcs = 200;        // ค่าล่าสุดจาก backend ไว้ preload ตอนเปิดแป้น
    int lastPitchMm = 24;

    void openKeypad(int mode);
    void closeKeypad();
    void confirmKeypad();
    void refreshKeypadDisplay();
    void setKeypadVisible(bool visible);

    // ============ 🎥 VISION GATE: ปุ่ม PASS / NG ============
    // สเต็ป VISION บน gateway หยุดรอคนยืนยันเสมอ (แม้โหมด auto) ถ้าจอไม่มีปุ่มนี้
    // แล้วสั่ง START จากจออย่างเดียวโดยไม่เปิดหน้าเว็บ เครื่องจะค้างที่ VISION ตลอดไป
    touchgfx::Box visionDim;                              // ฉากหลังมืด กันกดทะลุไปโดนปุ่มข้างล่าง
    touchgfx::Box visionPanel;                            // กล่องคำถาม
    touchgfx::TextAreaWithOneWildcard visionTitle;        // ข้อความ "VISION CHECK"
    touchgfx::Unicode::UnicodeChar visionTitleBuffer[20];
    touchgfx::ClickListener<touchgfx::Box> visionPassBtn; // ปุ่มเขียว = ชิ้นงานดี
    touchgfx::ClickListener<touchgfx::Box> visionNgBtn;   // ปุ่มแดง = ชิ้นงานเสีย
    touchgfx::TextAreaWithOneWildcard visionPassLabel;
    touchgfx::Unicode::UnicodeChar visionPassBuffer[8];
    touchgfx::TextAreaWithOneWildcard visionNgLabel;
    touchgfx::Unicode::UnicodeChar visionNgBuffer[8];
    touchgfx::Callback<MainScreenView, const touchgfx::Box&, const touchgfx::ClickEvent&> visionCallback;
    void visionClickHandler(const touchgfx::Box& src, const touchgfx::ClickEvent& evt);

    bool visionGateShown = false;

    void setVisionGateVisible(bool visible);
};

#endif // MAINSCREENVIEW_HPP
