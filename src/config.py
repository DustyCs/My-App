from kivy.core.window import Window # type: ignore

ALARM_URL      = "http://localhost:5000/api/app-alarm"
ALARM_SOUND    = "alarm.mp3"
POLL_INTERVAL  = 10
REFRESH_PERIOD = 60

# preview on desktop
Window.size = (360, 640)