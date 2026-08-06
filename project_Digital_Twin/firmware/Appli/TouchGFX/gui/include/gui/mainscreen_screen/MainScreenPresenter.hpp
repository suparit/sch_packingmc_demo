#ifndef MAINSCREENPRESENTER_HPP
#define MAINSCREENPRESENTER_HPP

#include <gui/model/ModelListener.hpp>
#include <mvp/Presenter.hpp>

using namespace touchgfx;

class MainScreenView;
class Model;

class MainScreenPresenter : public touchgfx::Presenter, public ModelListener
{
public:
    MainScreenPresenter(MainScreenView& v);

    virtual void activate();
    virtual void deactivate();

    virtual ~MainScreenPresenter() {}

    void bind(Model* m)
    {
        model = m;
    }

    virtual void onWebDataUpdated(int pieces, const char* stateName, int temp,
                                  const char* statusText, const char* alarmText,
                                  int target, int pitch);

    virtual void onVisionGateChanged(bool waitingForOperator);

private:
    MainScreenPresenter();
    MainScreenView& view;
    Model* model;
};

#endif // MAINSCREENPRESENTER_HPP