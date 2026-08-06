/**
 * uart_link.c — Serial Link (UART4 / ST-LINK VCP) สำหรับคุยกับ Digital Twin บน PC
 *
 * - RX: interrupt ทีละ byte เก็บลง ring buffer แล้วให้ GUI thread มา poll เป็นบรรทัด
 * - TX: blocking สั้นๆ (บรรทัดละไม่กี่ร้อย byte ที่ 115200 ≈ ไม่กี่ ms)
 */
#include "uart_link.h"
#include "stm32h7rsxx_hal.h"
#include <string.h>

#define UART_LINK_BAUDRATE   115200U
#define RX_RING_SIZE         2048U

UART_HandleTypeDef huart4;

static volatile uint16_t rxHead = 0;   /* ตำแหน่งเขียน (ISR) */
static volatile uint16_t rxTail = 0;   /* ตำแหน่งอ่าน (GUI thread) */
static uint8_t rxRing[RX_RING_SIZE];
static uint8_t rxByte;
static uint8_t initialized = 0;

/* HAL เรียกอัตโนมัติจาก HAL_UART_Init() */
void HAL_UART_MspInit(UART_HandleTypeDef* huart)
{
    if (huart->Instance == UART4)
    {
        GPIO_InitTypeDef gpio = {0};

        __HAL_RCC_GPIOD_CLK_ENABLE();
        __HAL_RCC_UART4_CLK_ENABLE();

        /* PD0 = UART4_RX, PD1 = UART4_TX (ST-LINK VCP บนบอร์ด H7S78-DK) */
        gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1;
        gpio.Mode = GPIO_MODE_AF_PP;
        gpio.Pull = GPIO_NOPULL;
        gpio.Speed = GPIO_SPEED_FREQ_LOW;
        gpio.Alternate = GPIO_AF8_UART4;
        HAL_GPIO_Init(GPIOD, &gpio);

        /* ความสำคัญต่ำกว่าระบบกราฟิก/RTOS — ISR แค่หย่อน byte ลง ring buffer */
        HAL_NVIC_SetPriority(UART4_IRQn, 7, 0);
        HAL_NVIC_EnableIRQ(UART4_IRQn);
    }
}

void HAL_UART_MspDeInit(UART_HandleTypeDef* huart)
{
    if (huart->Instance == UART4)
    {
        __HAL_RCC_UART4_CLK_DISABLE();
        HAL_GPIO_DeInit(GPIOD, GPIO_PIN_0 | GPIO_PIN_1);
        HAL_NVIC_DisableIRQ(UART4_IRQn);
    }
}

void uart_link_init(void)
{
    if (initialized)
    {
        return;
    }

    huart4.Instance = UART4;
    huart4.Init.BaudRate = UART_LINK_BAUDRATE;
    huart4.Init.WordLength = UART_WORDLENGTH_8B;
    huart4.Init.StopBits = UART_STOPBITS_1;
    huart4.Init.Parity = UART_PARITY_NONE;
    huart4.Init.Mode = UART_MODE_TX_RX;
    huart4.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart4.Init.OverSampling = UART_OVERSAMPLING_16;
    huart4.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
    huart4.Init.ClockPrescaler = UART_PRESCALER_DIV1;

    if (HAL_UART_Init(&huart4) == HAL_OK)
    {
        initialized = 1;
        HAL_UART_Receive_IT(&huart4, &rxByte, 1);   /* เริ่มดักรับทีละ byte */
    }
}

void uart_link_send_line(const char* line)
{
    if (!initialized || line == NULL)
    {
        return;
    }

    uint16_t len = (uint16_t)strlen(line);
    HAL_UART_Transmit(&huart4, (const uint8_t*)line, len, 100);
    if (len == 0 || line[len - 1] != '\n')
    {
        HAL_UART_Transmit(&huart4, (const uint8_t*)"\n", 1, 10);
    }
}

int uart_link_poll_line(char* out, int maxLen)
{
    if (!initialized || out == NULL || maxLen < 2)
    {
        return 0;
    }

    /* สแกนหา \n ในช่วงข้อมูลที่ค้างอยู่ (tail → head) */
    uint16_t head = rxHead;   /* snapshot กัน ISR ขยับระหว่างสแกน */
    uint16_t scan = rxTail;
    int newlineFound = 0;

    while (scan != head)
    {
        if (rxRing[scan] == '\n')
        {
            newlineFound = 1;
            break;
        }
        scan = (uint16_t)((scan + 1) % RX_RING_SIZE);
    }

    if (!newlineFound)
    {
        return 0;
    }

    /* คัดลอกตั้งแต่ tail จนถึงตัว \n (ไม่รวม \n) แล้วเลื่อน tail ข้ามไป */
    int i = 0;
    while (rxTail != scan)
    {
        char c = (char)rxRing[rxTail];
        rxTail = (uint16_t)((rxTail + 1) % RX_RING_SIZE);
        if (c != '\r' && i < maxLen - 1)
        {
            out[i++] = c;
        }
    }
    rxTail = (uint16_t)((rxTail + 1) % RX_RING_SIZE);   /* ข้ามตัว \n */
    out[i] = '\0';
    return 1;
}

/* ===== HAL Callbacks (interrupt context) ===== */

void HAL_UART_RxCpltCallback(UART_HandleTypeDef* huart)
{
    if (huart->Instance == UART4)
    {
        uint16_t next = (uint16_t)((rxHead + 1) % RX_RING_SIZE);
        if (next != rxTail)   /* buffer เต็มให้ทิ้ง byte ใหม่ (กันเขียนทับข้อมูลเก่า) */
        {
            rxRing[rxHead] = rxByte;
            rxHead = next;
        }
        HAL_UART_Receive_IT(&huart4, &rxByte, 1);   /* ดักรับ byte ถัดไป */
    }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef* huart)
{
    if (huart->Instance == UART4)
    {
        /* เคลียร์ error (เช่น overrun) แล้วดักรับต่อ ไม่ให้สายหลุดถาวร */
        HAL_UART_Receive_IT(&huart4, &rxByte, 1);
    }
}

/* Interrupt vector — เรียกจาก stm32h7rsxx_it.c */
void UART4_IRQHandler(void)
{
    HAL_UART_IRQHandler(&huart4);
}
