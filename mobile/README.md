# HealthTracker

A personal Android health-tracking app built with Kotlin, Jetpack Compose, Room, and Hilt. It tracks diet, exercise, bowel movements, blood pressure, and personal notes — all stored locally with optional background sync to a remote endpoint.

## Features

| Screen | What it does |
|---|---|
| **Diary** | Day-by-day log of food, exercise, and notes with date navigation. Add food entries with a name and an optional photo (camera or gallery). |
| **Exercise** | Browse workout video categories, play a looping exercise video with a timer, then log the session on completion or skip. |
| **Notes** | Rich personal notes with inline images. Notes also appear in the Diary for the day they were created. |
| **Charts** | Bar chart showing total exercise minutes for the last 7 days. |
| **BM** | Bowel movement log using the Bristol Stool Scale (1–7) with optional notes. |
| **BP** | Blood pressure log (systolic/diastolic) with optional notes. |

## Build

```powershell
.\gradlew.bat assembleDebug 2>&1 | Tee-Object -FilePath build.log
```

Other build commands:

| Purpose | Command |
|---|---|
| Errors/warnings only | `.\gradlew.bat assembleDebug 2>&1 \| Tee-Object -FilePath build.log \| Select-String -Pattern "error:\|warning:\|Exception"` |
| Clean build | `.\gradlew.bat clean assembleDebug 2>&1 \| Tee-Object -FilePath build.log` |
| Run unit tests | `.\gradlew.bat test` |

The built APK lands at `app/build/outputs/apk/debug/app-debug.apk`.

## Install and sideload via ADB

ADB (Android Debug Bridge) is at `C:\Users\alave\AppData\Local\Android\Sdk\platform-tools\adb.exe`.

Add it to PATH permanently (run once, then restart PowerShell):
```powershell
[Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";C:\Users\alave\AppData\Local\Android\Sdk\platform-tools", "User")
```

### Common ADB commands

| Command | What it does |
|---|---|
| `adb devices` | List connected devices — run first to confirm phone is detected |
| `adb push <pc-path> <device-path>` | Copy file/folder from PC to phone |
| `adb pull <device-path> <pc-path>` | Copy file/folder from phone to PC |
| `adb install app.apk` | Install an APK manually |
| `adb shell` | Open a terminal shell on the device |
| `adb logcat` | Stream the device's live log output |

adb -s adb-R5CY102E73X-9Lf2Ee._adb-tls-connect._tcp shell getprop ro.product.model
adb -s adb-RFCY21XNCDJ-Ki7tKe._adb-tls-connect._tcp shell getprop ro.product.model
adb -s adb-RFCY21XNCDJ-Ki7tKe._adb-tls-connect._tcp push "D:\src\one\videos\Darebee\." "/sdcard/Android/data/com.alaverty.healthtracker/files/videos/Darebee/"
adb -s adb-RFCY21XNCDJ-Ki7tKe._adb-tls-connect._tcp push "D:\src\one\videos\Mobility\." "/sdcard/Android/data/com.alaverty.healthtracker/files/videos/Mobility/"


### Push exercise videos

The Exercise screen reads workout videos from the app's external files directory. Each subfolder becomes a selectable category.

```powershell
adb shell mkdir -p "/sdcard/Android/data/com.alaverty.healthtracker/files/videos/Darebee"
adb shell mkdir -p "/sdcard/Android/data/com.alaverty.healthtracker/files/videos/Mobility"
adb push "D:\src\one\videos\Darebee\." "/sdcard/Android/data/com.alaverty.healthtracker/files/videos/Darebee/"
adb push "D:\src\one\videos\Mobility\." "/sdcard/Android/data/com.alaverty.healthtracker/files/videos/Mobility/"
```

Each subfolder under `files/videos/` becomes a selectable category on the Exercise screen.

## Background sync

All entries carry `isSynced` and `updatedAt` fields. `UploadWorker` runs hourly on unmetered Wi-Fi, POSTing all unsynced entries to the configured endpoint.

To enable sync, replace the placeholder base URL in `app/src/main/java/com/alaverty/healthtracker/di/AppModule.kt`:

```kotlin
.baseUrl("https://webhook.site/YOUR-TOKEN-HERE/")
```

Use [webhook.site](https://webhook.site) for testing, or point it at your own server. The worker POST's to `<baseUrl>sync` with a JSON body containing all five entry types.
