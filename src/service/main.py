from jnius import autoclass
import time
import sys
import os

# ===== Android classes =====
PythonService = autoclass('org.kivy.android.PythonService')
NotificationBuilder = autoclass('android.app.Notification$Builder')
NotificationChannel = autoclass('android.app.NotificationChannel')
NotificationManager = autoclass('android.app.NotificationManager')
Context = autoclass('android.content.Context')
Build_VERSION = autoclass('android.os.Build$VERSION')
Build_VERSION_CODES = autoclass('android.os.Build$VERSION_CODES')
PowerManager = autoclass('android.os.PowerManager')
PendingIntent = autoclass('android.app.PendingIntent')
Intent = autoclass('android.content.Intent')
MediaPlayer = autoclass('android.media.MediaPlayer')
AudioManager = autoclass('android.media.AudioManager')
Vibrator = autoclass('android.os.Vibrator')

# ===== Import main app logic =====
sys.path.append('/data/data/org.yourpackage.name/files/app')
try:
    from main import alarm_layout_instance, AlarmLayout, POLL_INTERVAL, ALARM_SOUND
except:
    alarm_layout_instance = None
    AlarmLayout = None
    POLL_INTERVAL = 10
    ALARM_SOUND = "/data/data/org.yourpackage.name/files/app/fixed-alarm.wav"

service = PythonService.mService

# ===== Notification channel =====
CHANNEL_ID = "alarm_channel"
CHANNEL_NAME = "Alarm Background Service"
notification_manager = service.getSystemService(Context.NOTIFICATION_SERVICE)

if Build_VERSION.SDK_INT >= Build_VERSION_CODES.O:
    channel = NotificationChannel(CHANNEL_ID, CHANNEL_NAME,
                                  NotificationManager.IMPORTANCE_HIGH)
    notification_manager.createNotificationChannel(channel)

# Intent: Launch main activity on tap
package_name = service.getPackageName()
pm = service.getPackageManager()
launch_intent = pm.getLaunchIntentForPackage(package_name)
launch_intent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP)
pending_intent = PendingIntent.getActivity(service, 0, launch_intent,
                                           PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE)

# ===== Foreground notification =====
if Build_VERSION.SDK_INT >= Build_VERSION_CODES.O:
    builder = NotificationBuilder(service, CHANNEL_ID)
else:
    builder = NotificationBuilder(service)

builder.setContentTitle("Alarm Service Running")
builder.setContentText("Your alarms will trigger even while asleep.")
builder.setSmallIcon(service.getApplicationInfo().icon)
builder.setContentIntent(pending_intent)
notification = builder.build()
service.startForeground(1, notification)

# ===== Keep service alive =====
ServiceClass = autoclass('org.kivy.android.PythonService')
ServiceClass.onStartCommand = lambda *args: ServiceClass.START_STICKY

# ===== Wake lock =====
power_manager = service.getSystemService(Context.POWER_SERVICE)
wake_lock = power_manager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AlarmServiceWakelock")
wake_lock.acquire(10 * 60 * 1000)

# ===== Play sound + vibrate =====
def play_alarm_sound_and_vibrate():
    try:
        mp = MediaPlayer()
        mp.setAudioStreamType(AudioManager.STREAM_ALARM)
        mp.setDataSource(ALARM_SOUND)
        mp.prepare()
        mp.setLooping(True)
        mp.start()
        print("[Service] Playing alarm sound")

        vibrator = service.getSystemService(Context.VIBRATOR_SERVICE)
        if vibrator:
            pattern = [0, 1000, 1000]  # vibrate 1s, pause 1s
            vibrator.vibrate(pattern, 0)  # repeat
            print("[Service] Vibration started")

        # Auto stop after 60 seconds
        time.sleep(60)
        mp.stop()
        mp.release()
        if vibrator:
            vibrator.cancel()
        print("[Service] Alarm stopped")

    except Exception as e:
        print("[Service] Failed to play sound:", e)

# ===== Heads-up notification =====
def show_alarm_notification(title="Alarm", message="Time to act!"):
    try:
        if Build_VERSION.SDK_INT >= Build_VERSION_CODES.O:
            nb = NotificationBuilder(service, CHANNEL_ID)
        else:
            nb = NotificationBuilder(service)

        nb.setContentTitle(title)
        nb.setContentText(message)
        nb.setSmallIcon(service.getApplicationInfo().icon)
        nb.setPriority(NotificationManager.IMPORTANCE_HIGH)
        nb.setAutoCancel(True)
        nb.setFullScreenIntent(pending_intent, True)
        alarm_notification = nb.build()

        notification_manager.notify(99, alarm_notification)

        wl = power_manager.newWakeLock(
            PowerManager.FULL_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP |
            PowerManager.ON_AFTER_RELEASE,
            "AlarmServiceScreenLock")
        wl.acquire(5000)
        wl.release()

    except Exception as e:
        print("[Service] Heads-up notification failed:", e)

# ===== Background loop =====
try:
    if alarm_layout_instance is None and AlarmLayout:
        alarm_layout_instance = AlarmLayout()

    while True:
        try:
            if alarm_layout_instance:
                alarm_layout_instance._do_poll()
                if alarm_layout_instance.alarm_triggered:
                    show_alarm_notification(
                        title="⏰ Alarm Triggered!",
                        message="Tap to open the app."
                    )
                    play_alarm_sound_and_vibrate()
            else:
                print("[Service] AlarmLayout not available.")

        except Exception as e:
            print("[Service] Poll error:", e)

        if not wake_lock.isHeld():
            wake_lock.acquire(10 * 60 * 1000)

        time.sleep(POLL_INTERVAL)

except Exception as e:
    print("[Service] Crash:", e)

finally:
    if wake_lock.isHeld():
        wake_lock.release()
