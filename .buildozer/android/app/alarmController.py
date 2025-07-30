from alarmModel import *
import threading
import os
import sys
import json
import time
from kivy.clock import Clock # type: ignore
from kivy.app import App # type: ignore

try:
    from playsound import playsound # type: ignore
    SOUND_BACKEND = "playsound"
except ImportError:
    from plyer import audio # type: ignore
    SOUND_BACKEND = "plyer"

class AlarmController:
    def __init__(self, view):
        self.view = view
        self.model = None
        self.app_id = None
    def on_start(self, _):
        aid = self.view.app_id_in.text.strip()
        if not aid: self.view.show_id_view("Please enter ID"); return
        self.model = AlarmModel(aid)
        if not self.model.validate(): self.view.show_id_view("Invalid ID"); return
        self.app_id=aid; self._save(aid)
        self.view.show_main_view(aid)
        Clock.schedule_once(lambda dt: self._start(),0)
    def _start(self):
        Clock.schedule_interval(lambda dt: self._refresh(), REFRESH_PERIOD)
        threading.Thread(target=self._poll_loop, daemon=True).start()
        self._refresh()
    def _poll_loop(self):
        while True:
            trigger, item = self.model.poll()
            if trigger:
                threading.Thread(target=playsound, args=(ALARM_SOUND,), daemon=True).start()
            time.sleep(POLL_INTERVAL)
    def _refresh(self):
        s,a=self.model.fetch_week()
        self.view.render_schedule(s,a)
    def on_reset(self, _):
        try: os.remove(self._path())
        except: pass; App.get_running_app().stop(); os.execl(sys.executable, sys.executable, *sys.argv)
    def _path(self): return os.path.join(App.get_running_app().user_data_dir, 'settings.json')
    def _save(self, aid): json.dump({'app_id':aid}, open(self._path(),'w'))
    def load(self):
        p=self._path()
        if os.path.exists(p):
            aid=json.load(open(p)).get('app_id')
            if aid: self.app_id=aid; self.model=AlarmModel(aid); self.view.show_main_view(aid); Clock.schedule_once(lambda dt: self._start(),0)