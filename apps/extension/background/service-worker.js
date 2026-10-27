/**
 * MediaCompile Web Clipper — Background Service Worker (Manifest V3)
 * Handles lifecycle events and background clip messaging.
 */

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    chrome.storage.local.set({
      apiBase: 'http://127.0.0.1:8000',
      authToken: '',
    });
  }
});
