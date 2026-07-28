# Meeting Screen Blocker

Chromium/Comet extension that takes over every open tab's screen 5 minutes
before your next Google Calendar meeting starts, so you can't miss it.

- Reads your primary Google Calendar (read-only) every 5 minutes, looking
  ahead 2 hours.
- 5 minutes before a meeting with a scheduled time (all-day events are
  skipped), it injects a full-screen overlay into every open tab — including
  tabs opened while the alert is active.
- The overlay shows the meeting title, a countdown, a **Join meeting** button
  (if the event has a Meet/video link), and a **Dismiss** button. Either
  action clears the overlay from all tabs.

## One-time setup

Because this pulls from your real Google Calendar, it needs an OAuth client
you create yourself — Google ties OAuth client IDs to a specific extension
ID, so this can't be pre-configured for you.

1. **Load the extension first, unpacked**, to get its extension ID:
   - Open `chrome://extensions` (or `comet://extensions`) and enable
     **Developer mode**.
   - Click **Load unpacked** and select this `meeting-blocker-extension`
     folder.
   - Copy the **ID** shown on the extension's card (a 32-character string).
     This ID stays stable as long as you don't move this folder.

2. **Create a Google Cloud OAuth client:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/) and
     create/select a project.
   - Enable the **Google Calendar API** (APIs & Services → Library).
   - Under **APIs & Services → OAuth consent screen**, configure it (External
     is fine — add your own email as a test user; Internal if this is a
     Google Workspace org you admin).
   - Under **APIs & Services → Credentials**, click **Create Credentials →
     OAuth client ID**, choose **Chrome Extension** as the application type,
     and paste in the extension ID from step 1.
   - Copy the generated **Client ID**.

3. **Wire the client ID into the extension:**
   - Open `manifest.json` and replace `YOUR_OAUTH_CLIENT_ID.apps.googleusercontent.com`
     with the client ID you just copied.
   - Back on `chrome://extensions`, click the reload icon on this extension's
     card.

4. **Connect your calendar:**
   - Click the extension's toolbar icon → **Connect Google Calendar** →
     grant the read-only Calendar permission.
   - The popup will list your upcoming tracked meetings once synced.

## Trying it out

Click **Preview alert (test)** in the popup to trigger the full-screen
overlay immediately without waiting for a real meeting.

## Notes / limitations

- Requires Comet/Chrome to be running (doesn't wake a fully closed browser).
- Only covers tabs the extension can script — internal browser pages
  (`chrome://…`) can't be overlaid.
- Scope is `calendar.readonly`; the extension never writes to your calendar.
