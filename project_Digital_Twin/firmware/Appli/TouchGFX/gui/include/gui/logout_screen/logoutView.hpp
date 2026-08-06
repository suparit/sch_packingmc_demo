#ifndef LOGOUTVIEW_HPP
#define LOGOUTVIEW_HPP

#include <gui_generated/logout_screen/logoutViewBase.hpp>
#include <gui/logout_screen/logoutPresenter.hpp>

class logoutView : public logoutViewBase
{
public:
    logoutView();
    virtual ~logoutView() {}
    virtual void setupScreen();
    virtual void tearDownScreen();
protected:
};

#endif // LOGOUTVIEW_HPP
