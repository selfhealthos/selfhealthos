Part 1: The Master Blueprint Prompt
Role: Senior Android Developer
Tech Stack: Kotlin, Jetpack Compose, Room Database, Hilt (Dependency Injection), Media3 ExoPlayer, WorkManager, Vico Charts, Retrofit.
App Overview:
A health tracking app (similar to Cara Care) that works offline-first. It tracks Diet, Exercise, and Personal Notes. Data is stored locally and synced to a REST API only when on WiFi.
1. Data Architecture (Offline-First):
Use Room Database. Every entry must have a UUID (String) as the Primary Key and an isSynced (Boolean) flag.
Create three main entities: DietEntry, ExerciseEntry, and PersonalNote.
Each entity must have a timestamp (Long) for the entry time and an updatedAt (Long) for sync logic.
The server will handle deduplication using the UUID (Upsert).
2. Main Screen (The Diary):
Top Header: A date navigation bar with "Back" and "Forward" icons and the current selected date (e.g., "Thursday, June 4").
Content: A LazyColumn showing a combined timeline of all entries (Food, Exercise, Notes) for the selected date only.
Empty State: If no entries exist for that day, show a "No entries yet" message.
3. Navigation (Bottom Bar):
Implement a Scaffold with a BottomNavigation containing:
Food Diary: The main timeline view.
Exercise: A screen that picks a random .mp4 from context.getExternalFilesDir("videos").
Includes a Video Player (Media3) that loops.
A count-up timer (seconds).
"Complete" and "Skip" buttons that save the result to Room with the video name and duration.
Notes: A simple list/editor for personal blog-style notes.
Charts: A screen using Vico Charts to show weekly progress.
4. The Sync Engine:
Create a SyncWorker using WorkManager.
Constraint: NetworkType.UNMETERED (WiFi only).
Logic: Fetch all entries where isSynced == false, POST them as a JSON array to a placeholder endpoint, and mark them isSynced = true upon success.
Part 2: Implementation Steps (Run these one by one)
Since the app is complex, don't ask the AI to write it all at once. Follow this sequence:
Step 1: The Data Layer
"Generate the Room Database setup for this app. Include the Entities for Diet, Exercise, and Notes with UUIDs. Include a 'HealthRepository' class that can fetch entries filtered by a specific 24-hour date range."
Step 2: Main Diary UI & Date Logic
"Create the Main Diary Screen in Jetpack Compose. Add a header with back/forward buttons to change the 'Selected Date'. Show a list of entries for that date. Use a ViewModel to handle the date switching and data loading from Room."
Step 3: Exercise Video Player & Timer
"Create the Exercise Screen. It should:
Find a random mp4 file in the app's internal storage.
Play it using Media3 ExoPlayer on a loop.
Show a timer counting up from 0.
When 'Complete' is pressed, save the exercise name, duration, and timestamp to Room, then reset."
Step 4: The Sync Worker
"Write a WorkManager class called UploadWorker. It should find all unsynced Room entries, format them into a single JSON list, and simulate a Retrofit POST request. Ensure it only runs on WiFi."
Step 5: The Charting Screen
"Create a Stats screen using the Vico library. It should pull the last 7 days of Exercise entries from Room and display a Bar Chart of 'Minutes Exercised per Day'."
Important Technical Advice for You:
Video Files: The AI cannot "see" your videos. You must manually put your .mp4 files (downloaded via yt-dlp) into the phone's folder:
/Android/data/your.package.name/files/videos/
The AI code will then be able to "list" the files in that folder and pick one.
Date Handling: Tell the AI to use java.time.LocalDate and convert it to Epoch Milliseconds for Room storage. This prevents messy timezone bugs when syncing to a server.
The Bottom Nav: Ensure the AI uses the "Material 3" versions of Navigation components, as the older "Material 2" versions are becoming deprecated.
Testing the Sync: Since you don't have a server yet, ask the AI to use "Beeceptor" or "Webhook.site" as a temporary placeholder URL so you can actually see the data being sent when you connect to WiFi.