// Service worker: syncs Google Calendar, schedules alarms, and takes over
// every open tab's screen 5 minutes before a meeting starts.

const SYNC_ALARM_NAME = 'calendar-sync';
const SYNC_INTERVAL_MINUTES = 5;
const LOOKAHEAD_MS = 2 * 60 * 60 * 1000; // only look at meetings starting within 2h
const LEAD_MS = 5 * 60 * 1000; // fire 5 minutes before start
const MEETING_ALARM_PREFIX = 'meeting-';

function getAuthToken(interactive) {
  return new Promise((resolve, reject) => {
    chrome.identity.getAuthToken({ interactive }, (token) => {
      if (chrome.runtime.lastError || !token) {
        reject(chrome.runtime.lastError || new Error('No token returned'));
        return;
      }
      resolve(token);
    });
  });
}

async function fetchUpcomingEvents(token) {
  const timeMin = new Date().toISOString();
  const timeMax = new Date(Date.now() + LOOKAHEAD_MS).toISOString();
  const url =
    'https://www.googleapis.com/calendar/v3/calendars/primary/events' +
    `?timeMin=${encodeURIComponent(timeMin)}` +
    `&timeMax=${encodeURIComponent(timeMax)}` +
    '&singleEvents=true&orderBy=startTime&maxResults=25';

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (res.status === 401) {
    // Token expired/invalid — drop it so the next sync re-authenticates.
    await new Promise((resolve) => chrome.identity.removeCachedAuthToken({ token }, resolve));
    throw new Error('Auth token rejected (401)');
  }
  if (!res.ok) {
    throw new Error(`Calendar API error: ${res.status}`);
  }
  const data = await res.json();
  return data.items || [];
}

function extractJoinLink(event) {
  if (event.hangoutLink) return event.hangoutLink;
  const entryPoints = event.conferenceData?.entryPoints || [];
  const video = entryPoints.find((e) => e.entryPointType === 'video');
  return video?.uri || null;
}

async function syncCalendar() {
  let token;
  try {
    token = await getAuthToken(false);
  } catch (err) {
    console.warn('Meeting Screen Blocker: not authenticated yet', err);
    return;
  }

  let events;
  try {
    events = await fetchUpcomingEvents(token);
  } catch (err) {
    console.warn('Meeting Screen Blocker: calendar fetch failed', err);
    return;
  }

  const { scheduledEvents = {} } = await chrome.storage.local.get('scheduledEvents');
  const nextScheduled = {};
  const now = Date.now();

  for (const event of events) {
    if (event.status === 'cancelled') continue;
    const startStr = event.start?.dateTime; // skip all-day events (date-only)
    if (!startStr) continue;

    const startMs = new Date(startStr).getTime();
    const alertMs = startMs - LEAD_MS;
    const alarmName = `${MEETING_ALARM_PREFIX}${event.id}`;

    const existing = scheduledEvents[event.id];
    const unchanged = existing && existing.updated === event.updated && existing.start === startStr;

    nextScheduled[event.id] = {
      alarmName,
      start: startStr,
      updated: event.updated,
      title: event.summary || '(No title)',
      joinLink: extractJoinLink(event),
    };

    if (unchanged) continue; // already scheduled for the current version of this event

    if (startMs <= now) continue; // meeting already started/passed, nothing to warn about

    await chrome.alarms.clear(alarmName);
    const when = alertMs <= now ? now + 1000 : alertMs; // if we're already inside the 5-min window, fire almost immediately
    chrome.alarms.create(alarmName, { when });
  }

  // Clean up alarms/state for events that disappeared (cancelled or out of window).
  for (const [eventId, info] of Object.entries(scheduledEvents)) {
    if (!nextScheduled[eventId]) {
      await chrome.alarms.clear(info.alarmName);
    }
  }

  await chrome.storage.local.set({ scheduledEvents: nextScheduled, lastSync: now });
}

function overlayInjector(title, timeLabel, joinLink) {
  const OVERLAY_ID = 'wy-meeting-blocker-overlay';
  if (document.getElementById(OVERLAY_ID)) return;

  const overlay = document.createElement('div');
  overlay.id = OVERLAY_ID;
  overlay.style.cssText = `
    position: fixed; inset: 0; width: 100vw; height: 100vh;
    background: linear-gradient(135deg, #0f172a, #1e293b);
    color: #f8fafc; z-index: 2147483647;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    text-align: center; padding: 40px;
  `;

  const eyebrow = document.createElement('div');
  eyebrow.textContent = timeLabel;
  eyebrow.style.cssText = 'font-size: 20px; letter-spacing: 2px; text-transform: uppercase; color: #94a3b8; margin-bottom: 16px;';

  const heading = document.createElement('div');
  heading.textContent = title;
  heading.style.cssText = 'font-size: 48px; font-weight: 700; max-width: 900px; margin-bottom: 40px;';

  const buttonRow = document.createElement('div');
  buttonRow.style.cssText = 'display: flex; gap: 16px;';

  if (joinLink) {
    const joinBtn = document.createElement('button');
    joinBtn.textContent = 'Join meeting';
    joinBtn.style.cssText = `
      font-size: 18px; padding: 14px 32px; border-radius: 8px; border: none;
      background: #22c55e; color: #052e16; font-weight: 600; cursor: pointer;
    `;
    joinBtn.onclick = () => chrome.runtime.sendMessage({ type: 'join', url: joinLink });
    buttonRow.appendChild(joinBtn);
  }

  const dismissBtn = document.createElement('button');
  dismissBtn.textContent = 'Dismiss';
  dismissBtn.style.cssText = `
    font-size: 18px; padding: 14px 32px; border-radius: 8px; border: 1px solid #475569;
    background: transparent; color: #f8fafc; cursor: pointer;
  `;
  dismissBtn.onclick = () => chrome.runtime.sendMessage({ type: 'dismiss' });
  buttonRow.appendChild(dismissBtn);

  overlay.append(eyebrow, heading, buttonRow);
  document.documentElement.appendChild(overlay);
}

function overlayRemover() {
  document.getElementById('wy-meeting-blocker-overlay')?.remove();
}

function timeLabelFor(startMs) {
  const diffMin = Math.round((startMs - Date.now()) / 60000);
  if (diffMin <= 0) return 'Starting now';
  return `Starting in ${diffMin} minute${diffMin === 1 ? '' : 's'}`;
}

async function injectOverlayIntoTab(tabId, alert) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: overlayInjector,
      args: [alert.title, timeLabelFor(alert.start), alert.joinLink],
    });
  } catch (err) {
    // Tab may be a chrome:// page or otherwise unscriptable — ignore.
  }
}

async function injectOverlayIntoAllTabs(alert) {
  const tabs = await chrome.tabs.query({});
  await Promise.all(tabs.map((tab) => injectOverlayIntoTab(tab.id, alert)));
}

async function removeOverlayFromAllTabs() {
  const tabs = await chrome.tabs.query({});
  await Promise.all(
    tabs.map((tab) =>
      chrome.scripting.executeScript({ target: { tabId: tab.id }, func: overlayRemover }).catch(() => {})
    )
  );
}

async function triggerAlert(eventId, info) {
  const alert = { eventId, title: info.title, start: new Date(info.start).getTime(), joinLink: info.joinLink };
  await chrome.storage.local.set({ activeAlert: alert });
  await injectOverlayIntoAllTabs(alert);
  chrome.action.setBadgeText({ text: '!' });
  chrome.action.setBadgeBackgroundColor({ color: '#dc2626' });
}

async function clearAlert() {
  await chrome.storage.local.set({ activeAlert: null });
  await removeOverlayFromAllTabs();
  chrome.action.setBadgeText({ text: '' });
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(SYNC_ALARM_NAME, { periodInMinutes: SYNC_INTERVAL_MINUTES });
  syncCalendar();
});

chrome.runtime.onStartup.addListener(() => {
  syncCalendar();
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === SYNC_ALARM_NAME) {
    syncCalendar();
    return;
  }
  if (alarm.name.startsWith(MEETING_ALARM_PREFIX)) {
    const eventId = alarm.name.slice(MEETING_ALARM_PREFIX.length);
    const { scheduledEvents = {} } = await chrome.storage.local.get('scheduledEvents');
    const info = scheduledEvents[eventId];
    if (info) triggerAlert(eventId, info);
  }
});

// Cover any tab opened/navigated while an alert is active.
async function coverTabIfAlertActive(tabId) {
  const { activeAlert } = await chrome.storage.local.get('activeAlert');
  if (activeAlert) injectOverlayIntoTab(tabId, activeAlert);
}

chrome.tabs.onCreated.addListener((tab) => coverTabIfAlertActive(tab.id));
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === 'complete') coverTabIfAlertActive(tabId);
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'dismiss') {
    clearAlert();
  } else if (message.type === 'join') {
    chrome.tabs.create({ url: message.url });
    clearAlert();
  } else if (message.type === 'authenticate') {
    getAuthToken(true)
      .then(() => syncCalendar())
      .then(() => sendResponse({ ok: true }))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true; // keep the message channel open for the async response
  } else if (message.type === 'testAlert') {
    triggerAlert('test', {
      title: 'Test Meeting',
      start: Date.now() + LEAD_MS,
      joinLink: null,
    }).then(() => sendResponse({ ok: true }));
    return true;
  } else if (message.type === 'getStatus') {
    chrome.storage.local.get(['scheduledEvents', 'activeAlert', 'lastSync']).then((data) => {
      sendResponse(data);
    });
    return true;
  }
});
