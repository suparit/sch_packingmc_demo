#if defined(WIN32) || defined(_WIN32)
#include <winsock2.h>
#else
#include "uart_link.h"
#endif

#include <gui/settingsscreen_screen/SettingsScreenView.hpp>
#include <images/BitmapDatabase.hpp>
#include <texts/TextKeysAndLanguages.hpp>
#include <touchgfx/Color.hpp>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

// ============ พิกัดแป้นพิมพ์บนจอ 800x480 (ภาพ KEYPAD.png ขนาด 280x360 วาง 1:1) ============
// หมายเหตุ: ห้ามใช้ชื่อ KEYPAD_POS_X / KEYPAD_POS_Y เพราะชนกับ macro ใน wincrypt.h ของ Windows
static const int KEYPAD_POS_X = 260;
static const int KEYPAD_POS_Y = 60;
static const int KEYPAD_COL_X[3] = { 12, 100, 188 };        // คอลัมน์ปุ่มในภาพ
static const int KEYPAD_ROW_Y[4] = { 104, 168, 232, 296 };  // แถวปุ่มในภาพ
static const int KEYPAD_KEY_W = 80;
static const int KEYPAD_KEY_H = 56;

static const int PARAM_MAX_DIGITS = 4;      // พิมพ์ได้สูงสุด 4 หลัก (0-9999)
static const int PARAM_MAX_VALUE  = 9999;

// ค่าพารามิเตอร์ทั้ง 10 ช่อง — ประกาศเป็น static นอกคลาส เพื่อให้ค่าที่พิมพ์ไว้ไม่หาย
// ตอนสลับไปหน้า Main/Report แล้วกลับมา (TouchGFX สร้าง View ใหม่ทุกครั้งที่เปลี่ยนหน้า)
// ค่าเริ่มต้นตามที่ออกแบบไว้ใน Designer (Speed 50, Accel/Decel 30, ที่เหลือ 0)
static int s_paramValue[10] = { 50, 30, 30, 0, 0, 0, 0, 0, 0, 0 };

SettingsScreenView::SettingsScreenView()
    : editButtonCallback(this, &SettingsScreenView::editButtonClickHandler),
      keypadCallback(this, &SettingsScreenView::keypadClickHandler)
{

}

// ขยายกล่องตัวเลขไปทางขวา (ข้อความชิดซ้าย ขอบซ้ายคงที่) กันตัวเลขยาวโดนตัด
// เพราะ Designer เรียก resizeToCurrentText() ทำให้กล่องกว้างเท่าข้อความตัวอย่าง ("0" / "50")
static void widenNumberBox(touchgfx::TextAreaWithOneWildcard& t, int16_t extra)
{
    t.setPosition(t.getX(), t.getY(), t.getWidth() + extra, t.getHeight());
}

void SettingsScreenView::setupScreen()
{
    SettingsScreenViewBase::setupScreen();

    // ============ ผูกปุ่มดินสอเข้ากับช่องข้อความทีละคู่ ============
    touchgfx::AbstractButtonContainer* btns[PARAM_COUNT] = {
        &Button1, &Button2, &Button3, &Button4,  &Button5,
        &Button6, &Button8, &Button9, &Button10, &Button11
    };
    touchgfx::TextAreaWithOneWildcard* texts[PARAM_COUNT] = {
        &textMortor_Speed1, &textMotorAcceleration2, &textMotorDeceleration3, &textCameraPosition4, &textLoadPosition5,
        &textTemperature6,  &textWelding7,           &textTargetPieces8,      &textTape9,           &textReel10
    };
    touchgfx::Unicode::UnicodeChar* buffers[PARAM_COUNT] = {
        textMortor_Speed1Buffer, textMotorAcceleration2Buffer, textMotorDeceleration3Buffer, textCameraPosition4Buffer, textLoadPosition5Buffer,
        textTemperature6Buffer,  textWelding7Buffer,           textTargetPieces8Buffer,      textTape9Buffer,           textReel10Buffer
    };
    const uint16_t sizes[PARAM_COUNT] = {
        TEXTMORTOR_SPEED1_SIZE, TEXTMOTORACCELERATION2_SIZE, TEXTMOTORDECELERATION3_SIZE, TEXTCAMERAPOSITION4_SIZE, TEXTLOADPOSITION5_SIZE,
        TEXTTEMPERATURE6_SIZE,  TEXTWELDING7_SIZE,           TEXTTARGETPIECES8_SIZE,      TEXTTAPE9_SIZE,           TEXTREEL10_SIZE
    };
    // 💾 ปุ่ม SAVE PARAMS ใช้ callback ตัวเดียวกับปุ่มดินสอ แล้วไปแยกใน handler
    // (Designer ไม่ได้ผูก Interaction ให้ BTN_Save ไว้ จึงผูกเองในโค้ดแบบเดียวกับปุ่มดินสอ)
    BTN_Save.setAction(editButtonCallback);

    for (int i = 0; i < PARAM_COUNT; i++)
    {
        paramBtn[i]        = btns[i];
        paramText[i]       = texts[i];
        paramBuffer[i]     = buffers[i];
        paramBufferSize[i] = sizes[i];

        paramBtn[i]->setAction(editButtonCallback);
        widenNumberBox(*paramText[i], 40);
        // เขียนค่าล่าสุดที่จำไว้ทับข้อความตัวอย่างจาก Designer
        Unicode::snprintf(paramBuffer[i], paramBufferSize[i], "%d", s_paramValue[i]);
    }

    // ============ ประกอบแป้นพิมพ์ตัวเลข (ซ่อนไว้ก่อน) ============
    keypadDim.setPosition(0, 0, 800, 480);
    keypadDim.setColor(touchgfx::Color::getColorFromRGB(0, 0, 0));
    keypadDim.setAlpha(140);
    keypadDim.setTouchable(true);   // กลืนทุกการกดที่ทะลุนอกแป้น
    add(keypadDim);

    keypadImg.setBitmap(touchgfx::Bitmap(BITMAP_KEYPAD_ID));
    keypadImg.setPosition(KEYPAD_POS_X, KEYPAD_POS_Y, 280, 360);
    keypadImg.setScalingAlgorithm(touchgfx::ScalableImage::NEAREST_NEIGHBOR);
    add(keypadImg);

    // ช่องแสดงเลข (ใช้ TypedText เดิมของระบบ: Monnospace2 ชิดขวา รองรับตัวเลข)
    keypadDisplay.setPosition(KEYPAD_POS_X + 20, KEYPAD_POS_Y + 60, 240, 30);
    keypadDisplay.setColor(touchgfx::Color::getColorFromRGB(22, 51, 127));
    keypadDisplay.setWildcard(keypadDisplayBuffer);
    keypadDisplay.setTypedText(touchgfx::TypedText(T___SINGLEUSE_EMSE));
    keypadDisplayBuffer[0] = 0;
    add(keypadDisplay);

    // จุดกดล่องหนทับปุ่มเลข 0-9, C, OK ตามตำแหน่งในภาพ
    for (int d = 0; d <= 9; d++) {
        int row, col;
        if (d == 0) { row = 3; col = 1; }
        else        { row = 2 - (d - 1) / 3; col = (d - 1) % 3; }
        keyHits[d].setPosition(KEYPAD_POS_X + KEYPAD_COL_X[col], KEYPAD_POS_Y + KEYPAD_ROW_Y[row], KEYPAD_KEY_W, KEYPAD_KEY_H);
        keyHits[d].setAlpha(0);
        keyHits[d].setClickAction(keypadCallback);
        add(keyHits[d]);
    }
    keyHits[10].setPosition(KEYPAD_POS_X + KEYPAD_COL_X[0], KEYPAD_POS_Y + KEYPAD_ROW_Y[3], KEYPAD_KEY_W, KEYPAD_KEY_H);   // C
    keyHits[10].setAlpha(0);
    keyHits[10].setClickAction(keypadCallback);
    add(keyHits[10]);

    keyHits[11].setPosition(KEYPAD_POS_X + KEYPAD_COL_X[2], KEYPAD_POS_Y + KEYPAD_ROW_Y[3], KEYPAD_KEY_W, KEYPAD_KEY_H);   // OK
    keyHits[11].setAlpha(0);
    keyHits[11].setClickAction(keypadCallback);
    add(keyHits[11]);

    keyClose.setPosition(KEYPAD_POS_X + 236, KEYPAD_POS_Y + 4, 40, 36);                                    // X
    keyClose.setAlpha(0);
    keyClose.setClickAction(keypadCallback);
    add(keyClose);

    setKeypadVisible(false);
}

void SettingsScreenView::tearDownScreen()
{
    SettingsScreenViewBase::tearDownScreen();
}

// 🎮 ยิงคำสั่ง JSON ดิบไปหา Python Gateway
//    - Simulator บน PC: ผ่าน TCP Socket (127.0.0.1:8766)
//    - บอร์ดจริง: ผ่าน UART4 (ST-LINK VCP) → serial_bridge.py → Gateway
static void sendJsonToPython(const char* json)
{
#if defined(WIN32) || defined(_WIN32)
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s != INVALID_SOCKET) {
        sockaddr_in clientService;
        clientService.sin_family = AF_INET;
        clientService.sin_addr.s_addr = inet_addr("127.0.0.1");
        clientService.sin_port = htons(8766);
        if (connect(s, (SOCKADDR*)&clientService, sizeof(clientService)) != SOCKET_ERROR) {
            send(s, json, (int)strlen(json), 0);
        }
        closesocket(s);
    }
#else
    uart_link_send_line(json);
#endif
}

// ✏️ กดปุ่มดินสอช่องไหน → เปิดแป้นพิมพ์ให้ช่องนั้น / กด SAVE → ส่งค่าทั้งชุดไป gateway
void SettingsScreenView::editButtonClickHandler(const touchgfx::AbstractButtonContainer& src)
{
    if (&src == &BTN_Save)
    {
        saveParamsToGateway();
        return;
    }

    for (int i = 0; i < PARAM_COUNT; i++)
    {
        if (&src == paramBtn[i])
        {
            openKeypad(i);
            return;
        }
    }
}

// 💾 SAVE PARAMS: ส่งค่าทั้ง 10 ช่องเป็นคำสั่งเดียว
// gateway เอา target_pieces ไปใช้กับ FSM ตรงๆ ที่เหลือเก็บไว้ใน machine_params ให้หน้าเว็บ/รายงานใช้ต่อ
void SettingsScreenView::saveParamsToGateway()
{
    char json[320];
    int n = snprintf(json, sizeof(json),
        "{\"action\":\"SET_PARAMS\""
        ",\"motor_speed\":%d"
        ",\"motor_accel\":%d"
        ",\"motor_decel\":%d"
        ",\"camera_pos\":%d"
        ",\"load_pos\":%d"
        ",\"temperature\":%d"
        ",\"welding\":%d"
        ",\"tape\":%d"
        ",\"reel\":%d",
        s_paramValue[0], s_paramValue[1], s_paramValue[2], s_paramValue[3], s_paramValue[4],
        s_paramValue[5], s_paramValue[6], s_paramValue[8], s_paramValue[9]);

    // ส่ง target_pieces เฉพาะตอนที่ตั้งค่าไว้จริง — ถ้าปล่อยเป็น 0 gateway จะปัดขึ้นเป็น 1
    // แล้วงานจะจบ batch ทันทีตั้งแต่ชิ้นแรก
    if (n > 0 && n < (int)sizeof(json) && s_paramValue[7] > 0)
    {
        n += snprintf(json + n, sizeof(json) - n, ",\"target_pieces\":%d", s_paramValue[7]);
    }
    if (n > 0 && n < (int)sizeof(json) - 3)
    {
        snprintf(json + n, sizeof(json) - n, "}\n");
        sendJsonToPython(json);
    }
}

void SettingsScreenView::openKeypad(int index)
{
    editingIndex = index;
    // preload ค่าปัจจุบันไว้ในช่อง จะได้เห็นว่ากำลังแก้จากค่าไหน (กด C เพื่อล้าง)
    snprintf(keypadValue, sizeof(keypadValue), "%d", s_paramValue[index]);
    refreshKeypadDisplay();
    setKeypadVisible(true);
}

void SettingsScreenView::closeKeypad()
{
    editingIndex = -1;
    setKeypadVisible(false);
}

// กด OK: ตัดค่าให้อยู่ในช่วง 0-9999 แล้วเขียนลงช่องข้อความที่จับคู่ไว้
void SettingsScreenView::confirmKeypad()
{
    if (editingIndex >= 0 && editingIndex < PARAM_COUNT)
    {
        int value = atoi(keypadValue);
        if (value < 0) value = 0;
        if (value > PARAM_MAX_VALUE) value = PARAM_MAX_VALUE;

        s_paramValue[editingIndex] = value;
        Unicode::snprintf(paramBuffer[editingIndex], paramBufferSize[editingIndex], "%d", value);
        paramText[editingIndex]->invalidate();
    }
    closeKeypad();
}

void SettingsScreenView::keypadClickHandler(const touchgfx::Box& src, const touchgfx::ClickEvent& evt)
{
    if (evt.getType() != touchgfx::ClickEvent::RELEASED)
    {
        return;
    }

    if (&src == &keyClose)
    {
        closeKeypad();
        return;
    }
    if (&src == &keyHits[10])   // C = ล้างค่า
    {
        keypadValue[0] = '\0';
        refreshKeypadDisplay();
        return;
    }
    if (&src == &keyHits[11])   // OK = ยืนยัน
    {
        confirmKeypad();
        return;
    }

    // ปุ่มตัวเลข 0-9
    for (int d = 0; d <= 9; d++)
    {
        if (&src == &keyHits[d])
        {
            int len = (int)strlen(keypadValue);
            if (len < PARAM_MAX_DIGITS)
            {
                keypadValue[len] = (char)('0' + d);
                keypadValue[len + 1] = '\0';
                refreshKeypadDisplay();
            }
            return;
        }
    }
}

void SettingsScreenView::refreshKeypadDisplay()
{
    Unicode::fromUTF8((const uint8_t*)keypadValue, keypadDisplayBuffer, 8);
    keypadDisplay.invalidate();
}

void SettingsScreenView::setKeypadVisible(bool visible)
{
    keypadDim.setVisible(visible);
    keypadImg.setVisible(visible);
    keypadDisplay.setVisible(visible);
    for (int i = 0; i < 12; i++)
    {
        keyHits[i].setVisible(visible);
        keyHits[i].setTouchable(visible);
    }
    keyClose.setVisible(visible);
    keyClose.setTouchable(visible);
    keypadDim.setTouchable(visible);

    keypadDim.invalidate();   // วาดพื้นที่ทั้งจอใหม่ (ครอบคลุมทุก widget ของแป้น)
}
