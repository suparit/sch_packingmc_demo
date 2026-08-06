#ifndef LOGINSCREENPRESENTER_HPP
#define LOGINSCREENPRESENTER_HPP

#include <gui/model/ModelListener.hpp>
#include <mvp/Presenter.hpp>

using namespace touchgfx;

class LoginScreenView;
class Model;

class LoginScreenPresenter : public touchgfx::Presenter, public ModelListener
{
public:
    LoginScreenPresenter(LoginScreenView& v);

    // framework เรียกตอนสลับหน้าจอ เพื่อผูก Presenter เข้ากับ Model กลาง
    void bind(Model* m)
    {
        model = m;
    }

    /**
     * The activate function is called automatically when this screen is "switched in"
     * (ie. made active). Initialization logic can be placed here.
     */
    virtual void activate();

    /**
     * The deactivate function is called automatically when this screen is "switched out"
     * (ie. made inactive). Teardown functionality can be placed here.
     */
    virtual void deactivate();

    virtual ~LoginScreenPresenter() {}

private:
    LoginScreenPresenter();

    LoginScreenView& view;
    Model* model = nullptr;
};

#endif // LOGINSCREENPRESENTER_HPP
