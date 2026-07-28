const statusEl = document.getElementById('status');
const meetingsEl = document.getElementById('meetings');
const connectBtn = document.getElementById('connectBtn');
const testBtn = document.getElementById('testBtn');

function formatTime(dateStr) {
  return new Date(dateStr).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function render() {
  chrome.runtime.sendMessage({ type: 'getStatus' }, (data) => {
    const scheduled = Object.values(data.scheduledEvents || {}).sort(
      (a, b) => new Date(a.start) - new Date(b.start)
    );

    if (data.activeAlert) {
      statusEl.textContent = `Alert active: ${data.activeAlert.title}`;
    } else if (scheduled.length > 0) {
      statusEl.textContent = `Connected — ${scheduled.length} upcoming meeting${scheduled.length === 1 ? '' : 's'} tracked`;
      connectBtn.textContent = 'Re-sync calendar';
    } else if (data.lastSync) {
      statusEl.textContent = 'Connected — no meetings in the next 2 hours';
      connectBtn.textContent = 'Re-sync calendar';
    } else {
      statusEl.textContent = 'Not connected yet';
    }

    meetingsEl.innerHTML = '';
    for (const event of scheduled.slice(0, 5)) {
      const row = document.createElement('div');
      row.textContent = `${formatTime(event.start)} — ${event.title}`;
      meetingsEl.appendChild(row);
    }
  });
}

connectBtn.addEventListener('click', () => {
  connectBtn.disabled = true;
  connectBtn.textContent = 'Connecting…';
  chrome.runtime.sendMessage({ type: 'authenticate' }, (res) => {
    connectBtn.disabled = false;
    if (!res?.ok) {
      statusEl.textContent = `Connection failed: ${res?.error || 'unknown error'}`;
    }
    render();
  });
});

testBtn.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'testAlert' }, () => {
    window.close();
  });
});

render();
