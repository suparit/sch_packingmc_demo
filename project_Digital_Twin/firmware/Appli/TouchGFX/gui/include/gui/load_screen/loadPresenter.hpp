#ifndef LOADPRESENTER_HPP
#define LOADPRESENTER_HPP

#include <gui/model/ModelListener.hpp>
#include <mvp/Presenter.hpp>

using namespace touchgfx;

class loadView;
class Model;

class loadPresenter : public touchgfx::Presenter, public ModelListener
{
public:
    loadPresenter(loadView& v);

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

    virtual ~loadPresenter() {}

private:
    loadPresenter();

    loadView& view;
    Model* model = nullptr;
};

#endif // LOADPRESENTER_HPP
