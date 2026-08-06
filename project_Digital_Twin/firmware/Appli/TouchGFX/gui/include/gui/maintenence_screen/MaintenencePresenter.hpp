#ifndef MAINTENENCEPRESENTER_HPP
#define MAINTENENCEPRESENTER_HPP

#include <gui/model/ModelListener.hpp>
#include <mvp/Presenter.hpp>

using namespace touchgfx;

class MaintenenceView;
class Model;

class MaintenencePresenter : public touchgfx::Presenter, public ModelListener
{
public:
    MaintenencePresenter(MaintenenceView& v);

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

    virtual ~MaintenencePresenter() {}

private:
    MaintenencePresenter();

    MaintenenceView& view;
    Model* model = nullptr;
};

#endif // MAINTENENCEPRESENTER_HPP
