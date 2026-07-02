const sampleUrls = [
  'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  'https://soundcloud.com/example/ambient-night',
  'https://vimeo.com/123456789'
];

const audioQualities = ['64 kbps', '128 kbps', '192 kbps', '256 kbps', '320 kbps'];
const videoQualities = ['144p', '240p', '360p', '480p', '720p', '1080p', '4K'];

const state = {
  currentAnalysis: null,
  queue: [],
  history: []
};

const API_BASE = 'http://127.0.0.1:8000/api';

const mediaUrlInput = document.getElementById('mediaUrl');
const analyzeBtn = document.getElementById('analyzeBtn');
const analysisResult = document.getElementById('analysisResult');
const audioOptions = document.getElementById('audioOptions');
const videoOptions = document.getElementById('videoOptions');
const queueList = document.getElementById('queueList');
const historyList = document.getElementById('historyList');
const dropZone = document.getElementById('dropZone');
const toast = document.getElementById('toast');

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast.timeout);
  showToast.timeout = setTimeout(() => toast.classList.remove('show'), 2200);
}

function validateUrl(value) {
  try {
    const url = new URL(value);
    return /https?:/.test(url.protocol);
  } catch {
    return false;
  }
}

async function createMediaProfile(url) {
  const response = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url })
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Unable to analyze media URL.');
  }

  return await response.json();
}

function renderOptions() {
  if (!state.currentAnalysis) {
    audioOptions.innerHTML = '';
    videoOptions.innerHTML = '';
    return;
  }

  audioOptions.innerHTML = audioQualities.map((quality, index) => `
    <button class="option-btn ${index === 0 ? 'active' : ''}" data-kind="audio" data-quality="${quality}">
      <span>${quality}</span>
      <small>${index < 2 ? 'Fast' : index === 2 ? 'Balanced' : 'High fidelity'}</small>
    </button>
  `).join('');

  videoOptions.innerHTML = videoQualities.map((quality, index) => `
    <button class="option-btn ${index === 4 ? 'active' : ''}" data-kind="video" data-quality="${quality}">
      <span>${quality}</span>
      <small>${quality === '4K' ? 'Ultra' : quality === '1080p' ? 'Premium' : 'Ready'}</small>
    </button>
  `).join('');
}

function renderQueue() {
  if (!state.queue.length) {
    queueList.innerHTML = '<div class="queue-item">No active downloads yet.</div>';
    return;
  }

  queueList.innerHTML = state.queue.map((item) => `
    <div class="queue-item">
      <strong>${item.title}</strong>
      <div class="meta">${item.format} • ${item.quality}</div>
      <div class="progress-track"><div class="progress-bar" style="width:${item.progress}%"></div></div>
      <div class="meta">${item.status} • ${item.progress}%</div>
      ${item.fileName ? `<a class="ghost-btn small" href="/downloads/${item.fileName}" target="_blank" rel="noopener">Download file</a>` : ''}
    </div>
  `).join('');
}

function renderHistory() {
  const query = document.getElementById('historySearch').value.toLowerCase();
  const filtered = state.history.filter((item) => `${item.title} ${item.format} ${item.status}`.toLowerCase().includes(query));

  if (!filtered.length) {
    historyList.innerHTML = '<div class="history-item">No history yet.</div>';
    return;
  }

  historyList.innerHTML = filtered.map((item) => `
    <div class="history-item">
      <strong>${item.title}</strong>
      <div class="meta">${item.format} • ${item.quality} • ${item.size}</div>
      <div class="meta">${item.status} • ${item.date}</div>
      ${item.fileName ? `<a class="ghost-btn small" href="/downloads/${item.fileName}" target="_blank" rel="noopener">Open file</a>` : ''}
    </div>
  `).join('');
}

function persistState() {
  localStorage.setItem('mediaforgeState', JSON.stringify({ history: state.history, queue: state.queue }));
}

function hydrateState() {
  const saved = localStorage.getItem('mediaforgeState');
  if (!saved) {
    state.history = [
      { title: 'Neon Nights', format: 'MP4', quality: '1080p', size: '1.4 GB', status: 'Completed', date: 'Today' },
      { title: 'Midnight Drift', format: 'MP3', quality: '320 kbps', size: '38 MB', status: 'Completed', date: 'Yesterday' }
    ];
    return;
  }

  try {
    const parsed = JSON.parse(saved);
    state.history = parsed.history || [];
  } catch {
    state.history = [];
  }
}

async function analyzeUrl() {
  const value = mediaUrlInput.value.trim();
  if (!validateUrl(value)) {
    showToast('Please enter a valid public media URL.');
    return;
  }

  analysisResult.classList.remove('hidden');
  document.getElementById('resultTitle').textContent = 'Analyzing…';
  document.getElementById('resultDescription').textContent = 'Preparing format preview and metadata.';

  try {
    const profile = await createMediaProfile(value);
    state.currentAnalysis = profile;
    document.getElementById('resultImage').src = profile.thumbnail;
    document.getElementById('resultTitle').textContent = profile.title;
    document.getElementById('resultDescription').textContent = profile.description;
    document.getElementById('resultDuration').textContent = `⏱ ${profile.duration}`;
    document.getElementById('resultAuthor').textContent = `👤 ${profile.author}`;
    document.getElementById('resultDate').textContent = `📅 ${profile.date}`;
    document.getElementById('resultViews').textContent = `👁 ${profile.views}`;
    renderOptions();
    showToast('Analysis complete. Choose a format to download.');
  } catch (error) {
    showToast(error.message || 'Analysis failed.');
  }
}

async function startDownload(kind, quality) {
  if (!state.currentAnalysis) {
    showToast('Analyze a URL before downloading.');
    return;
  }

  const response = await fetch(`${API_BASE}/downloads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      analysisId: state.currentAnalysis.id,
      title: state.currentAnalysis.title,
      fileType: kind === 'audio' ? 'MP3' : 'MP4',
      quality,
      size: kind === 'audio' ? '38 MB' : '1.4 GB',
      url: mediaUrlInput.value.trim()
    })
  });

  if (!response.ok) {
    showToast('Unable to queue the download.');
    return;
  }

  const entry = await response.json();
  state.queue.push({
    id: entry.id,
    title: state.currentAnalysis.title,
    format: kind === 'audio' ? 'MP3' : 'MP4',
    quality,
    size: kind === 'audio' ? '38 MB' : '1.4 GB',
    status: 'Queued',
    progress: 0,
    date: 'Just now',
    fileName: entry.fileName || ''
  });
  renderQueue();
  persistState();
  showToast(`${entry.fileType || 'Download'} ${quality} queued.`);

  let current = 0;
  const timer = setInterval(async () => {
    current += 10;
    if (current >= 100) {
      clearInterval(timer);
      await fetch(`${API_BASE}/downloads/${entry.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'Completed', progress: 100 })
      });
      state.history.unshift({
        title: state.currentAnalysis.title,
        format: kind === 'audio' ? 'MP3' : 'MP4',
        quality,
        size: kind === 'audio' ? '38 MB' : '1.4 GB',
        status: 'Completed',
        date: 'Just now',
        fileName: entry.fileName || ''
      });
      state.queue = state.queue.filter((item) => item.id !== entry.id);
      renderQueue();
      renderHistory();
      persistState();
      return;
    }

    await fetch(`${API_BASE}/downloads/${entry.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'Downloading', progress: current })
    });

    entry.progress = current;
    entry.status = 'Downloading';
    renderQueue();
  }, 180);
}

function animateCounters() {
  document.querySelectorAll('[data-counter]').forEach((el) => {
    const target = Number(el.dataset.counter);
    let current = 0;
    const step = Math.max(1, Math.round(target / 40));
    const timer = setInterval(() => {
      current += step;
      if (current >= target) {
        el.textContent = target.toLocaleString();
        clearInterval(timer);
      } else {
        el.textContent = current.toLocaleString();
      }
    }, 20);
  });
}

analyzeBtn.addEventListener('click', analyzeUrl);
mediaUrlInput.addEventListener('keydown', (event) => {
  if (event.ctrlKey && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    mediaUrlInput.focus();
  }
  if (event.key === 'Enter') {
    analyzeUrl();
  }
});

document.querySelectorAll('.chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    mediaUrlInput.value = chip.dataset.url;
    showToast('Sample URL inserted.');
  });
});

dropZone.addEventListener('dragover', (event) => {
  event.preventDefault();
  dropZone.style.borderColor = 'rgba(67, 216, 190, 0.6)';
});

dropZone.addEventListener('dragleave', () => {
  dropZone.style.borderColor = 'rgba(255, 255, 255, 0.24)';
});

dropZone.addEventListener('drop', (event) => {
  event.preventDefault();
  dropZone.style.borderColor = 'rgba(255, 255, 255, 0.24)';
  const url = event.dataTransfer.getData('text/plain');
  if (url) {
    mediaUrlInput.value = url;
    showToast('Link dropped into the analyzer.');
  }
});

analysisResult.addEventListener('click', (event) => {
  const button = event.target.closest('[data-kind]');
  if (!button) return;
  document.querySelectorAll('[data-kind]').forEach((item) => item.classList.remove('active'));
  button.classList.add('active');
  startDownload(button.dataset.kind, button.dataset.quality);
});

document.getElementById('clearQueueBtn').addEventListener('click', () => {
  state.queue = [];
  renderQueue();
  showToast('Queue cleared.');
});

document.getElementById('historySearch').addEventListener('input', renderHistory);

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      animateCounters();
      observer.disconnect();
    }
  });
}, { threshold: 0.4 });

observer.observe(document.querySelector('.metrics'));

hydrateState();
renderQueue();
renderHistory();

fetch(`${API_BASE}/downloads`)
  .then((response) => response.json())
  .then((downloads) => {
    if (downloads.length) {
      state.history = downloads.map((download) => ({
        title: download.title,
        format: download.fileType,
        quality: download.quality,
        size: download.size,
        status: download.status,
        date: download.createdAt.slice(0, 10)
      })).concat(state.history);
      renderHistory();
    }
  })
  .catch(() => {});
