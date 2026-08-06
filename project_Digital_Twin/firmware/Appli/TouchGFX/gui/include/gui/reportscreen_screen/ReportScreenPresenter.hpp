#ifndef REPORTSCREENPRESENTER_HPP
#define REPORTSCREENPRESENTER_HPP

#include <gui/model/ModelListener.hpp>
#include <mvp/Presenter.hpp>

using namespace touchgfx;

class ReportScreenView;
class Model; // Forward declaration ของ Model ฝั่งโปรเจกต์

class ReportScreenPresenter : public touchgfx::Presenter, public ModelListener
{
public:
    ReportScreenPresenter(ReportScreenView& v)
        : view(v), model(0)
    {}

    /**
     * Binds the presenter to the model.
     */
    void bind(Model* m)
    {
        model = m;
    }

    virtual void activate() {}
    virtual void deactivate() {}

    virtual ~ReportScreenPresenter() {}

private:
    ReportScreenPresenter();

    ReportScreenView& view;
    Model* model;
};

#endif // REPORTSCREENPRESENTER_HPP
