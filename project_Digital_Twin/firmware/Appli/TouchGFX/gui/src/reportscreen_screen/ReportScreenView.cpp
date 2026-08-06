#if defined(WIN32) || defined(_WIN32)
#include <winsock2.h>
#include <windows.h>
#else
#include "uart_link.h"
#include <touchgfx/hal/OSWrappers.hpp>
#endif

#include <gui/reportscreen_screen/ReportScreenView.hpp>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

ReportScreenView::ReportScreenView()
{

}

// ขยายกล่องตัวเลขไปทางซ้าย (ข้อความชิดขวา ขอบขวาคงที่เดิม)
// กันตัวเลขยาวกว่าข้อความ template ใน Designer แล้วโดนตัด เช่น 100.0 กลายเป็น 00.0
static void widenNumberBox(touchgfx::TextAreaWithOneWildcard& t, int16_t extra)
{
    t.setPosition(t.getX() - extra, t.getY(), t.getWidth() + extra, t.getHeight());
}

void ReportScreenView::setupScreen()
{
    ReportScreenViewBase::setupScreen();

    widenNumberBox(txtTotalPcs, 50);
    widenNumberBox(txtOkPcs, 50);
    widenNumberBox(txtNgPcs, 50);
    widenNumberBox(txtYieldRate, 50);

    // 🚀 เปิดมาหน้านี้ปุ๊บ ให้ดึงค่าล่าสุดจากเว็บทันที
    tickCounter = 0;
    btnRefreshClicked();
}

void ReportScreenView::tearDownScreen()
{
    ReportScreenViewBase::tearDownScreen();
}

// 🔄 Real-time: TouchGFX เรียกฟังก์ชันนี้ทุกเฟรม (~60 ครั้ง/วินาที)
// ครบทุก 120 tick (~2 วินาที) ให้ดึงข้อมูลรายงาน + SQL Ledger รอบใหม่อัตโนมัติ
void ReportScreenView::handleTickEvent()
{
    tickCounter++;
    if (tickCounter >= 120)
    {
        tickCounter = 0;
        btnRefreshClicked();
    }
}

// 🟢 Helper: ดึงค่าสตริงจาก key ใน JSON แบบสแกนง่ายๆ พร้อมแปลง \n และ \" กลับเป็นตัวจริง
//    รองรับทั้ง "key":"..." และ "key": "..." (มีช่องว่างหลัง colon แบบ json.dumps ปกติ)
static bool extractJsonString(const char* src, const char* key, char* out, int outSize)
{
    char pattern[32];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    const char* p = strstr(src, pattern);
    if (!p) return false;
    p += strlen(pattern);
    while (*p == ':' || *p == ' ') p++;
    if (*p != '"') return false;
    p++;

    int i = 0;
    while (*p != '"' && *p != '\0' && i < outSize - 1) {
        if (*p == '\\' && *(p + 1) == 'n') {
            out[i++] = '\n';
            p += 2;
        } else if (*p == '\\' && *(p + 1) == '"') {
            out[i++] = '"';
            p += 2;
        } else {
            out[i++] = *p++;
        }
    }
    out[i] = '\0';
    return true;
}

// 🟢 Helper: ส่งคำสั่ง 1 ก้อนหา Python Gateway แล้วรอรับคำตอบ คืนจำนวน byte ที่ได้ (0 = ไม่สำเร็จ)
//    - Simulator บน PC: TCP Socket (127.0.0.1:8766) วนรับจนอีกฝั่งปิดสาย
//    - บอร์ดจริง: ส่งทาง UART แล้วรอบรรทัดคำตอบ (มี key "total"/"status") สูงสุด ~400ms
static int sendCmdAndRecv(const char* cmd, char* buffer, int bufSize)
{
    int totalReceived = 0;
#if defined(WIN32) || defined(_WIN32)
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s != INVALID_SOCKET) {
        DWORD timeout = 1000; // 1 วินาที
        setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, (const char*)&timeout, sizeof(timeout));
        setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char*)&timeout, sizeof(timeout));

        sockaddr_in clientService;
        clientService.sin_family = AF_INET;
        clientService.sin_addr.s_addr = inet_addr("127.0.0.1");
        clientService.sin_port = htons(8766);

        if (connect(s, (SOCKADDR*)&clientService, sizeof(clientService)) != SOCKET_ERROR) {
            send(s, cmd, (int)strlen(cmd), 0);

            int bytesReceived;
            while (totalReceived < bufSize - 1 &&
                   (bytesReceived = recv(s, buffer + totalReceived, bufSize - 1 - totalReceived, 0)) > 0) {
                totalReceived += bytesReceived;
            }
        }
        closesocket(s);
    }
#else
    uart_link_init();
    uart_link_send_line(cmd);

    static char line[2048];   // static กันกินสแตกของ GUI task (มี GUI thread เดียว ปลอดภัย)
    for (int waited = 0; waited < 400; waited += 10)
    {
        while (uart_link_poll_line(line, sizeof(line)))
        {
            // คำตอบของหน้า Report จะมี key พวกนี้ — บรรทัด broadcast อื่นข้ามไป
            if (strstr(line, "\"total\"") || strstr(line, "\"status\"") || strstr(line, "\"file\""))
            {
                strncpy(buffer, line, bufSize - 1);
                buffer[bufSize - 1] = '\0';
                return (int)strlen(buffer);
            }
        }
        touchgfx::OSWrappers::taskDelay(10);
    }
#endif
    if (totalReceived >= 0 && totalReceived < bufSize) {
        buffer[totalReceived] = '\0';
    }
    return totalReceived;
}

// 🔵 REFRESH: บังคับซิงค์ข้อมูลรายงาน + SQL Ledger เดี๋ยวนี้ (ไม่ต้องรอรอบ 2 วินาที)
void ReportScreenView::btnRefreshClicked()
{
    tickCounter = 0; // เริ่มนับรอบ auto-refresh ใหม่จากวินาทีที่กด

    char buffer[2048] = {0};
    if (sendCmdAndRecv("{\"cmd\":\"REQ_REPORT_DATA\"}\n", buffer, sizeof(buffer)) > 0) {
        // Parse ตัวเลขแบบสแกนง่ายๆ e.g. {"total":250,"ok":240,"ng":10,"yield":96.0}
        int total = 0, ok = 0, ng = 0;
        float yieldRate = 0.0f;

        char* pTotal = strstr(buffer, "\"total\":");
        char* pOk = strstr(buffer, "\"ok\":");
        char* pNg = strstr(buffer, "\"ng\":");
        char* pYield = strstr(buffer, "\"yield\":");

        if (pTotal) total = atoi(pTotal + 8);
        if (pOk) ok = atoi(pOk + 5);
        if (pNg) ng = atoi(pNg + 5);
        if (pYield) yieldRate = (float)atof(pYield + 8);

        updateReportData(total, ok, ng, yieldRate);

        // แสดง Live SQL Transition Ledger (10 แถวล่าสุด) ใน scrollableContainer1
        // (ถ้า backend รุ่นเก่าไม่มี ledger_text ให้ถอยไปแสดง log_text แทน)
        char textBuf[1024] = {0};
        if (extractJsonString(buffer, "ledger_text", textBuf, sizeof(textBuf)) ||
            extractJsonString(buffer, "log_text", textBuf, sizeof(textBuf))) {
            updateAlarmLogText(textBuf);
        }
    }
}

// 🔴 CLEAR LOGS: ล้างประวัติ SQL ทั้งหมด (machine_logs + summary) = เริ่มเก็บสถิติ lot ใหม่
//    หน้า Analytics บนเว็บจะว่างตามกันเพราะใช้ฐานข้อมูลเดียวกัน
void ReportScreenView::btnClearClicked()
{
    char buffer[256] = {0};
    sendCmdAndRecv("{\"cmd\":\"CLEAR_SQL_HISTORY\"}\n", buffer, sizeof(buffer));

    // ดึงข้อมูลรอบใหม่มาแสดงทันที (ledger จะขึ้น NO SQL DATA YET)
    btnRefreshClicked();
}

// 🟢 SAVE DATA: สั่ง Python export ประวัติทั้งหมดเป็นไฟล์ CSV ใน python_backend/exports/
//    แล้วโชว์ชื่อไฟล์ยืนยันบนจอชั่วครู่ ก่อน auto-refresh กลับมาแสดง ledger ตามปกติ
void ReportScreenView::btnSaveClicked()
{
    char buffer[512] = {0};
    if (sendCmdAndRecv("{\"cmd\":\"EXPORT_CSV\"}\n", buffer, sizeof(buffer)) > 0) {
        char fileBuf[256] = {0};
        char msg[512] = {0};

        if (strstr(buffer, "\"status\":\"saved\"") &&
            extractJsonString(buffer, "file", fileBuf, sizeof(fileBuf))) {
            snprintf(msg, sizeof(msg),
                     "[ OK ] DATA EXPORTED TO CSV:\n\npython_backend/exports/\n%s", fileBuf);
        } else {
            snprintf(msg, sizeof(msg), "[ ERROR ] CSV EXPORT FAILED!\nCHECK PYTHON GATEWAY CONSOLE");
        }
        updateAlarmLogText(msg);

        // หน่วงรอบ auto-refresh ออกไป ~4 วินาที ให้ผู้ใช้อ่านข้อความยืนยันทัน
        tickCounter = -120;
    } else {
        updateAlarmLogText("[ ERROR ] GATEWAY OFFLINE!\nCANNOT EXPORT CSV");
        tickCounter = -120;
    }
}

void ReportScreenView::updateReportData(int total, int ok, int ng, float yieldRate)
{
    Unicode::snprintf(txtTotalPcsBuffer, TXTTOTALPCS_SIZE, "%d", total);
    txtTotalPcs.invalidate();

    Unicode::snprintf(txtOkPcsBuffer, TXTOKPCS_SIZE, "%d", ok);
    txtOkPcs.invalidate();

    Unicode::snprintf(txtNgPcsBuffer, TXTNGPCS_SIZE, "%d", ng);
    txtNgPcs.invalidate();

    Unicode::snprintfFloat(txtYieldRateBuffer, TXTYIELDRATE_SIZE, "%.1f", yieldRate);
    txtYieldRate.invalidate();
}

void ReportScreenView::updateAlarmLogText(const char* logText)
{
    Unicode::fromUTF8((const uint8_t*)logText, textArea1Buffer, TEXTAREA1_SIZE);
    textArea1.invalidate();
}
