#ifndef MODELLISTENER_HPP
#define MODELLISTENER_HPP

class ModelListener
{
public:
    virtual ~ModelListener() {}

    // รับข้อมูลจาก Model ส่งต่อไปให้ Presenter
    // (target = เป้าหมายชิ้นงาน, pitch = ระยะพิตช์ mm — ซิงค์สองทางกับเว็บ 3D Twin)
    virtual void onWebDataUpdated(int pieces, const char* stateName, int temp,
                                  const char* statusText, const char* alarmText,
                                  int target, int pitch) {}

    // 🎥 สเต็ป VISION: gateway หยุดรอ operator กด PASS/NG อยู่ (คีย์ step_allowed ใน payload)
    // หน้าจอที่สนใจค่อย override เอง — หน้าอื่นใช้ตัวว่างนี้ได้เลย
    virtual void onVisionGateChanged(bool waitingForOperator) {}
};

#endif // MODELLISTENER_HPP
