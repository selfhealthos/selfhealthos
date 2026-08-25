# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## After every code change: run the build

After finishing any code changes, always run the debug build and check for errors:

```powershell
.\gradlew.bat assembleDebug 2>&1 | Tee-Object -FilePath build.log
```

Then read `build.log` and fix any errors before reporting the task as done. If the build succeeds, tell the user it compiled cleanly.

## Build commands

| Purpose | Command |
|---|---|
| Full debug build (with log file) | `.\gradlew.bat assembleDebug 2>&1 \| Tee-Object -FilePath build.log` |
| Errors/warnings only | `.\gradlew.bat assembleDebug 2>&1 \| Tee-Object -FilePath build.log \| Select-String -Pattern "error:\|warning:\|Exception"` |
| Clean build | `.\gradlew.bat clean assembleDebug 2>&1 \| Tee-Object -FilePath build.log` |
| Run unit tests | `.\gradlew.bat test` |

## Project

- **Package:** `com.alaverty.healthtracker`
- **Min SDK:** 26 / **Compile SDK:** 35
- **Stack:** Kotlin, Jetpack Compose, Room (v14), Hilt, Media3 ExoPlayer, WorkManager, Retrofit/OkHttp, DataStore, EncryptedSharedPreferences

## Architecture

The app is a single-module MVVM app. Data flows: **Room DAOs → HealthRepository → HiltViewModels → Compose screens**.

### Data layer

`HealthRepository` (`data/repository/`) is the **single data-access class** — all ViewModels inject only it, never DAOs directly. It owns the `dayRange(date)` and `rangeMs(start, end)` helpers that convert `LocalDate` to epoch-millis bounds used by every day-scoped or range query.

Room database (`AppDatabase`, version 14) has sixteen entities, all sharing the same sync fields:

| Entity | Table | Key fields |
|---|---|---|
| `DietEntry` | `diet_entries` | `name`, `photoPath` |
| `ExerciseEntry` | `exercise_entries` | `videoName`, `durationSeconds` |
| `PersonalNote` | `personal_notes` | `title`, `content` |
| `BmEntry` | `bm_entries` | `bmNumber`, `notes` |
| `BpEntry` | `bp_entries` | `systolic`, `diastolic`, `notes` |
| `WeightEntry` | `weight_entries` | `weightKg`, `notes` |
| `Habit` | `habits` | `name`, `sortOrder` |
| `HabitCompletion` | `habit_completions` | `habitId`, `habitName`, `date` (YYYY-MM-DD), `completedAt` |
| `LabResult` | `lab_results` | `markerName`, `value`, `unit`, `date` (YYYY-MM-DD test date) |
| `BodyMeasurement` | `body_measurements` | `waistCm`, `hipsCm`, `neckCm`, `bodyFatPct` (all nullable) |
| `FitnessTest` | `fitness_tests` | `gripKg`, `singleLegBalanceSec`, `sitToStandReps`, `deadHangSec` (all nullable) |

Every entity uses a UUID string `@PrimaryKey`, stores time as epoch-millis `Long`, and carries `isSynced: Boolean` + `updatedAt: Long` + `deletedAt: Long?` for portal sync. `AlarmEntry` is the exception: device-local config, deliberately unsynced.

Schema migrations live in the `AppDatabase` companion object (`MIGRATION_1_2` … `MIGRATION_13_14`). **Always add a new `MIGRATION_X_Y` there and register it in `AppModule.kt` when changing the schema.**

### UI layer

Eight screens, each with its own `@HiltViewModel`, composed under a single `Scaffold` with a horizontally-scrollable bottom nav (`AppNavigation.kt`):

| Route | Screen | ViewModel |
|---|---|---|
| `diary` | `DiaryScreen` | `DiaryViewModel` — combines diet+exercise+notes for a selected day using `flatMapLatest` + `combine` |
| `exercise` | `ExerciseScreen` | `ExerciseViewModel` |
| `notes` | `NotesScreen` | `NotesViewModel` |
| `charts` | `ChartsScreen` | `ChartsViewModel` — shows last 7 days of exercise minutes |
| `bm` | `BmScreen` | `BmViewModel` |
| `bp` | `BpScreen` | `BpViewModel` |
| `weight` | `WeightScreen` | `WeightViewModel` — lists all entries newest-first with delta from previous |
| `habits` | `HabitsScreen` | `HabitsViewModel` — date nav + checkbox list; `flatMapLatest+combine` habits with completions |
| `labs` | `LabsScreen` | `LabsViewModel` — blood test results grouped by marker (free-text names), expandable history |
| `body` | `BodyScreen` | `BodyViewModel` — two tabs: body measurements (waist-to-height ratio vs height in Settings) and monthly fitness tests |
| `settings` | `SettingsScreen` | `SettingsViewModel` — GitHub export config, trigger, habit management, and height (Profile) |

All ViewModels expose `StateFlow` to Compose. The nav graph uses `popUpTo(diary) { saveState = true }` + `restoreState = true` so back-stack state is preserved across tab switches.

### Sync to the home portal

**Everything is migrated.** Every entry type now syncs to the portal at
`https://home.laverty`. Alarms are the one exception and are deliberately
local-only: a reminder schedule is device behaviour, not health history, and is
only meaningful on the phone that fires it.

The design, in one line: **Room is the queue, and the server's reply is the only
thing that empties it.**

Two endpoints, because they must be able to fail independently:

| Endpoint | Carries | Manager / worker |
|---|---|---|
| `POST /api/v1/health/sync/gym` | Gym sets + the exercise catalogue | `GymSyncManager` / `GymSyncWorker` |
| `POST /api/v1/health/sync/entries` | The other twelve types, in one batch | `EntrySyncManager` / `EntrySyncWorker` |

Gym keeps its own endpoint because a set has to be merged *after* the exercise
it links to. Nothing else has that ordering problem. They stay separate workers
because WorkManager retries per worker: one worker would put a weight reading
behind a gym set the server is refusing, retrying both forever.

| Piece | Does |
|---|---|
| `sync/GymSyncManager`, `sync/EntrySyncManager` | The protocol. Read unsynced rows, post, mark only what came back accepted. |
| `sync/GymSyncWorker`, `sync/EntrySyncWorker` | Run the managers under WorkManager, plus an hourly sweep each. |
| `sync/EnrolmentService` | Trades email + password for a device token, once. |
| `data/preferences/TokenStore` | The token, in `EncryptedSharedPreferences`. Never DataStore. |
| `data/remote/HomeApi` + `HomeDto` + `EntryDto` | Wire shapes, mapped explicitly from the entities. |
| `data/remote/HomeInterceptors` | Rewrites the host from Settings; attaches the bearer; notices 401. |

**`HealthRepository` asks for a sync after every write**, via `syncSoon()` on
each insert and soft delete. Deliberately there rather than in each ViewModel —
the gym screen's own trigger predates it — so that "a write always asks for a
sync" is structural instead of something twelve ViewModels must each remember.

Four rules, each of which exists because breaking it loses data silently:

- **Save locally first, always.** `GymViewModel.saveSet` writes the row and
  *then* asks for a sync. A save can never fail for want of a network.
- **Mark synced only what the server named.** The reply is a list of accepted
  ids, not a 204. Marking everything on a 2xx is how one rejected row gets
  dropped from the phone forever with a success in the log.
- **Delete is a tombstone.** `deletedAt` is set, `isSynced` cleared, and the row
  stays until the server acknowledges it. `purgeSyncedTombstones` runs only
  after. A hard delete leaves the set on the portal forever.
- **A 401 never drops the queue.** `AuthInterceptor` flags the token dead and
  Settings says so. Entries stay put and resume after re-enrolment.

There is **no wifi detection**. Reading the SSID needs location permission on
Android 10+ and would still answer the wrong question — the portal is reachable
or it is not, and the only way to know is to ask. Away from home the request
fails fast and everything stays queued.

The portal is served with a leaf from the Laverty Root CA, which Android has
never heard of. `res/raw/laverty_root_ca.crt` plus
`res/xml/network_security_config.xml` trust it for `home.laverty` and
`192.168.1.111` **only** — not device-wide.

### Traps this sync has already sprung

- **Prime the server URL before any request.** `serverUrlBlocking()` reads a
  cached field seeded with the compiled-in `DEFAULT_SERVER_URL`
  (`https://home.laverty/`) and corrected *asynchronously* by
  `observeServerUrl`. A worker waking a cold process beats that first DataStore
  read, so every request went to `home.laverty` — a name the phone cannot
  resolve, which is exactly why the address in Settings had been changed to an
  IP. Both managers now call `primeServerUrl()` first. The symptom was three
  weeks of entries queued with **nothing whatsoever in Caddy's access log**;
  the fastest way to see it again is that absence.
- **A sync with no UI caller is a sync nobody watches.** `EntrySyncManager` was
  reachable only from its worker, so the one path it had was the cold-start
  path that was broken, while `GymSyncManager` quietly worked because Settings
  called it directly from the foreground. Anything that can only run in the
  background will only fail in the background.
- **Settings must report both syncs.** `syncStatus` was `gymSyncManager.status`
  alone and `pendingGymCount` counted only gym rows, so the screen said "Up to
  date — nothing waiting to sync" over a real backlog of twenty. The status
  line now shows the worse of the two and the count covers every table.
- **`ExistingWorkPolicy.KEEP` traps a failing worker.** It is right per save and
  wrong as the only path: enough failures back the worker off to WorkManager's
  five-hour ceiling, and KEEP then drops every `requestSync` a save makes until
  that window comes round — seventeen attempts deep, saving an entry did
  nothing at all. App start now calls `restartSync` (REPLACE) so opening the
  app is a way out, and the Settings button calls the managers directly.
- **Read the queue from the device, not the UI.** The app is debuggable, so
  `adb exec-out run-as com.alaverty.healthtracker cat databases/health_tracker.db`
  gives the real `isSynced = 0` counts, and the same against
  `no_backup/androidx.work.workdb` gives `run_attempt_count` per worker — which
  is what distinguishes "never ran" from "ran and failed 17 times".

### The legacy webhook sync is gone

`UploadWorker`, `ApiService` and `SyncPayload` have been deleted, along with the
`@Named("webhook")` Retrofit instance. It posted every type to
`https://webhook.site/YOUR-TOKEN-HERE/` — a placeholder nobody ever filled in,
so none of it was going anywhere; the hourly worker had been waking the phone to
fail since it was written.

WorkManager persists schedules across upgrades, so `HealthTrackerApp` cancels
the old `health_sync` unique work by name on startup. **Do not reintroduce a
second write path to the same rows** — two of them is how an entry gets marked
synced by whichever answered first while the other never received it.

### Tombstones

Every syncable entity carries `deletedAt` (migration 13→14), and every delete in
`HealthRepository` is a soft delete. A hard delete is invisible to the server:
the entry stays on the portal forever with nothing left locally to say it went.
Rows are cleared by `purgeSyncedEntryTombstones()` — and *only* after the server
has acknowledged them, because any earlier there would be nothing left to
resend.

Reads filter `deletedAt IS NULL`; the sync queue deliberately does not, since an
unsynced tombstone is precisely what has to be sent.

### GitHub export

`GitHubExportService` (`data/github/`) exports data to a separate GitHub repo (`alexlaverty/one-data`) as per-day NDJSON files under `data/YYYY/MM/DD/<type>.ndjson`. Settings (repo, PAT, sync range) are persisted via DataStore in `SettingsRepository`.

### DI

`AppModule` (`di/`) is a single `@InstallIn(SingletonComponent::class)` module providing the database, all six DAOs, two Retrofit instances (`@Named("webhook")` and `@Named("github")`), DataStore, and all service singletons.

## Keeping the GitHub export in sync with app changes

**This is a mandatory step whenever the data model changes.**

The GitHub export pipeline in `data/github/GitHubExportService.kt` must stay in sync with the Room entities. Whenever you:

- **Add a new entry type** → add a new DAO with `getEntriesForRange`, add a repository method, add a fetch + `groupBy` + `syncNdjson` call in `GitHubExportService.export()`, and add it to the portal sync: a `_Spec` in the portal's `apps/health/entrysync.py`, a DTO and `toDto()` in `EntryDto.kt`, and a field on `EntrySyncRequest` plus its `collect()`/`markAccepted()` lines
- **`Habit` is special** — definitions export to `data/habits.ndjson` (not date-scoped); completions go to `data/YYYY/MM/DD/habit_completions.ndjson` per day
- **Add a field to an existing entity** → no export change needed (Gson serialises all fields automatically), but update `D:\src\one-data\CLAUDE.md` schema table
- **Rename or remove a field** → check `GitHubExportService` for any field references (currently only `id`, `timestamp`, `updatedAt` are accessed by name in the merge logic)
- **Remove an entity type** → remove from all of the above

Also update `D:\src\one-data\CLAUDE.md` to keep the schema documentation and DuckDB query examples accurate.
