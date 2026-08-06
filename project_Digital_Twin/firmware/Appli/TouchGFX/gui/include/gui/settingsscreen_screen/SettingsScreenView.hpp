#ifndef SETTINGSSCREENVIEW_HPP
#define SETTINGSSCREENVIEW_HPP

#include <gui_generated/settingsscreen_screen/SettingsScreenViewBase.hpp>
#include <gui/settingsscreen_screen/SettingsScreenPresenter.hpp>
#include <touchgfx/widgets/Box.hpp>
#include <touchgfx/widgets/ScalableImage.hpp>
#include <touchgfx/widgets/TextAreaWithWildcard.hpp>
#include <touchgfx/mixins/ClickListener.hpp>

class SettingsScreenView : public SettingsScreenViewBase
{
public:
    SettingsScreenView();
    virtual ~SettingsScreenView() {}
    virtual void setupScreen();
    virtual void tearDownScreen();

protected:
    // ============ ช่องพารามิเตอร์ 10 ช่อง (ปุ่มดินสอ ↔ ช่องตัวเลข) ============
    // ลำดับต้องตรงกันทั้ง 3 ตาราง: Button1→textMortor_Speed1 ... Button11→textReel10
    static const int PARAM_COUNT = 10;

    touchgfx::AbstractButtonContainer* paramBtn[PARAM_COUNT];
    touchgfx::TextAreaWithOneWildcard* paramText[PARAM_COUNT];
    touchgfx::Unicode::UnicodeChar*    paramBuffer[PARAM_COUNT];
    uint16_t                           paramBufferSize[PARAM_COUNT];

    touchgfx::Callback<SettingsScreenView, const touchgfx::AbstractButtonContainer&> editButtonCallback;
    void editButtonClickHandler(const touchgfx::AbstractButtonContainer& src);

    // ============ แป้นพิมพ์ตัวเลข (ภาพ KEYPAD.png + จุดกดล่องหน) — แบบเดียวกับ MainScreen ============
    touchgfx::Box keypadDim;                                // ฉากหลังมืด กันกดทะลุไปโดนปุ่มข้างล่าง
    touchgfx::ScalableImage keypadImg;                      // ภาพแป้นพิมพ์
    touchgfx::TextAreaWithOneWildcard keypadDisplay;        // ช่องแสดงเลขที่กำลังพิมพ์
    touchgfx::Unicode::UnicodeChar keypadDisplayBuffer[8];
    touchgfx::ClickListener<touchgfx::Box> keyHits[12];     // index 0-9 = เลข, 10 = C, 11 = OK
    touchgfx::ClickListener<touchgfx::Box> keyClose;        // ปุ่ม X ปิดแป้น
    touchgfx::Callback<SettingsScreenView, const touchgfx::Box&, const touchgfx::ClickEvent&> keypadCallback;
    void keypadClickHandler(const touchgfx::Box& src, const touchgfx::ClickEvent& evt);

    int  editingIndex = -1;         // ช่องที่กำลังแก้อยู่ (-1 = แป้นปิด)
    char keypadValue[6] = {0};      // เลขที่พิมพ์ค้างไว้ (สูงสุด 4 หลัก)

    // 💾 ปุ่ม SAVE PARAMS: ยิงค่าทั้ง 10 ช่องเป็น SET_PARAMS ไปที่ Python Gateway
    void saveParamsToGateway();

    void openKeypad(int index);
    void closeKeypad();
    void confirmKeypad();
    void refreshKeypadDisplay();
    void setKeypadVisible(bool visible);
};

#endif // SETTINGSSCREENVIEW_HPP
