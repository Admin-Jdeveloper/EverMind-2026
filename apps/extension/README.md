# MediaCompile Web Clipper (Chrome Manifest V3)

The MediaCompile Web Clipper lets you save articles, research notes, and selected text directly from your browser into your private MediaCompile library with full user consent.

---

## Minimal Permissions Policy
- **`activeTab`**: Only accesses the current webpage when you explicitly click the extension icon. It never runs background tracking scripts or inspects unclicked tabs.
- **`storage`**: Securely persists your MediaCompile API endpoint URL and authentication token locally on your device.

---

## Installation (Developer Mode)

1. Open your Chromium-based browser (Chrome, Edge, Brave, Arc, Opera) and navigate to:
   - Chrome: `chrome://extensions`
   - Edge: `edge://extensions`
   - Brave: `brave://extensions`
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked**.
4. Select the `apps/extension` directory from your MediaCompile workspace.
5. The **MediaCompile Web Clipper** icon will appear in your extensions bar!

---

## Configuration & Usage

1. Click the extension icon.
2. Click **Settings & Auth** at the bottom of the popup.
3. Configure your API Base URL (defaults to `http://127.0.0.1:8000`).
4. Paste your signed JWT token (generated from the MediaCompile web app).
5. Click **Save Settings**.
6. On any article or webpage, open the popup, optionally select a collection or enter tags/notes, and click **Save to Personal Library**!
