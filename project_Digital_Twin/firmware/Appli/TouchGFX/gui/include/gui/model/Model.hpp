#ifndef MODEL_HPP
#define MODEL_HPP

#include <stdint.h>

class ModelListener;

class Model
{
public:
    Model();

    void bind(ModelListener* listener)
    {
        modelListener = listener;
    }

    void tick();

    // ฟังก์ชันส่งคำสั่งไป Python
    void sendActionToGateway(const char* action);

    // Getters สำหรับส่งค่าให้ Presenter
    const char* getFsmState() { return currentState; }
    uint16_t getTempLeft() { return tempLeft; }
    uint16_t getTempRight() { return tempRight; }
    uint32_t getActualPcs() { return actualPcs; }
    uint32_t getTargetPcs() { return targetPcs; }
    float getCycleTime() { return cycleTime; }
    uint16_t getPitch() { return pitchMm; }

private:
    ModelListener* modelListener;

    // แกะ payload JSON 1 บรรทัด (จาก TCP บน Simulator / จาก UART บนบอร์ดจริง) แล้วส่งขึ้น UI
    void processPayloadLine(char* recvbuf);

    // ข้อมูลระบบ NEXCORE (จำลองข้อมูลสด)
    char currentState[32];
    uint16_t tempLeft;
    uint16_t tempRight;
    uint32_t actualPcs;
    uint32_t targetPcs;
    float cycleTime;
    uint16_t pitchMm;
    
    uint16_t tickCounter;
};

#endif // MODEL_HPP