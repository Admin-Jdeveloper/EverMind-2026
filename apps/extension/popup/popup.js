document.addEventListener('DOMContentLoaded', async () => {
  const pageTitleInput = document.getElementById('pageTitle');
  const pageUrlInput = document.getElementById('pageUrl');
  const collectionSelect = document.getElementById('collectionSelect');
  const pageTagsInput = document.getElementById('pageTags');
  const userNotesInput = document.getElementById('userNotes');
  const clipForm = document.getElementById('clipForm');
  const submitBtn = document.getElementById('submitBtn');
  const btnText = document.getElementById('btnText');
  const spinner = document.getElementById('spinner');
  const statusAlert = document.getElementById('statusAlert');
  const toggleConfigBtn = document.getElementById('toggleConfigBtn');
  const configSection = document.getElementById('configSection');
  const apiBaseInput = document.getElementById('apiBase');
  const authTokenInput = document.getElementById('authToken');
  const saveConfigBtn = document.getElementById('saveConfigBtn');

  // Load configuration from local storage
  let apiBase = 'http://127.0.0.1:8000';
  let authToken = '';

  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
    chrome.storage.local.get(['apiBase', 'authToken'], (result) => {
      if (result.apiBase) {
        apiBase = result.apiBase;
        apiBaseInput.value = apiBase;
      }
      if (result.authToken) {
        authToken = result.authToken;
        authTokenInput.value = authToken;
      }
      loadCollections();
    });
  } else {
    loadCollections();
  }

  // Get active tab info
  if (typeof chrome !== 'undefined' && chrome.tabs && chrome.tabs.query) {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs && tabs[0]) {
        const tab = tabs[0];
        pageTitleInput.value = tab.title || '';
        pageUrlInput.value = tab.url || '';
      }
    });
  } else {
    pageTitleInput.value = 'Demo: Distributed Consensus in PostgreSQL';
    pageUrlInput.value = 'https://example.com/demo-article';
  }

  // Toggle settings
  toggleConfigBtn.addEventListener('click', () => {
    configSection.classList.toggle('hidden');
  });

  saveConfigBtn.addEventListener('click', () => {
    apiBase = apiBaseInput.value.trim().replace(/\/$/, '');
    authToken = authTokenInput.value.trim();

    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      chrome.storage.local.set({ apiBase, authToken }, () => {
        showAlert('Settings saved successfully.', 'success');
        configSection.classList.add('hidden');
        loadCollections();
      });
    } else {
      showAlert('Settings saved in-memory.', 'success');
      configSection.classList.add('hidden');
    }
  });

  async function loadCollections() {
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

      const res = await fetch(`${apiBase}/api/v1/content/collections/`, { headers });
      if (res.ok) {
        const data = await res.json();
        const list = Array.isArray(data) ? data : (data.results || []);
        collectionSelect.innerHTML = '<option value="">Unfiled Library</option>';
        list.forEach((c) => {
          const opt = document.createElement('option');
          opt.value = c.id;
          opt.textContent = c.name;
          collectionSelect.appendChild(opt);
        });
      }
    } catch {
      // Offline / unauthenticated
    }
  }

  clipForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideAlert();

    const title = pageTitleInput.value.trim();
    const url = pageUrlInput.value.trim();
    const collectionId = collectionSelect.value || null;
    const tags = pageTagsInput.value.split(',').map((t) => t.trim()).filter(Boolean);
    const notes = userNotesInput.value.trim();

    setLoading(true);

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

      const res = await fetch(`${apiBase}/api/v1/content/clip/`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          url,
          title,
          collection_id: collectionId,
          tags,
          notes,
        }),
      });

      const data = await res.json();

      if (res.ok) {
        if (data.is_duplicate) {
          showAlert(`Already in library! Updated notes.`, 'warning');
        } else {
          showAlert(`Saved to MediaCompile library! (${data.chunk_count || 1} chunks indexed)`, 'success');
        }
      } else {
        const err = data.error || (data.url ? data.url[0] : 'Failed to clip page.');
        showAlert(err, 'error');
      }
    } catch (err) {
      showAlert('Could not contact MediaCompile API. Check Settings & Auth.', 'error');
    } finally {
      setLoading(false);
    }
  });

  function showAlert(msg, type) {
    statusAlert.textContent = msg;
    statusAlert.className = `alert ${type}`;
    statusAlert.classList.remove('hidden');
  }

  function hideAlert() {
    statusAlert.classList.add('hidden');
  }

  function setLoading(loading) {
    submitBtn.disabled = loading;
    if (loading) {
      btnText.textContent = 'Saving...';
      spinner.classList.remove('hidden');
    } else {
      btnText.textContent = 'Save to Personal Library';
      spinner.classList.add('hidden');
    }
  }
});
