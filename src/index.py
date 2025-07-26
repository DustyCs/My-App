import os
import sys
import json
import threading
import time
import requests # type: ignore

from kivy.app import App # type: ignore
from kivy.clock import Clock # type: ignore
from kivy.core.window import Window # type: ignore
from kivy.uix.boxlayout import BoxLayout # type: ignore
from kivy.uix.scrollview import ScrollView # type: ignore
from kivy.uix.textinput import TextInput # type: ignore
from kivy.uix.button import Button # type: ignore
from kivy.uix.label import Label # type: ignore
from kivy.graphics import Color, RoundedRectangle # type: ignore

try:
    from playsound import playsound # type: ignore
    SOUND_BACKEND = "playsound"
except ImportError:
    from plyer import audio # type: ignore
    SOUND_BACKEND = "plyer"

# —————————————————————————————————————————————————————————————————————————
# CONFIG
# —————————————————————————————————————————————————————————————————————————
ALARM_URL      = "http://localhost:5000/api/app-alarm"
ALARM_SOUND    = "alarm.mp3"     # your audio file
POLL_INTERVAL  = 10              # in seconds
REFRESH_PERIOD = 60              # in seconds

# simulate phone‑size for desktop preview
Window.size = (360, 640)


# —————————————————————————————————————————————————————————————————————————
# A little “Card” widget via canvas
# —————————————————————————————————————————————————————————————————————————
class CardBox(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=12, spacing=8, **kwargs)
        with self.canvas.before:
            Color(rgba=(1,1,1,0.1))
            self._bg = RoundedRectangle(radius=[10], pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

    def _upd_bg(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


# —————————————————————————————————————————————————————————————————————————
# Main layout
# —————————————————————————————————————————————————————————————————————————
class AlarmLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=16, spacing=12, **kwargs)
        self.app_id     = self._load_app_id()
        self._refresh_ev= None

        # we'll build UI once, below
        if self.app_id:
            self._build_main_view()
        else:
            self._build_id_view()


    # — ID ENTRY ———————————————————————————————————————————————
    def _build_id_view(self):
        self.clear_widgets()
        self.status = Label(text="Enter your App ID", size_hint_y=None, height=30)
        self.add_widget(self.status)

        self.input_box = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.app_id_in = TextInput(hint_text="abcd-1234-efgh", multiline=False)
        self.input_box.add_widget(self.app_id_in)
        btn = Button(text="Start", background_color=(0.2,0.6,1,1))
        btn.bind(on_press=self._on_submit)
        self.input_box.add_widget(btn)

        self.add_widget(self.input_box)


    def _on_submit(self, _):
        val = self.app_id_in.text.strip()
        if not val:
            self.status.text = "Please enter an ID"
        elif self._validate_id(val):
            self.app_id = val
            self._save_app_id(val)
            self._build_main_view()
        else:
            self.status.text = "Invalid ID"


    # — MAIN ALARM + SCHEDULE DISPLAY —————————————————————————————————————————
    def _build_main_view(self):
        self.clear_widgets()
        self.status = Label(text=f"Alarm Active (ID: {self.app_id})", size_hint_y=None, height=30)
        self.add_widget(self.status)

        # Reset
        r = Button(text="Reset ID", size_hint_y=None, height=40, background_color=(1,0.4,0.3,1))
        r.bind(on_press=self._on_reset)
        self.add_widget(r)

        # Scrollable “card”
        self.card_scroll = ScrollView(size_hint=(1,None), size=(self.width, self.height*0.6))
        card = CardBox(size_hint_y=None)
        card.bind(minimum_height=card.setter('height'))

        self.card_content = Label(
            text="Loading this week…",
            markup=True,
            size_hint_y=None,
            height=100,
            valign='top'
        )
        self.card_content.bind(
            texture_size=lambda inst,ts: setattr(inst, 'height', ts[1])
        )

        card.add_widget(self.card_content)
        self.card_scroll.add_widget(card)
        self.add_widget(self.card_scroll)

        # start polling & refreshing
        Clock.schedule_once(lambda dt: self._start_polling(), 0)
        Clock.schedule_once(lambda dt: self._refresh_schedule(), 0)
        self._start_auto_refresh()


    # — VALIDATION & PERSISTENCE —————————————————————————————————————————
    def _validate_id(self, app_id):
        try:
            r = requests.get(f"{ALARM_URL}/validate/{app_id}")
            return r.status_code==200 and r.json().get("valid") is True
        except:
            return False

    def _settings_path(self):
        return os.path.join(App.get_running_app().user_data_dir, "settings.json")

    def _save_app_id(self, app_id):
        with open(self._settings_path(), "w") as f:
            json.dump({"app_id":app_id}, f)

    def _load_app_id(self):
        p = self._settings_path()
        if os.path.exists(p):
            try:
                return json.load(open(p)).get("app_id")
            except:
                return None
        return None

    def _on_reset(self, _):
        try: os.remove(self._settings_path())
        except: pass
        App.get_running_app().stop()
        os.execl(sys.executable, sys.executable, *sys.argv)


    # — ALARM POLLING —————————————————————————————————————————————————
    def _start_polling(self):
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def _poll_loop(self):
        while True:
            try:
                r = requests.get(f"{ALARM_URL}/appId/{self.app_id}")
                if r.status_code==200 and r.json().get("trigger"):
                    threading.Thread(target=self._play_sound, daemon=True).start()
            except Exception as e:
                print("Poll error:", e)
            time.sleep(POLL_INTERVAL)

    def _play_sound(self):
        if SOUND_BACKEND=="playsound":
            playsound(ALARM_SOUND)
        else:
            try: audio.player.play(ALARM_SOUND)
            except: pass


    # — WEEKLY REFRESH —————————————————————————————————————————————————
    def _refresh_schedule(self):
        try:
            s = requests.get(f"http://localhost:5000/api/schedules/current-week/{self.app_id}").json()
            a = requests.get(f"http://localhost:5000/api/activities/current-week/{self.app_id}").json()
            lines = []
            if s:
                lines.append("[b]Schedules[/b]")
                for e in s:
                    lines.append(f"• {e['title']} on {e['date']}")
            if a:
                lines.append("\n[b]Activities[/b]")
                for e in a:
                    lines.append(f"• {e['activityType']} on {e['date']}")
            if not s and not a:
                lines = ["No upcoming items"]
            self.card_content.text = "\n".join(lines)
        except Exception as e:
            print("Refresh error:", e)
            self.card_content.text = "Could not fetch data"

    def _start_auto_refresh(self):
        if self._refresh_ev:
            self._refresh_ev.cancel()
        self._refresh_ev = Clock.schedule_interval(lambda dt: self._refresh_schedule(), REFRESH_PERIOD)


class AlarmApp(App):
    def build(self):
        return AlarmLayout()


if __name__=="__main__":
    AlarmApp().run()
