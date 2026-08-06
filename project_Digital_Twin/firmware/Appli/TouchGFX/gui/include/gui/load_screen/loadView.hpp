#ifndef LOADVIEW_HPP
#define LOADVIEW_HPP

#include <gui_generated/load_screen/loadViewBase.hpp>
#include <gui/load_screen/loadPresenter.hpp>

class loadView : public loadViewBase
{
public:
    loadView();
    virtual ~loadView() {}
    virtual void setupScreen();
    virtual void tearDownScreen();

    // เดินแถบโหลด 0-100% แล้วเข้าหน้า Login อัตโนมัติ
    virtual void handleTickEvent();

protected:
    int tickCounter = 0;
    int lastPercent = -1;   // -1 = ยังไม่เคยวาด บังคับให้วาดครั้งแรกเสมอ

    void showPercent(int percent);
};

#endif // LOADVIEW_HPP
