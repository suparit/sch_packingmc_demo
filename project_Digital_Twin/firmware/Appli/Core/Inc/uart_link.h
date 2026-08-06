/**
 * uart_link.h — Serial Link ระหว่างบอร์ด STM32H7S78-DK กับ Digital Twin บน PC
 *
 * ใช้ UART4 (TX=PD1, RX=PD0) ซึ่งต่อกับ ST-LINK Virtual COM Port ในตัวบอร์ด
 * ฝั่ง PC รันสคริปต์ python_backend/serial_bridge.py เพื่อถ่ายทอดข้อมูล
 * ระหว่าง COM port กับ gateway_fsm.py (TCP 8766) — โปรโตคอลเป็น JSON คั่นด้วย \n
 * เหมือนที่ TouchGFX Simulator ใช้ทุกประการ
 */
#ifndef UART_LINK_H
#define UART_LINK_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* เรียกครั้งเดียวตอนบูต (เรียกซ้ำได้ ไม่ init ซ้ำ) */
void uart_link_init(void);

/* ส่งสตริง 1 บรรทัดออก UART (เติม \n ให้อัตโนมัติถ้ายังไม่มี) — blocking สั้นๆ */
void uart_link_send_line(const char* line);

/* ดึงบรรทัดที่รับครบแล้ว (ตัด \n ออกให้) — คืน 1 ถ้าได้บรรทัด, 0 ถ้ายังไม่มี */
int uart_link_poll_line(char* out, int maxLen);

#ifdef __cplusplus
}
#endif

#endif /* UART_LINK_H */
