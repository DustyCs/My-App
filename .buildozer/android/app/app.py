from alarmView import *
from alarmController import *

class AlarmApp(App):
    def build(self):
        view=AlarmView(None)
        ctrl=AlarmController(view)
        view.ctrl=ctrl
        ctrl.load()
        return view

if __name__=='__main__': AlarmApp().run()