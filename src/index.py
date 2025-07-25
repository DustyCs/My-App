import os
import sys
import json
import threading
import time
import requests

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label

from kivy.uix.boxlayout import BoxLayout
from kivy.graphics import Color, RoundedRectangle

try:
    from playsound import playsound
    SOUND_BACKEND = "playsound"
except ImportError:
    from plyer import audio
    SOUND_BACKEND = "plyer"

# —————————————————————————————————————————————————————————————————————————
# CONFIG
# —————————————————————————————————————————————————————————————————————————
ALARM_URL      = "http://localhost:5000/api/app-alarm"
SETTINGS_FILE  = "settings.json"
ALARM_SOUND    = "alarm.mp3"   # your audio file
POLL_INTERVAL  = 10             # in seconds
REFRESH_PERIOD = 60             # in seconds

# make window phone‑sized for preview
Window.size = (360, 640)

# —————————————————————————————————————————————————————————————————————————
# BoxLayout
# —————————————————————————————————————————————————————————————————————————
class CardBox(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=12, spacing=8, **kwargs)
        # draw a light “card” background behind us
        with self.canvas.before:
            Color(rgba=(1, 1, 1, 0.1))  # white at 10% opacity
            self._bg = RoundedRectangle(radius=[10], pos=self.pos, size=self.size)
        # keep rectangle in sync
        self.bind(pos=self._update_bg, size=self._update_bg)

    def _update_bg(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size


# —————————————————————————————————————————————————————————————————————————
# MAIN LAYOUT
# —————————————————————————————————————————————————————————————————————————
class AlarmLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=16, spacing=12, **kwargs)

        # load App ID if saved
        self.app_id       = self._load_app_id()
        self._refresh_ev  = None

        # status at top
        self.status_label = Label(text="", size_hint_y=None, height=30)
        self.add_widget(self.status_label)

        if self.app_id:
            self._enter_main_flow()
        else:
            self._enter_id_flow()

    # — ID ENTRY VIEW ———————————————————————————————————————————————
    def _enter_id_flow(self):
        self.clear_widgets()
        self.add_widget(self.status_label)

        # bright header
        self.add_widget(Label(text="🎯 Enter your App ID", font_size=20, size_hint_y=None, height=40))

        self.id_box = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.app_id_input = TextInput(hint_text="abcd-1234-efgh...", multiline=False)
        self.id_box.add_widget(self.app_id_input)
        btn = Button(text="🚀 Start", background_color=(0.2,0.6,1,1))
        btn.bind(on_press=self._on_submit_id)
        self.id_box.add_widget(btn)
        self.add_widget(self.id_box)

    def _on_submit_id(self, _):
        val = self.app_id_input.text.strip()
        if not val:
            self.status_label.text = "❗ Please enter something"
            return
        if self._validate_id(val):
            self.app_id = val
            self._save_app_id(val)
            self.status_label.text = "✅ ID accepted!"
            self._enter_main_flow()
        else:
            self.status_label.text = "❌ Invalid ID"

    # — MAIN VIEW —————————————————————————————————————————————————
    def _enter_main_flow(self):
        self.clear_widgets()
        self.add_widget(self.status_label)
        self.add_widget(Label(text=f"🔔 Alarm Active (ID: {self.app_id})",
                              font_size=16, size_hint_y=None, height=30))

        # Reset button
        reset = Button(text="♻️ Reset App ID",
                       size_hint_y=None, height=40,
                       background_color=(1,0.4,0.3,1))
        reset.bind(on_press=self._on_reset)
        self.add_widget(reset)

        # ─── scrollable card area ──────────────────────────────────────────
        # 1) create a ScrollView container
        self.card_scroll = ScrollView(size_hint=(1, None),
                                      size=(self.width, self.height * 0.6))
        # 2) inside it, put our CardBox
        card = CardBox(size_hint_y=None)
        # allow the card to grow vertically to fit its children
        card.bind(minimum_height=card.setter('height'))

        # 3) your Label goes inside the CardBox
        self.card_content = Label(
            text="⏳ Fetching week…",
            markup=True,
            size_hint_y=None,
            height=100,
            valign='top'
        )
        # make the label grow as text changes
        self.card_content.bind(
            texture_size=lambda inst, ts: setattr(inst, 'height', ts[1])
        )

        card.add_widget(self.card_content)
        self.card_scroll.add_widget(card)
        self.add_widget(self.card_scroll)
        # ───────────────────────────────────────────────────────────────────

        # kick off polling + refresh
        Clock.schedule_once(lambda dt: self._start_polling(), 0)
        Clock.schedule_once(lambda dt: self._refresh_schedule(), 0)
        self._start_auto_refresh()


    # — VALIDATION & SETTINGS ———————————————————————————————————————
    def _validate_id(self, app_id):
        try:
            r = requests.get(f"{ALARM_URL}/validate/{app_id}")
            return r.status_code==200 and r.json().get("valid") is True
        except Exception:
            return False

    def _save_app_id(self, app_id):
        with open(SETTINGS_FILE, "w") as f:
            json.dump({"app_id":app_id}, f)

    def _load_app_id(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                return json.load(open(SETTINGS_FILE)).get("app_id")
            except:
                return None
        return None

    def _on_reset(self, _):
        if os.path.exists(SETTINGS_FILE):
            os.remove(SETTINGS_FILE)
        # restart to clear state
        App.get_running_app().stop()
        os.execl(sys.executable, sys.executable, *sys.argv)

    # — POLLING ALARM —————————————————————————————————————————————————
    def _start_polling(self):
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def _poll_loop(self):
        while True:
            try:
                r = requests.get(f"{ALARM_URL}/appId/{self.app_id}")
                if r.status_code==200 and r.json().get("trigger"):
                    # play sound
                    threading.Thread(target=self._play_sound, daemon=True).start()
            except Exception as e:
                print("Poll err:", e)
            time.sleep(POLL_INTERVAL)

    def _play_sound(self):
        if SOUND_BACKEND=="playsound":
            playsound(ALARM_SOUND)
        else:
            try: audio.player.play(ALARM_SOUND)
            except: pass

    # — REFRESH SCHEDULE —————————————————————————————————————————————————
    def _refresh_schedule(self):
        try:
            s = requests.get(f"http://localhost:5000/api/schedules/current-week/{self.app_id}").json()
            a = requests.get(f"http://localhost:5000/api/activities/current-week/{self.app_id}").json()
            lines = []
            if s:
                lines.append("[b]📅 Schedules[/b]")
                for e in s:
                    lines.append(f"• {e.get('title')} @ {e.get('date')}")
            if a:
                lines.append("\n[b]🎽 Activities[/b]")
                for e in a:
                    lines.append(f"• {e.get('activityType')} @ {e.get('date')}")
            if not s and not a:
                lines = ["(No upcoming items)"]
            self.card_content.text = "\n".join(lines)
        except Exception as e:
            self.card_content.text = "⚠️ Could not fetch data"
            print("Refresh err:", e)

    def _start_auto_refresh(self):
        if self._refresh_ev:
            self._refresh_ev.cancel()
        self._refresh_ev = Clock.schedule_interval(lambda dt: self._refresh_schedule(), REFRESH_PERIOD)


# —————————————————————————————————————————————————————————————————————————
class AlarmApp(App):
    def build(self):
        return AlarmLayout()


if __name__=="__main__":
    AlarmApp().run()
