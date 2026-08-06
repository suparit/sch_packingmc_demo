#if defined(WIN32) || defined(_WIN32)
#include <winsock2.h>
#else
#include "uart_link.h"
#endif

#include <gui/mainscreen_screen/MainScreenView.hpp>
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

// ============ 🎥 พิกัด overlay ยืนยันผลตรวจกล้อง (VISION) ============
static const int VG_PANEL_X = 250;
static const int VG_PANEL_Y = 150;
static const int VG_PANEL_W = 300;
static const int VG_PANEL_H = 180;
static const int VG_BTN_Y   = 240;
static const int VG_BTN_W   = 110;
static const int VG_BTN_H   = 60;
static const int VG_PASS_X  = 275;
static const int VG_NG_X    = 415;

MainScreenView::MainScreenView()
    : keypadCallback(this, &MainScreenView::keypadClickHandler),
      visionCallback(this, &MainScreenView::visionClickHandler)
{

}

// ขยายกล่องตัวเลขไปทางซ้าย (ข้อความชิดขวา ขอบขวาคงที่) กันตัวเลขยาวโดนตัด
static void widenNumberBox(touchgfx::TextAreaWithOneWildcard& t, int16_t extra)
{
    t.setPosition(t.getX() - extra, t.getY(), t.getWidth() + extra, t.getHeight());
}

void MainScreenView::setupScreen()
{
    MainScreenViewBase::setupScreen();

    // Target อาจยาวถึง 4 หลัก (เช่น 1000) แต่กล่องถูก resize ตามข้อความ template "200"
    widenNumberBox(textTargetPcs, 40);

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

    // ============ 🎥 overlay ยืนยันผลตรวจกล้อง (ซ่อนไว้ก่อน) ============
    // เพิ่มทีหลังแป้นพิมพ์ เพื่อให้วาดทับได้ถ้าบังเอิญเปิดค้างไว้ตอนกล้องตรวจเสร็จ
    visionDim.setPosition(0, 0, 800, 480);
    visionDim.setColor(touchgfx::Color::getColorFromRGB(0, 0, 0));
    visionDim.setAlpha(150);
    visionDim.setTouchable(true);   // กลืนทุกการกดที่ทะลุนอก overlay
    add(visionDim);

    visionPanel.setPosition(VG_PANEL_X, VG_PANEL_Y, VG_PANEL_W, VG_PANEL_H);
    visionPanel.setColor(touchgfx::Color::getColorFromRGB(22, 51, 127));
    add(visionPanel);

    // TypedText: ต้องใช้ชุดที่ฟอนต์มี A-Z — CDKF (monosb_12, จัดกึ่งกลาง) ตัวเดียวกับ txtFsmState
    // ห้ามใช้ EMSE: เป็นฟอนต์ของช่องตัวเลขคีย์แพด (monosb_20) ที่ generate มาเฉพาะตัวเลข
    // ตัวอักษรทุกตัวจะกลายเป็น '?' บนจอ (เจอจริง 2026-08-04)
    // กล่องข้อความกว้างเท่า panel/ปุ่ม แล้วให้ CENTER จัดให้เอง จะได้ไม่ต้องเดา offset
    visionTitle.setPosition(VG_PANEL_X, VG_PANEL_Y + 45, VG_PANEL_W, 30);
    visionTitle.setColor(touchgfx::Color::getColorFromRGB(255, 255, 255));
    visionTitle.setWildcard(visionTitleBuffer);
    visionTitle.setTypedText(touchgfx::TypedText(T___SINGLEUSE_CDKF));
    Unicode::fromUTF8((const uint8_t*)"VISION CHECK", visionTitleBuffer, 20);
    add(visionTitle);

    visionPassBtn.setPosition(VG_PASS_X, VG_BTN_Y, VG_BTN_W, VG_BTN_H);
    visionPassBtn.setColor(touchgfx::Color::getColorFromRGB(0, 153, 76));
    visionPassBtn.setClickAction(visionCallback);
    add(visionPassBtn);

    visionNgBtn.setPosition(VG_NG_X, VG_BTN_Y, VG_BTN_W, VG_BTN_H);
    visionNgBtn.setColor(touchgfx::Color::getColorFromRGB(178, 34, 34));
    visionNgBtn.setClickAction(visionCallback);
    add(visionNgBtn);

    // ป้ายบนปุ่ม — กล่องกว้างเท่าปุ่มพอดี ให้ CENTER จัดกลางเอง
    // y เลื่อนลง 22 เพื่อให้ข้อความสูง ~12 px อยู่กลางปุ่มสูง 60 px
    visionPassLabel.setPosition(VG_PASS_X, VG_BTN_Y + 22, VG_BTN_W, 30);
    visionPassLabel.setColor(touchgfx::Color::getColorFromRGB(255, 255, 255));
    visionPassLabel.setWildcard(visionPassBuffer);
    visionPassLabel.setTypedText(touchgfx::TypedText(T___SINGLEUSE_CDKF));
    visionPassLabel.setTouchable(false);
    Unicode::fromUTF8((const uint8_t*)"PASS", visionPassBuffer, 8);
    add(visionPassLabel);

    visionNgLabel.setPosition(VG_NG_X, VG_BTN_Y + 22, VG_BTN_W, 30);
    visionNgLabel.setColor(touchgfx::Color::getColorFromRGB(255, 255, 255));
    visionNgLabel.setWildcard(visionNgBuffer);
    visionNgLabel.setTypedText(touchgfx::TypedText(T___SINGLEUSE_CDKF));
    visionNgLabel.setTouchable(false);
    Unicode::fromUTF8((const uint8_t*)"NG", visionNgBuffer, 8);
    add(visionNgLabel);

    setVisionGateVisible(false);
}

void MainScreenView::tearDownScreen()
{
    MainScreenViewBase::tearDownScreen();
}

void MainScreenView::updateDataFromWeb(int pieces, const char* stateName, int temp,
                                       const char* statusText, const char* alarmText,
                                       int target, int pitch)
{
    // 1. อัปเดตตัวเลขนับชิ้นงาน
    if (pieces >= 0) {
        Unicode::snprintf(textActualPcsBuffer, TEXTACTUALPCS_SIZE, "%d", pieces);
        textActualPcs.invalidate();
    }

    // 2. อัปเดต FSM State
    if (stateName != nullptr && strlen(stateName) > 0) {
        memset(txtFsmStateBuffer, 0, sizeof(txtFsmStateBuffer));
        Unicode::fromUTF8((const uint8_t*)stateName, txtFsmStateBuffer, TXTFSMSTATE_SIZE);
        txtFsmState.invalidate();
    }

    // 3. อัปเดตอุณหภูมิ Left / Right
    if (temp > 0) {
        Unicode::snprintf(textTempLeftBuffer, TEXTTEMPLEFT_SIZE, "%d", temp);
        textTempLeft.invalidate();

        Unicode::snprintf(textTempRightBuffer, TEXTTEMPRIGHT_SIZE, "%d", temp);
        textTempRight.invalidate();
    }

    // 🟢 4. อัปเดต STATUS [ RUNNING / STOPPED ]
    if (statusText != nullptr && strlen(statusText) > 0) {
        memset(txtStatusBuffer, 0, sizeof(txtStatusBuffer));
        Unicode::fromUTF8((const uint8_t*)statusText, txtStatusBuffer, TXTSTATUS_SIZE);
        txtStatus.invalidate();
    }

    // 🟢 5. อัปเดต ALARM [ NONE / ERROR MSG ]
    if (alarmText != nullptr && strlen(alarmText) > 0) {
        memset(txtAlarmBuffer, 0, sizeof(txtAlarmBuffer));
        Unicode::fromUTF8((const uint8_t*)alarmText, txtAlarmBuffer, TXTALARM_SIZE);
        txtAlarm.invalidate();
    }

    // 🔢 6. อัปเดต Target Pcs + Pitch (ซิงค์ Real-time จากเว็บ 3D Twin / แป้นพิมพ์)
    if (target > 0) {
        lastTargetPcs = target;
        Unicode::snprintf(textTargetPcsBuffer, TEXTTARGETPCS_SIZE, "%d", target);
        textTargetPcs.invalidate();
    }
    if (pitch > 0) {
        lastPitchMm = pitch;
        Unicode::snprintf(txtPitchBuffer, TXTPITCH_SIZE, "%d", pitch);
        txtPitch.invalidate();
    }
}

// 🎮 ฟังก์ชันยิงคำสั่ง JSON ดิบไปหา Python Gateway
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

// 🎮 ฟังก์ชันสั่งงานปุ่มกด ยิงคำสั่ง action ตรงหา Python
static void sendCmdToPython(const char* action)
{
    char buf[128];
    snprintf(buf, sizeof(buf), "{\"action\":\"%s\"}\n", action);
    sendJsonToPython(buf);
}

void MainScreenView::btnStartClicked()
{
    sendCmdToPython("START");
}

void MainScreenView::btnStopClicked()
{
    sendCmdToPython("STOP");
}

void MainScreenView::btnResetClicked()
{
    sendCmdToPython("RESET");
}

// ============ แป้นพิมพ์ตัวเลข ============

// 🔢 ปุ่มดินสอข้าง TARGET: เปิดแป้นตั้งเป้าหมายชิ้นงาน → แสดงผลที่ textTargetPcs
void MainScreenView::btnTargetEditClicked()
{
    openKeypad(KEYPAD_TARGET);
}

// 🔢 ปุ่มดินสอข้าง PITCH: เปิดแป้นตั้งระยะพิตช์ → แสดงผลที่ txtPitch
void MainScreenView::btnPitchEditClicked()
{
    openKeypad(KEYPAD_PITCH);
}

void MainScreenView::openKeypad(int mode)
{
    keypadMode = mode;
    // preload ค่าปัจจุบันไว้ในช่อง จะได้เห็นว่ากำลังแก้จากค่าไหน (กด C เพื่อล้าง)
    snprintf(keypadValue, sizeof(keypadValue), "%d",
             (mode == KEYPAD_TARGET) ? lastTargetPcs : lastPitchMm);
    refreshKeypadDisplay();
    setKeypadVisible(true);
}

void MainScreenView::closeKeypad()
{
    keypadMode = KEYPAD_NONE;
    setKeypadVisible(false);
}

// กด OK: ตัดค่าให้อยู่ในช่วงที่ปลอดภัย แล้วยิง SET_PARAMS ให้ Python
// ค่าใหม่จะ broadcast กลับมาอัปเดต textTargetPcs / txtPitch และเว็บ 3D Twin แบบ Real-time
void MainScreenView::confirmKeypad()
{
    int value = atoi(keypadValue);
    char json[96];

    if (keypadMode == KEYPAD_TARGET) {
        if (value < 1) value = 1;
        if (value > 9999) value = 9999;
        snprintf(json, sizeof(json), "{\"action\":\"SET_PARAMS\",\"target_pieces\":%d}\n", value);
        sendJsonToPython(json);

        lastTargetPcs = value;   // อัปเดตจอทันทีไม่ต้องรอ broadcast
        Unicode::snprintf(textTargetPcsBuffer, TEXTTARGETPCS_SIZE, "%d", value);
        textTargetPcs.invalidate();
    } else if (keypadMode == KEYPAD_PITCH) {
        if (value < 1) value = 1;
        if (value > 99) value = 99;
        snprintf(json, sizeof(json), "{\"action\":\"SET_PARAMS\",\"pitch\":%d}\n", value);
        sendJsonToPython(json);

        lastPitchMm = value;
        Unicode::snprintf(txtPitchBuffer, TXTPITCH_SIZE, "%d", value);
        txtPitch.invalidate();
    }
    closeKeypad();
}

void MainScreenView::keypadClickHandler(const touchgfx::Box& src, const touchgfx::ClickEvent& evt)
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

    // ปุ่มตัวเลข 0-9 (Pitch จำกัด 2 หลัก, Target จำกัด 4 หลัก)
    int maxLen = (keypadMode == KEYPAD_PITCH) ? 2 : 4;
    for (int d = 0; d <= 9; d++)
    {
        if (&src == &keyHits[d])
        {
            int len = (int)strlen(keypadValue);
            if (len < maxLen)
            {
                keypadValue[len] = (char)('0' + d);
                keypadValue[len + 1] = '\0';
                refreshKeypadDisplay();
            }
            return;
        }
    }
}

// ============ 🎥 VISION GATE: ปุ่ม PASS / NG ============

// เรียกจาก Presenter ทุกครั้งที่ payload มีคีย์ step_allowed
// (เปลี่ยนสถานะเมื่อค่าต่างจากเดิมเท่านั้น ไม่งั้นจะสั่ง invalidate ทั้งจอทุก 20 ms)
void MainScreenView::updateVisionGate(bool waitingForOperator)
{
    if (waitingForOperator == visionGateShown)
    {
        return;
    }
    visionGateShown = waitingForOperator;
    setVisionGateVisible(waitingForOperator);
}

void MainScreenView::visionClickHandler(const touchgfx::Box& src, const touchgfx::ClickEvent& evt)
{
    if (evt.getType() != touchgfx::ClickEvent::RELEASED)
    {
        return;
    }

    if (&src == &visionPassBtn)
    {
        sendJsonToPython("{\"action\":\"DECISION\",\"value\":true}\n");
    }
    else if (&src == &visionNgBtn)
    {
        sendJsonToPython("{\"action\":\"DECISION\",\"value\":false}\n");
    }
    else
    {
        return;   // กดโดนฉากหลังมืด = ไม่ทำอะไร ต้องเลือก PASS หรือ NG เท่านั้น
    }

    // ปิด overlay ทันทีไม่ต้องรอ broadcast กลับ กันกดซ้ำสองครั้ง
    visionGateShown = false;
    setVisionGateVisible(false);
}

void MainScreenView::setVisionGateVisible(bool visible)
{
    visionDim.setVisible(visible);
    visionDim.setTouchable(visible);
    visionPanel.setVisible(visible);
    visionTitle.setVisible(visible);

    visionPassBtn.setVisible(visible);
    visionPassBtn.setTouchable(visible);
    visionNgBtn.setVisible(visible);
    visionNgBtn.setTouchable(visible);
    visionPassLabel.setVisible(visible);
    visionNgLabel.setVisible(visible);

    visionDim.invalidate();   // วาดพื้นที่ทั้งจอใหม่ (ครอบคลุมทุก widget ของ overlay)
}

void MainScreenView::refreshKeypadDisplay()
{
    Unicode::fromUTF8((const uint8_t*)keypadValue, keypadDisplayBuffer, 8);
    keypadDisplay.invalidate();
}

void MainScreenView::setKeypadVisible(bool visible)
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
