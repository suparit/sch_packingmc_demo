#ifndef MAINTENENCEVIEW_HPP
#define MAINTENENCEVIEW_HPP

#include <gui_generated/maintenence_screen/MaintenenceViewBase.hpp>
#include <gui/maintenence_screen/MaintenencePresenter.hpp>

class MaintenenceView : public MaintenenceViewBase
{
public:
    MaintenenceView();
    virtual ~MaintenenceView() {}
    virtual void setupScreen();
    virtual void tearDownScreen();
protected:
};

#endif // MAINTENENCEVIEW_HPP
