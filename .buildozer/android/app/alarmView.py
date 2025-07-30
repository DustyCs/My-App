from kivy.graphics import Color, RoundedRectangle # type: ignore
from kivy.uix.boxlayout import BoxLayout # type: ignore
from kivy.uix.textinput import TextInput # type: ignore
from kivy.uix.button import Button # type: ignore
from kivy.uix.label import Label # type: ignore
from kivy.uix.scrollview import ScrollView # type: ignore

class CardBox(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=12, spacing=8, **kwargs)
        with self.canvas.before:
            Color(rgba=(1,1,1,0.1))
            self._bg = RoundedRectangle(radius=[10], pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)
    def _upd_bg(self, *a):
        self._bg.pos = self.pos; self._bg.size = self.size

class AlarmView(BoxLayout):
    def __init__(self, controller, **kwargs):
        super().__init__(orientation='vertical', padding=16, spacing=12, **kwargs)
        self.ctrl = controller
        self.status = Label(size_hint_y=None, height=30)
        self.add_widget(self.status)
        # input
        self.id_input = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.app_id_in = TextInput(hint_text="App ID", multiline=False)
        self.start_btn = Button(text="Start", background_color=(0.2,0.6,1,1))
        self.start_btn.bind(on_press=self.ctrl.on_start)
        self.id_input.add_widget(self.app_id_in)
        self.id_input.add_widget(self.start_btn)
        self.add_widget(self.id_input)
        # reset
        self.reset_btn = Button(text="Reset", size_hint_y=None, height=40, background_color=(1,0.4,0.3,1))
        self.reset_btn.bind(on_press=self.ctrl.on_reset)
        # schedule display
        self.card_scroll = ScrollView(size_hint=(1,None), size=(self.width, self.height*0.6))
        card = CardBox(size_hint_y=None)
        card.bind(minimum_height=card.setter('height'))
        self.card_content = Label(text="", markup=True, size_hint_y=None, valign='top')
        self.card_content.bind(texture_size=lambda inst,ts: setattr(inst, 'height', ts[1]))
        card.add_widget(self.card_content)
        self.card_scroll.add_widget(card)

    def show_id_view(self, msg="Enter App ID"):
        self.clear_widgets(); self.status.text=msg
        self.add_widget(self.status)
        self.add_widget(self.id_input)

    def show_main_view(self, app_id):
        self.clear_widgets(); self.status.text=f"Alarm Active: {app_id}"
        self.add_widget(self.status); self.add_widget(self.reset_btn); self.add_widget(self.card_scroll)

    def render_schedule(self, schedules, activities):
        lines=[]
        if schedules:
            lines.append("Schedules:")
            for e in schedules: lines.append(f"• {e['title']} @ {e['date']}")
        if activities:
            lines.append("Activities:")
            for e in activities: lines.append(f"• {e['activityType']} @ {e['date']}")
        if not lines: lines=["No items"]
        self.card_content.text="\n".join(lines)