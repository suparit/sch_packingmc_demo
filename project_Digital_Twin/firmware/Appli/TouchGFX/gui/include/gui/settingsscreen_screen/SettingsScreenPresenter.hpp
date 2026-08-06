#ifndef SETTINGSSCREENPRESENTER_HPP
#define SETTINGSSCREENPRESENTER_HPP

#include <gui/model/ModelListener.hpp>
#include <mvp/Presenter.hpp>

using namespace touchgfx;

class SettingsScreenView;
class Model;

class SettingsScreenPresenter : public touchgfx::Presenter, public ModelListener
{
public:
    SettingsScreenPresenter(SettingsScreenView& v);

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

    virtual ~SettingsScreenPresenter() {}

private:
    SettingsScreenPresenter();

    SettingsScreenView& view;
    Model* model = nullptr;
};

#endif // SETTINGSSCREENPRESENTER_HPP
