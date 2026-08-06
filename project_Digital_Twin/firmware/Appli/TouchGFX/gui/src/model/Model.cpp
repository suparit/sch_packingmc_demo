#include <gui/model/Model.hpp>
#include <gui/model/ModelListener.hpp>

#if defined(WIN32) || defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#else
// บนบอร์ดจริง: คุยกับ Digital Twin ผ่าน UART4 (ST-LINK VCP) + serial_bridge.py บน PC
#include "uart_link.h"
#endif

#include <stdio.h>
#include <string.h>

#if defined(WIN32) || defined(_WIN32)
// ใช้เฉพาะตอนรัน Simulator บน PC
static SOCKET sock = INVALID_SOCKET;
static bool isConnected = false;
#endif

Model::Model() : modelListener(0)
{
#if defined(WIN32) || defined(_WIN32)
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2, 2), &wsaData);
#else
    uart_link_init();
#endif
}

// 🧠 แกะ payload JSON แล้วอัปเดต UI — ใช้ร่วมกันทั้ง Simulator (TCP) และบอร์ดจริง (UART)
void Model::processPayloadLine(char* recvbuf)
{
    int pieces = -1;
    char stateBuf[64] = "";
    int temp = -1;
    char statusBuf[32] = "[ RUNNING ]";
    char alarmBuf[64] = "[ NONE ]";

    // 🟢 แกะจำนวนชิ้นงาน
    char* pPieces = strstr(recvbuf, "\"pieces_count\":");
    if (!pPieces) pPieces = strstr(recvbuf, "\"actual_pcs\":");
    if (pPieces) {
        sscanf(pPieces, "%*[^:]:%d", &pieces);
    }

    // 🟢 แกะ FSM State
    char* pState = strstr(recvbuf, "\"current_state\":");
    if (!pState) pState = strstr(recvbuf, "\"fsm_state\":");
    if (!pState) pState = strstr(recvbuf, "\"state\":");

    if (pState) {
        char* colon = strchr(pState, ':');
        if (colon) {
            char* q1 = strchr(colon, '"');
            if (q1) {
                char* q2 = strchr(q1 + 1, '"');
                if (q2) {
                    int len = (int)(q2 - q1 - 1);
                    if (len > 0 && len < 63) {
                        strncpy(stateBuf, q1 + 1, len);
                        stateBuf[len] = '\0';
                    }
                }
            }
        }
    }

    // 🟢 แกะอุณหภูมิ
    char* pTemp = strstr(recvbuf, "\"current_temp\":");
    if (!pTemp) pTemp = strstr(recvbuf, "\"temp\":");
    if (pTemp) {
        sscanf(pTemp, "%*[^:]:%d", &temp);
    }

    // 🟢 แกะ Target Pieces + Pitch (ซิงค์สองทางกับเว็บ 3D Twin)
    int target = -1, pitch = -1;
    char* pTarget = strstr(recvbuf, "\"target_pieces\":");
    if (pTarget) {
        sscanf(pTarget, "%*[^:]:%d", &target);
    }
    char* pPitch = strstr(recvbuf, "\"pitch\":");
    if (pPitch) {
        sscanf(pPitch, "%*[^:]:%d", &pitch);
    }

    // 🟢 แกะ Status
    char* pRun = strstr(recvbuf, "\"running\":");
    if (pRun && strstr(pRun, "false")) {
        snprintf(statusBuf, sizeof(statusBuf), "[ STOPPED ]");
    } else if (strstr(stateBuf, "ALARM") || strstr(stateBuf, "ERROR")) {
        snprintf(statusBuf, sizeof(statusBuf), "[ ALARM ]");
    } else {
        snprintf(statusBuf, sizeof(statusBuf), "[ RUNNING ]");
    }

    // 🟢 แกะ Alarm Message จากทุกคีย์ที่อาจเกิดขึ้นได้
    char* pAlarmMsg = strstr(recvbuf, "\"alarm_message\":");
    if (!pAlarmMsg) pAlarmMsg = strstr(recvbuf, "\"alarm_text\":");
    if (!pAlarmMsg) pAlarmMsg = strstr(recvbuf, "\"alarm\":");
    if (!pAlarmMsg) pAlarmMsg = strstr(recvbuf, "\"error\":");
    if (!pAlarmMsg) pAlarmMsg = strstr(recvbuf, "\"predictive_warning\":");

    if (pAlarmMsg) {
        char* colon = strchr(pAlarmMsg, ':');
        if (colon) {
            char* q1 = strchr(colon, '"');
            if (q1) {
                char* q2 = strchr(q1 + 1, '"');
                if (q2) {
                    int len = (int)(q2 - q1 - 1);
                    if (len > 0 && len < 63) {
                        snprintf(alarmBuf, sizeof(alarmBuf), "[ %.*s ]", len, q1 + 1);
                    }
                }
            }
        }
    }

    // 💡 Fallback: ถ้าเครื่องติด ALARM แต่แกะข้อความไม่ได้ และ Temp เกิน 200°C ให้โชว์ HEATER OVERHEATED
    if (strstr(statusBuf, "ALARM") && strstr(alarmBuf, "NONE")) {
        if (temp >= 200) {
            snprintf(alarmBuf, sizeof(alarmBuf), "[ HEATER OVERHEATED ]");
        } else {
            snprintf(alarmBuf, sizeof(alarmBuf), "[ SYSTEM FAULT ]");
        }
    }

    // 🎥 แกะ step_allowed — gateway หยุดรอ operator กด PASS/NG ที่สเต็ป VISION อยู่หรือเปล่า
    //    (มีเฉพาะ payload สถานะ ไม่มีในบรรทัดตอบของหน้า Report จึงต้องเช็คก่อนว่าเจอคีย์จริง)
    bool gateFound = false;
    bool stepAllowed = false;
    char* pGate = strstr(recvbuf, "\"step_allowed\":");
    if (pGate) {
        char* colon = strchr(pGate, ':');
        if (colon) {
            char* v = colon + 1;
            while (*v == ' ') v++;
            gateFound = true;
            stepAllowed = (strncmp(v, "true", 4) == 0);
        }
    }

    // ส่งข้อมูลไปอัปเดต View ผ่าน Presenter
    if (modelListener) {
        modelListener->onWebDataUpdated(pieces, stateBuf, temp, statusBuf, alarmBuf, target, pitch);
        if (gateFound) {
            modelListener->onVisionGateChanged(stepAllowed);
        }
    }
}

void Model::tick()
{
#if defined(WIN32) || defined(_WIN32)
    // ===== Simulator บน PC: ต่อ TCP Socket ไปที่ Python Gateway (Port 8766) =====
    if (!isConnected) {
        if (sock != INVALID_SOCKET) {
            closesocket(sock);
            sock = INVALID_SOCKET;
        }

        sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (sock != INVALID_SOCKET) {
            sockaddr_in clientService;
            clientService.sin_family = AF_INET;
            clientService.sin_addr.s_addr = inet_addr("127.0.0.1");
            clientService.sin_port = htons(8766);

            DWORD timeout = 100;
            setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (const char*)&timeout, sizeof(timeout));

            if (connect(sock, (SOCKADDR*)&clientService, sizeof(clientService)) != SOCKET_ERROR) {
                u_long mode = 1;
                ioctlsocket(sock, FIONBIO, &mode);
                isConnected = true;
            }
        }
    }

    if (isConnected && sock != INVALID_SOCKET) {
        char recvbuf[1024] = {0};
        int bytesRecv = recv(sock, recvbuf, sizeof(recvbuf) - 1, 0);

        if (bytesRecv > 0) {
            recvbuf[bytesRecv] = '\0';
            processPayloadLine(recvbuf);
        }
        else if (bytesRecv == 0 || (bytesRecv == SOCKET_ERROR && WSAGetLastError() != WSAEWOULDBLOCK)) {
            closesocket(sock);
            sock = INVALID_SOCKET;
            isConnected = false;
        }
    }
#else
    // ===== บอร์ดจริง: ดึงบรรทัด JSON ที่ serial_bridge.py สตรีมลงมาทาง UART =====
    static char line[512];
    int guard = 0;
    while (guard++ < 8 && uart_link_poll_line(line, sizeof(line))) {
        // ข้ามบรรทัดที่เป็นคำตอบของหน้า Report (มี "total") — หน้านั้นจัดการเอง
        if (strstr(line, "\"total\"") == NULL) {
            processPayloadLine(line);
        }
    }
#endif
}
