import requests # type: ignore
from config import * 

class AlarmModel:
    def __init__(self, app_id):
        self.app_id = app_id

    def validate(self):
        try:
            r = requests.get(f"{ALARM_URL}/validate/{self.app_id}")
            return r.status_code == 200 and r.json().get("valid")
        except:
            return False

    def poll(self):
        try:
            r = requests.get(f"{ALARM_URL}/appId/{self.app_id}")
            if r.status_code == 200:
                data = r.json()
                return data.get("trigger", False), data.get("item", {})
        except Exception as e:
            print("Poll error:", e)
        return False, {}

    def fetch_week(self):
        try:
            s = requests.get(f"{ALARM_URL.replace('app-alarm','schedules')}/current-week/{self.app_id}").json()
            a = requests.get(f"{ALARM_URL.replace('app-alarm','activities')}/current-week/{self.app_id}").json()
            return s, a
        except Exception as e:
            print("Fetch error:", e)
            return [], []