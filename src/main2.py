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
from kivy.uix.anchorlayout import AnchorLayout # type: ignore
from kivy.uix.popup import Popup # type: ignore
from kivy.utils import platform # type: ignore
from kivy.core.audio import SoundLoader # type: ignore
from kivy.storage.jsonstore import JsonStore # type: ignore
from kivy.uix.slider import Slider # type: ignore
from kivy.logger import Logger # type: ignore
from pathlib import Path

from plyer import audio, vibrator # type: ignore
SOUND_BACKEND = "plyer"

# —————————————————————————————————————————————————————————————————————————
# CONFIG
# —————————————————————————————————————————————————————————————————————————
# ALARM_URL      = "http://localhost:5000/api/app-alarm" # testing
# ALARM_SOUND    = "alarm.wav"     # your audio file
POLL_INTERVAL  = 10              # in seconds
REFRESH_PERIOD = 60              # in seconds
HERE = os.path.dirname(__file__)
ALARM_SOUND = os.path.join(HERE, "fixed-alarm.wav")
BACKEND_URLS = [
    "https://mern-lifetime.onrender.com/api",
    # "http://localhost:5000/api"
]

if platform == 'android':
    from android.storage import app_storage_path # from android
    store_path = Path(app_storage_path()) / "settings.json"
else:
    store_path = Path("settings.json")  # fallback for dev testing

store = JsonStore(store_path)

store = JsonStore("settings.json")

# simulate phone‑size for desktop preview
Window.size = (360, 640)
Window.clearcolor = (1, 1, 1, 1)

# —————————————————————————————————————————————————————————————————————————
# A little “Card” widget via canvas
# —————————————————————————————————————————————————————————————————————————
class CardBox(BoxLayout):
    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", 12)
        kwargs.setdefault("spacing", 8)
        super().__init__(**kwargs)

        with self.canvas.before:
            Color(1, 1, 1, 1)  # white background
            self.rect = RoundedRectangle(radius=[12])
        
        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


# —————————————————————————————————————————————————————————————————————————
# Main layout
# —————————————————————————————————————————————————————————————————————————
class AlarmLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=0, spacing=12, **kwargs)
        self.app_id     = self._load_app_id()
        self._refresh_ev= None
        self.alarm_triggered = False
        self.volume = store.get("audio")["volume"] if store.exists("audio") else 1.0

        # we'll build UI once, below
        if self.app_id:
            self._build_main_view()
        else:
            self._build_id_view()


    # — ID ENTRY ———————————————————————————————————————————————
    
    def _build_id_view(self):
        self.clear_widgets()

        # Anchor everything in the center
        container = AnchorLayout(anchor_x='center', anchor_y='center')
        card = BoxLayout(orientation='vertical', padding=20, spacing=12,
                        size_hint=(0.8, None), height=200)

        # Draw a red rounded rect + subtle shadow behind the card
        with card.canvas.before:
            # shadow
            Color(rgba=(0, 0, 0, 0.15))
            self._shadow_rect = RoundedRectangle(radius=[20], pos=(card.x-5, card.y-5),
                                                size=(card.width+10, card.height+10))
            # red background
            Color(rgba=(1, 0.3, 0.25, 1))
            self._bg_rect = RoundedRectangle(radius=[20], pos=card.pos, size=card.size)
        # keep them in sync
        card.bind(pos=self._update_card_bg, size=self._update_card_bg)

        # Title
        self.status = Label(text="Enter your App ID", size_hint_y=None, height=40,
                            color=(1,1,1,1), bold=True, font_size='18sp')
        card.add_widget(self.status)

        # Input + button row
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


    def _update_card_bg(self, instance, value):
        # update both shadow and bg to follow card
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


    # — MAIN ALARM + SCHEDULE DISPLAY —————————————————————————————————————————
    def _build_main_view(self):
        self.clear_widgets()

        # --- Red Header with ID ---
        header = BoxLayout(orientation='vertical', size_hint_y=None, height=100, padding=(10, 10), spacing=5)
        with header.canvas.before:
            Color(1, 0.3, 0.25, 1)
            self._header_bg = RoundedRectangle(pos=header.pos, size=header.size, radius=[0, 0, 20, 20])
        header.bind(pos=self._update_header_bg, size=self._update_header_bg)

        header.add_widget(Label(text="Alarm Active", font_size='24sp', bold=True, color=(1, 1, 1, 1)))
        header.add_widget(Label(text=f"(ID: {self.app_id})", font_size='16sp', color=(1, 1, 1, 1)))
        self.add_widget(header)

        # --- Card Scrollable Content ---
        self.card_scroll = ScrollView(size_hint=(1, 1))
        self.card_box = CardBox(size_hint_y=None, padding=16, spacing=12)
        self.card_box.bind(minimum_height=self.card_box.setter('height'))
        self.card_scroll.add_widget(self.card_box)
        self.add_widget(self.card_scroll)

        # --- Reset Button ---
        reset = Button(
            text="Reset ID",
            size_hint_y=None,
            height=50,
            background_color=(1, 0.3, 0.25, 1),
            color=(1, 1, 1, 1),
            background_normal='',
            font_size='16sp'
        )
        # reset.bind(on_press=self._on_reset)
        reset.bind(on_press=self._confirm_reset)
        self.add_widget(reset)

        # -- Volume Settings ---
        settings = Button(
            text="Volume Settings",
            size_hint_y=None,
            height=50,
            background_color=(1, 0.3, 0.25, 1),
            color=(1, 1, 1, 1),
            background_normal='',
            font_size='16sp'
        )
        settings.bind(on_press=self.open_volume_settings)
        self.add_widget(settings)

        # Load content
        Clock.schedule_once(lambda dt: self._start_polling(), 0)
        Clock.schedule_once(lambda dt: self._refresh_schedule(), 0)
        self._start_auto_refresh()

    def _update_header_bg(self, *args):
        self._header_bg.pos = args[0].pos
        self._header_bg.size = args[0].size

    def create_card(self, title, subtitle):
        card = BoxLayout(orientation='vertical', padding=12, spacing=6,
                        size_hint_y=None, height=100)

        with card.canvas.before:
            Color(1, 1, 1, 1)  # white background
            rect = RoundedRectangle(radius=[16])
            card._bg_rect = rect  # store so we can update
        card.bind(pos=lambda instance, _: setattr(rect, 'pos', instance.pos))
        card.bind(size=lambda instance, _: setattr(rect, 'size', instance.size))

        card.add_widget(Label(
            text=title, font_size='16sp', bold=True,
            color=(0.1, 0.1, 0.1, 1), size_hint_y=None, height=30
        ))
        card.add_widget(Label(
            text=subtitle, font_size='14sp',
            color=(0.3, 0.3, 0.3, 1), size_hint_y=None, height=20
        ))
        return card
    
    
    def open_volume_settings(self, _):
        # Container card
        card = BoxLayout(orientation='vertical', spacing=20, padding=20,
                         size_hint=(0.8, None), height=250)
        with card.canvas.before:
            # shadow
            Color(0, 0, 0, 0.15)
            shadow = RoundedRectangle(radius=[16], pos=(card.x-5, card.y-5),
                                      size=(card.width+10, card.height+10))
            # white background
            Color(1, 1, 1, 1)
            bg = RoundedRectangle(radius=[16], pos=card.pos, size=card.size)
        card.bind(pos=lambda inst, _: setattr(shadow, 'pos', (inst.x-5, inst.y-5)))
        card.bind(size=lambda inst, _: setattr(shadow, 'size', (inst.width+10, inst.height+10)))
        card.bind(pos=lambda inst, _: setattr(bg, 'pos', inst.pos),
                  size=lambda inst, _: setattr(bg, 'size', inst.size))

        # Header
        header = Label(text="🔊 Set Alarm Volume", size_hint=(1, None), height=40,
                       font_size='18sp', bold=True, color=(1, 0.3, 0.25, 1))
        card.add_widget(header)

        # Slider
        slider = Slider(min=0.0, max=1.0, value=self.volume,
                        size_hint=(1, None), height=40)
        card.add_widget(slider)

        # Buttons row
        btn_row = BoxLayout(size_hint=(1, None), height=50, spacing=10)
        save_btn = Button(text="Save", background_color=(1, 0.3, 0.25, 1),
                          color=(1,1,1,1), bold=True)
        cancel_btn = Button(text="Cancel", background_color=(0.8, 0.8, 0.8, 1),
                            color=(0,0,0,1))
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(save_btn)
        card.add_widget(btn_row)

        popup = Popup(title="", content=card,
                      size_hint=(None, None), size=(Window.width*0.9, 300),
                      auto_dismiss=False, background='')
        # hook up
        save_btn.bind(on_release=lambda *_: (
            setattr(self, 'volume', slider.value),
            store.put("audio", volume=slider.value),
            popup.dismiss()
        ))
        cancel_btn.bind(on_release=popup.dismiss)
        popup.open()

    
    def _confirm_reset(self, _):
        # Container card
        card = BoxLayout(orientation='vertical', spacing=20, padding=20,
                         size_hint=(0.8, None), height=200)
        with card.canvas.before:
            Color(0, 0, 0, 0.15)
            shadow = RoundedRectangle(radius=[16], pos=(card.x-5, card.y-5),
                                      size=(card.width+10, card.height+10))
            Color(1, 1, 1, 1)
            bg = RoundedRectangle(radius=[16], pos=card.pos, size=card.size)
        card.bind(pos=lambda inst, _: setattr(shadow, 'pos', (inst.x-5, inst.y-5)))
        card.bind(size=lambda inst, _: setattr(shadow, 'size', (inst.width+10, inst.height+10)))
        card.bind(pos=lambda inst, _: setattr(bg, 'pos', inst.pos),
                  size=lambda inst, _: setattr(bg, 'size', inst.size))

        # Question
        card.add_widget(Label(text="⚠️ Reset App ID?", size_hint=(1, None), height=40,
                              font_size='18sp', bold=True, color=(1, 0.3, 0.25, 1),
                              halign='center'))

        # Buttons
        btn_row = BoxLayout(size_hint=(1, None), height=50, spacing=10)
        yes = Button(text="Yes", background_color=(1, 0.3, 0.25, 1),
                     color=(1,1,1,1), bold=True)
        no  = Button(text="No",  background_color=(0.8,0.8,0.8,1),
                     color=(0,0,0,1))
        btn_row.add_widget(no)
        btn_row.add_widget(yes)
        card.add_widget(btn_row)

        popup = Popup(title="", content=card,
                      size_hint=(None, None), size=(Window.width*0.8, 220),
                      auto_dismiss=False, background='')
        no.bind(on_release=popup.dismiss)
        yes.bind(on_release=lambda *_: (popup.dismiss(), self._on_reset(None)))
        popup.open()


    # — VALIDATION & PERSISTENCE —————————————————————————————————————————
    def _validate_id(self, app_id):
        try:
            # r = requests.get(f"{ALARM_URL}/validate/{app_id}")
            r = call_backend(f"/app-alarm/validate/{app_id}")
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
        # threading.Thread(target=self._poll_loop, daemon=True).start()
        Clock.schedule_interval(self._poll_once, POLL_INTERVAL)

    def _do_poll(self):
        # this lives in a worker thread, so blocking requests.play() are fine here
        try:
            # r = requests.get(f"{ALARM_URL}/appId/{self.app_id}")
            r = call_backend(f"/app-alarm/appId/{self.app_id}")
            data = r.json() if r.status_code == 200 else {}
            if data.get("trigger") and not self.alarm_triggered:
                self.alarm_triggered = True
                item = data["item"]
                # schedule UI things back on the main thread
                Clock.schedule_once(lambda dt: self._play_sound(), 0)
                Clock.schedule_once(lambda dt: self.show_alarm(item), 0)
                # schedule resetting the flag 60s later
                Clock.schedule_once(lambda dt: setattr(self, 'alarm_triggered', False), 60)
                # fire-and-forget acknowledgement
                threading.Thread(
                    target=lambda: call_backend(
                        f"/app-alarm/mobile/alarms/{item['_id']}/acknowledge",
                        method="POST",
                        json={"type": data["source"]}
                    ),
                        # requests.post(
                        # f"{ALARM_URL}/mobile/alarms/{item['_id']}/acknowledge",
                        # json={"type": data["source"]}
                    daemon=True
                ).start()
        except Exception as e:
            print("Poll error:", e)

    def _poll_once(self, dt):
        # fire off the network check in a thread
        threading.Thread(target=self._do_poll, daemon=True).start()

    def _poll_loop(self):
        while True:
            try:
                # r = requests.get(f"{ALARM_URL}/appId/{self.app_id}")
                r = call_backend(f"/app-alarm/appId/{self.app_id}")
                if r.status_code==200 and r.json().get("trigger"):
                    threading.Thread(target=self._play_sound, daemon=True).start() # this will crash the app
            except Exception as e:
                print("Poll error:", e)
            time.sleep(POLL_INTERVAL)
 
    def show_alarm(self, item):
        """Pop up a dismissable alarm window"""
        title = item.get("title", "Alarm")
        date  = item.get("date", "")

        content = BoxLayout(orientation="vertical", padding=20, spacing=20)
        content.add_widget(Label(text=f"[b]{title}[/b]\n{date}", markup=True, halign='center'))

        btn = Button(
            text="Dismiss",
            size_hint_y=None,
            height="48dp",
            background_color=(1, 0.3, 0.25, 1),
            color=(1, 1, 1, 1),
            background_normal='',
            bold=True
        )

        content.add_widget(btn)

        popup = Popup(
            title="⏰ Alarm!",
            title_color=(1, 0.3, 0.25, 1),
            title_align="center",
            content=content,
            size_hint=(.85, .4),
            background='atlas://data/images/defaulttheme/button_pressed',
            auto_dismiss=False
        )

        def dismiss_and_reset(*_):
            popup.dismiss()
            self.alarm_triggered = False

        btn.bind(on_press=dismiss_and_reset)
        popup.open()

    def _play_sound(self):
        # try Kivy first
        sound = SoundLoader.load(ALARM_SOUND)
        if sound:
            sound.volume = self.volume
            sound.play()
        # fall back to plyer.audio on Android only
        elif platform == "android":
            try:
                audio.source = ALARM_SOUND
                audio.play()
            except Exception:
                Logger.warning("Audio: plyer.audio failed")

        # vibrate on Android (no‐op on desktop)
        if platform == "android":
            try:
                vibrator.vibrate(1.0)
            except Exception:
                Logger.warning("Vibration failed")


    # — WEEKLY REFRESH —————————————————————————————————————————————————

    def _refresh_schedule(self):
        self.card_box.clear_widgets()
        try:
            # s = requests.get(f"http://localhost:5000/api/schedules/current-week/{self.app_id}").json()
            s = call_backend(f"/schedules/current-week/{self.app_id}", method="get").json()
            # a = requests.get(f"http://localhost:5000/api/activities/current-week/{self.app_id}").json()
            a = call_backend(f"/activities/current-week/{self.app_id}", method="get").json()

            if s:
                self.card_box.add_widget(Label(text="Schedules", color=(1, 0.3, 0.25, 1), font_size='18sp', bold=True, size_hint_y=None, height=30))
                for e in s:
                    self.card_box.add_widget(self.create_card(e['title'], e['date']))


            if a:
                self.card_box.add_widget(Label(text="Activities", color=(1, 0.3, 0.25, 1), font_size='18sp', bold=True, size_hint_y=None, height=30))
                for e in a:
                    self.card_box.add_widget(self.create_card(e['activityType'], e['date']))

            if not s and not a:
                self.card_box.add_widget(Label(text="No upcoming items", font_size='16sp', size_hint_y=None, height=30))
        except Exception as e:
            print("Refresh error:", e)
            self.card_box.add_widget(Label(text="Could not fetch data", font_size='16sp', size_hint_y=None, height=30))

    def _start_auto_refresh(self):
        if self._refresh_ev:
            self._refresh_ev.cancel()
        self._refresh_ev = Clock.schedule_interval(lambda dt: self._refresh_schedule(), REFRESH_PERIOD)


class AlarmApp(App):
    def build(self):
        return AlarmLayout()
    
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
            # if it's a 2xx, return it immediately
            if 200 <= r.status_code < 300:
                return r
        except Exception as e:
            print(f"[Backend] {method.upper()} {url} failed:", e)
    # if we got here, all failed
    raise RuntimeError(f"All backend endpoints failed for {method.upper()} {path}")

if __name__=="__main__":
    AlarmApp().run()
