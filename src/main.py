import os
import sys
import json
import threading
import time
from jnius import autoclass 
from android import AndroidService
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
from kivy.uix.anchorlayout import AnchorLayout # type: ignore
from kivy.uix.popup import Popup # type: ignore
from kivy.utils import platform # type: ignore
from kivy.core.audio import SoundLoader # type: ignore
from kivy.storage.jsonstore import JsonStore # type: ignore
from kivy.uix.slider import Slider # type: ignore
from kivy.logger import Logger # type: ignore
from pathlib import Path

from plyer import audio, vibrator # type: ignore

# CONFIG
POLL_INTERVAL  = 10
REFRESH_PERIOD = 60
HERE = os.path.dirname(__file__)
ALARM_SOUND = os.path.join(HERE, "fixed-alarm.wav")
BACKEND_URLS = ["https://mern-lifetime.onrender.com/api"]

if platform == 'android':
    from android.storage import app_storage_path
    store_path = Path(app_storage_path()) / "settings.json"
else:
    store_path = Path("settings.json")

store = JsonStore(str(store_path))

Window.clearcolor = (1, 1, 1, 1)

# CardBox
class CardBox(BoxLayout):
    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", 12)
        kwargs.setdefault("spacing", 8)
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.rect = RoundedRectangle(radius=[12])
        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

# AlarmLayout
class AlarmLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=0, spacing=12, **kwargs)
        self.app_id = self._load_app_id()
        self._refresh_ev = None
        self.alarm_triggered = False
        self.volume = store.get("audio")["volume"] if store.exists("audio") else 1.0
        if self.app_id:
            self._build_main_view()
        else:
            self._build_id_view()

    def _build_id_view(self):
        self.clear_widgets()
        container = AnchorLayout(anchor_x='center', anchor_y='center')
        card = BoxLayout(orientation='vertical', padding=20, spacing=12,
                        size_hint=(0.8, None), height=200)
        with card.canvas.before:
            Color(rgba=(0, 0, 0, 0.15))
            self._shadow_rect = RoundedRectangle(radius=[20])
            Color(rgba=(1, 0.3, 0.25, 1))
            self._bg_rect = RoundedRectangle(radius=[20])
        card.bind(pos=self._update_card_bg, size=self._update_card_bg)
        self.status = Label(text="Enter your App ID", size_hint_y=None, height=40,
                            color=(1,1,1,1), bold=True, font_size='18sp')
        card.add_widget(self.status)
        row = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.app_id_in = TextInput(hint_text="abcd-1234-efgh", multiline=False,
                                background_color=(1,1,1,1), foreground_color=(0,0,0,1),
                                padding=(10, 10), font_size='16sp')
        row.add_widget(self.app_id_in)
        btn = Button(text="Start", size_hint_x=None, width=100,
                    background_color=(1,1,1,1), color=(1,0.3,0.25,1),
                    background_normal='', font_size='16sp')
        btn.bind(on_press=self._on_submit)
        row.add_widget(btn)
        card.add_widget(row)
        container.add_widget(card)
        self.add_widget(container)

    def _update_card_bg(self, instance, _):
        self._shadow_rect.pos = (instance.x - 5, instance.y - 5)
        self._shadow_rect.size = (instance.width + 10, instance.height + 10)
        self._bg_rect.pos = instance.pos
        self._bg_rect.size = instance.size

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

    def _build_main_view(self):
        self.clear_widgets()
        header = BoxLayout(orientation='vertical', size_hint_y=None, height=100, padding=(10, 10))
        with header.canvas.before:
            Color(1, 0.3, 0.25, 1)
            self._header_bg = RoundedRectangle(pos=header.pos, size=header.size, radius=[0, 0, 20, 20])
        header.bind(pos=self._update_header_bg, size=self._update_header_bg)
        header.add_widget(Label(text="Alarm Active", font_size='24sp', bold=True, color=(1, 1, 1, 1)))
        header.add_widget(Label(text=f"(ID: {self.app_id})", font_size='16sp', color=(1, 1, 1, 1)))
        self.add_widget(header)
        self.card_scroll = ScrollView(size_hint=(1, 1))
        self.card_box = CardBox(size_hint_y=None, padding=16, spacing=12)
        self.card_box.bind(minimum_height=self.card_box.setter('height'))
        self.card_scroll.add_widget(self.card_box)
        self.add_widget(self.card_scroll)
        reset = Button(text="Reset ID", size_hint_y=None, height=50,
                       background_color=(1, 0.3, 0.25, 1), color=(1, 1, 1, 1), background_normal='')
        reset.bind(on_press=self._confirm_reset)
        self.add_widget(reset)
        settings = Button(text="Volume Settings", size_hint_y=None, height=50,
                          background_color=(1, 0.3, 0.25, 1), color=(1, 1, 1, 1), background_normal='')
        settings.bind(on_press=self.open_volume_settings)
        self.add_widget(settings)
        Clock.schedule_once(lambda dt: self._start_polling(), 0)
        Clock.schedule_once(lambda dt: self._refresh_schedule(), 0)
        self._start_auto_refresh()

    def _update_header_bg(self, instance, _):
        self._header_bg.pos = instance.pos
        self._header_bg.size = instance.size

    def create_card(self, title, subtitle):
        card = BoxLayout(orientation='vertical', padding=12, spacing=6, size_hint_y=None, height=100)
        with card.canvas.before:
            Color(1, 1, 1, 1)
            rect = RoundedRectangle(radius=[16])
        card.bind(pos=lambda inst, _: setattr(rect, 'pos', inst.pos))
        card.bind(size=lambda inst, _: setattr(rect, 'size', inst.size))
        card.add_widget(Label(text=title, font_size='16sp', bold=True, color=(0.1, 0.1, 0.1, 1), size_hint_y=None, height=30))
        card.add_widget(Label(text=subtitle, font_size='14sp', color=(0.3, 0.3, 0.3, 1), size_hint_y=None, height=20))
        return card

    def open_volume_settings(self, _):
        card = BoxLayout(orientation='vertical', spacing=20, padding=20, size_hint=(0.8, None), height=250)
        with card.canvas.before:
            Color(0, 0, 0, 0.15)
            shadow = RoundedRectangle(radius=[16])
            Color(1, 1, 1, 1)
            bg = RoundedRectangle(radius=[16])
        card.bind(pos=lambda inst, _: setattr(shadow, 'pos', (inst.x-5, inst.y-5)))
        card.bind(size=lambda inst, _: setattr(shadow, 'size', (inst.width+10, inst.height+10)))
        card.bind(pos=lambda inst, _: setattr(bg, 'pos', inst.pos))
        card.bind(size=lambda inst, _: setattr(bg, 'size', inst.size))
        header = Label(text="🔊 Set Alarm Volume", size_hint=(1, None), height=40,
                       font_size='18sp', bold=True, color=(1, 0.3, 0.25, 1))
        card.add_widget(header)
        slider = Slider(min=0.0, max=1.0, value=self.volume, size_hint=(1, None), height=40)
        card.add_widget(slider)
        btn_row = BoxLayout(size_hint=(1, None), height=50, spacing=10)
        save_btn = Button(text="Save", background_color=(1, 0.3, 0.25, 1), color=(1,1,1,1), bold=True)
        cancel_btn = Button(text="Cancel", background_color=(0.8, 0.8, 0.8, 1), color=(0,0,0,1))
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(save_btn)
        card.add_widget(btn_row)
        popup = Popup(title="", content=card, size_hint=(None, None), size=(Window.width*0.9, 300), auto_dismiss=False, background='')
        save_btn.bind(on_release=lambda *_: (setattr(self, 'volume', slider.value), store.put("audio", volume=slider.value), popup.dismiss()))
        cancel_btn.bind(on_release=popup.dismiss)
        popup.open()

    def _confirm_reset(self, _):
        card = BoxLayout(orientation='vertical', spacing=20, padding=20, size_hint=(0.8, None), height=200)
        with card.canvas.before:
            Color(0, 0, 0, 0.15)
            shadow = RoundedRectangle(radius=[16])
            Color(1, 1, 1, 1)
            bg = RoundedRectangle(radius=[16])
        card.bind(pos=lambda inst, _: setattr(shadow, 'pos', (inst.x-5, inst.y-5)))
        card.bind(size=lambda inst, _: setattr(shadow, 'size', (inst.width+10, inst.height+10)))
        card.bind(pos=lambda inst, _: setattr(bg, 'pos', inst.pos))
        card.bind(size=lambda inst, _: setattr(bg, 'size', inst.size))
        card.add_widget(Label(text="⚠️ Reset App ID?", size_hint=(1, None), height=40,
                              font_size='18sp', bold=True, color=(1, 0.3, 0.25, 1), halign='center'))
        btn_row = BoxLayout(size_hint=(1, None), height=50, spacing=10)
        yes = Button(text="Yes", background_color=(1, 0.3, 0.25, 1), color=(1,1,1,1), bold=True)
        no = Button(text="No", background_color=(0.8,0.8,0.8,1), color=(0,0,0,1))
        btn_row.add_widget(no)
        btn_row.add_widget(yes)
        card.add_widget(btn_row)
        popup = Popup(title="", content=card, size_hint=(None, None), size=(Window.width*0.8, 220), auto_dismiss=False, background='')
        no.bind(on_release=popup.dismiss)
        yes.bind(on_release=lambda *_: (popup.dismiss(), self._on_reset(None)))
        popup.open()

    def _validate_id(self, app_id):
        try:
            r = call_backend(f"/app-alarm/validate/{app_id}")
            return r.status_code == 200 and r.json().get("valid") is True
        except Exception as e:
            Logger.warning(f"Validation failed: {e}")
            return False

    def _settings_path(self):
        path = Path(App.get_running_app().user_data_dir) / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _save_app_id(self, app_id):
        with open(self._settings_path(), "w") as f:
            json.dump({"app_id": app_id}, f)

    def _load_app_id(self):
        p = self._settings_path()
        if os.path.exists(p):
            try:
                return json.load(open(p)).get("app_id")
            except Exception as e:
                Logger.warning(f"Load ID failed: {e}")
        return None

    def _on_reset(self, _):
        try:
            os.remove(self._settings_path())
        except Exception:
            pass
        App.get_running_app().stop()
        if platform != 'android':
            os.execl(sys.executable, sys.executable, *sys.argv)

    def _start_polling(self):
        Clock.schedule_interval(self._poll_once, POLL_INTERVAL)

    def _do_poll(self):
        try:
            r = call_backend(f"/app-alarm/appId/{self.app_id}")
            data = r.json() if r.status_code == 200 else {}
            if data.get("trigger") and not self.alarm_triggered:
                self.alarm_triggered = True
                item = data["item"]

                # Service will handle sound/vibration
                Clock.schedule_once(lambda dt: self.show_alarm(item), 0)

                Clock.schedule_once(lambda dt: setattr(self, 'alarm_triggered', False), 60)
                threading.Thread(target=lambda: call_backend(
                    f"/app-alarm/mobile/alarms/{item['_id']}/acknowledge",
                    method="POST",
                    json={"type": data["source"]}
                ), daemon=True).start()

        except Exception as e:
            Logger.warning(f"Poll error: {e}")

    def _poll_once(self, dt):
        threading.Thread(target=self._do_poll, daemon=True).start()

    def show_alarm(self, item):
        title = item.get("title", "Alarm")
        date = item.get("date", "")
        content = BoxLayout(orientation="vertical", padding=20, spacing=20)
        content.add_widget(Label(text=f"[b]{title}[/b]\n{date}", markup=True, halign='center'))
        btn = Button(text="Dismiss", size_hint_y=None, height="48dp",
                     background_color=(1, 0.3, 0.25, 1), color=(1, 1, 1, 1), background_normal='', bold=True)
        content.add_widget(btn)
        popup = Popup(title="⏰ Alarm!", content=content, size_hint=(.85, .4), background='atlas://data/images/defaulttheme/button_pressed', auto_dismiss=False)
        btn.bind(on_press=lambda *_: (popup.dismiss(), setattr(self, 'alarm_triggered', False)))
        popup.open()

    # def _play_sound(self):
    #     if not os.path.exists(ALARM_SOUND):
    #         Logger.warning("Alarm sound file missing")
    #         return
    #     sound = SoundLoader.load(ALARM_SOUND)
    #     if sound:
    #         sound.volume = self.volume
    #         sound.play()
    #     elif platform == "android":
    #         try:
    #             audio.source = ALARM_SOUND
    #             audio.play()
    #         except Exception:
    #             Logger.warning("Audio: plyer.audio failed")
    #     if platform == "android":
    #         try:
    #             vibrator.vibrate(1.0)
    #         except Exception:
    #             Logger.warning("Vibration failed")
    def _play_sound(self):
        """
        Now handled in background service.
        Main app no longer plays audio or vibration directly
        to avoid double playback.
        """
        if platform != "android":
            # On desktop or dev mode, still play locally for testing
            if not os.path.exists(ALARM_SOUND):
                Logger.warning("Alarm sound file missing")
                return
            sound = SoundLoader.load(ALARM_SOUND)
            if sound:
                sound.volume = self.volume
                sound.play()

    def _refresh_schedule(self):
        self.card_box.clear_widgets()
        try:
            s = {}
            a = {}
            try:
                s = call_backend(f"/schedules/current-week/{self.app_id}", method="get").json()
            except Exception as e:
                print("Schedule fetch failed:", e)

            try:
                a = call_backend(f"/activities/current-week/{self.app_id}", method="get").json()
            except Exception as e:
                print("Activities fetch failed:", e)

            if s:
                self.card_box.add_widget(Label(
                    text="Schedules", color=(1, 0.3, 0.25, 1),
                    font_size='18sp', bold=True, size_hint_y=None, height=30))
                for e in s:
                    self.card_box.add_widget(self.create_card(
                        e.get('title', 'Untitled'),
                        e.get('date', 'No date')
                    ))

            if a:
                self.card_box.add_widget(Label(
                    text="Activities", color=(1, 0.3, 0.25, 1),
                    font_size='18sp', bold=True, size_hint_y=None, height=30))
                for e in a:
                    self.card_box.add_widget(self.create_card(
                        e.get('activityType', 'Unknown'),
                        e.get('date', 'No date')
                    ))

            if not s and not a:
                self.card_box.add_widget(Label(
                    text="No upcoming items", font_size='16sp',
                    size_hint_y=None, height=30))
        except Exception as e:
            print("Refresh error:", e)
            self.card_box.add_widget(Label(
                text="Could not fetch data", font_size='16sp',
                size_hint_y=None, height=30))

    def _start_auto_refresh(self):
        if self._refresh_ev:
            self._refresh_ev.cancel()
        self._refresh_ev = Clock.schedule_interval(
            lambda dt: self._refresh_schedule(),
            REFRESH_PERIOD
        )


class AlarmApp(App):
    def build(self):
        global alarm_layout_instance
        try:
            alarm_layout_instance = AlarmLayout()  # Keep reference
            if platform == "android":
                start_background_service()
                # threading.Thread(target=alarm_background_loop, daemon=True).start()
            return alarm_layout_instance
        except Exception as e:
            print("App build failed:", e)
            return Label(text="App failed to start", color=(1, 0, 0, 1))


# — Helper Functions —————————————————————————————————————————————————

def vibrate_device(duration=2.0):
    try:
        if platform == "android" and vibrator.exists():
            vibrator.vibrate(time=duration)
        else:
            print("Vibration not supported or not on Android.")
    except Exception as e:
        print("Vibration error:", e)


def call_backend(path, method="get", **kwargs):
    """
    Try each URL in BACKEND_URLS in order until one succeeds.
    `path` is appended to the base, e.g. "/validate/<id>".
    """
    for base in BACKEND_URLS:
        url = base.rstrip("/") + path
        try:
            if method.lower() == "get":
                r = requests.get(url, timeout=5, **kwargs)
            else:
                r = requests.post(url, timeout=5, **kwargs)
            if 200 <= r.status_code < 300:
                return r
        except Exception as e:
            print(f"[Backend] {method.upper()} {url} failed:", e)
    raise RuntimeError(f"All backend endpoints failed for {method.upper()} {path}")


def get_json_path():
    if platform == "android":
        dst = os.path.join(App.get_running_app().user_data_dir, "alarm.json")
        if not os.path.exists(dst):
            try:
                import shutil
                shutil.copy("alarm.json", dst)
            except Exception as e:
                print("Failed to copy alarm.json:", e)
        return dst
    return "alarm.json"


def get_alarm_json_path():
    if platform == "android":
        user_dir = App.get_running_app().user_data_dir
        target_path = os.path.join(user_dir, "alarm.json")
        if not os.path.exists(target_path):
            try:
                import shutil
                shutil.copy("alarm.json", target_path)
            except Exception as e:
                print("Failed to copy alarm.json:", e)
        return target_path
    else:
        return "alarm.json"

service = None
alarm_layout_instance = None  # Store a reference for background polling

def start_background_service():
    global service
    try:
        service = AndroidService('Alarm Background Service', 'running')
        service.start('service started')
        print("Background service started")
    except Exception as e:
        print("Failed to start service:", e)


def alarm_background_loop():
    global alarm_layout_instance
    while True:
        try:
            if alarm_layout_instance:
                print("Background service: running _do_poll()")
                alarm_layout_instance._do_poll()
            else:
                print("Background service: AlarmLayout not ready")
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print("Background loop error:", e)

if __name__ == "__main__":
    try:
        AlarmApp().run()
    except Exception as e:
        print("Critical app crash:", e)
