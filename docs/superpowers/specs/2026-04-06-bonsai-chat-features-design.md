# Bonsai Chat — Feature Expansion Design

**Date:** 2026-04-06
**Goal:** Bring Bonsai Chat to feature parity with ChatGPT/Claude.ai for use as a demo/showcase app and personal local AI assistant.
**Approach:** Incremental enhancement of existing vanilla JS architecture. No framework migration.
**Model constraint:** Designed for 8B local model. Features that require large-model capability (Mermaid diagrams, artifacts/live preview, voice output) are excluded. LaTeX math is included (verified working on 8B).

---

## Architecture

### Frontend File Structure

Split `app.js` into focused modules loaded as separate `<script>` tags (no bundler):

```
chat/static/
  index.html
  style.css
  js/
    core.js           -- shared state, WebSocket, init
    messages.js       -- message rendering, markdown, code blocks, LaTeX
    conversations.js  -- sidebar, search, folders, export
    controls.js       -- stop/regenerate/edit, response actions
    uploads.js        -- drag-drop, file attachment, image preview
    memory.js         -- custom instructions, cross-convo memory
    shortcuts.js      -- keyboard shortcuts
    voice.js          -- Web Speech API mic input
    stats.js          -- token count, tokens/sec, response time
    settings.js       -- settings modal, model switcher
```

### Backend Additions

New REST endpoints on `app.py`:

```
GET  /api/conversations/search?q=...      -- full-text search
GET  /api/conversations/{id}/export        -- export as markdown/JSON
POST /api/memory                           -- save a memory
GET  /api/memory                           -- list memories
DELETE /api/memory/{id}                    -- delete a memory
GET  /api/models                           -- list available local models
DELETE /api/conversations/{id}/messages/last -- delete last assistant message (for regenerate)
POST /api/upload                           -- file upload (multipart)
```

### Database Changes

New tables:
- `memories`: id, content, created_at
- `conversation_folders`: id, name, sort_order

Column additions:
- `conversations`: add `folder_id`, `pinned`, `system_prompt`
- `messages`: add `token_count`, `generation_ms`, `model`, `attachments` (JSON)

### CDN Dependencies

- KaTeX (LaTeX math rendering)
- highlight.js (already added)
- marked.js (already present)

---

## Feature Designs

### 4.1 — Conversation Management

**Search (Cmd/Ctrl+K):**
- Overlay search bar drops down from top of chat area (command palette style)
- Searches conversation titles AND message content via SQLite `LIKE` query
- Results show conversation title + matching message snippet with highlighted term
- Click result opens conversation scrolled to matching message
- Escape or click-outside dismisses

**Export:**
- Three-dot menu on each conversation in sidebar (visible on hover)
- Options: "Export as Markdown", "Export as JSON"
- Markdown format: title as `# heading`, messages as `**User:** / **Assistant:**` with timestamps
- JSON format: raw message array including tool_calls
- Triggers browser download

**Folders & Pinning:**
- Pin icon on conversation hover — pinned convos stick to top under "Pinned" group label
- "New Folder" button in sidebar, drag conversations into folders, collapsible sections
- One level of nesting only

**Inline title editing:**
- Double-click conversation title in sidebar to edit inline
- Enter to save, Escape to cancel

### 4.2 — Response Controls

**Stop generation:**
- Send button transforms to Stop button (square icon, red tint) during streaming
- Sends `{type: "stop"}` via WebSocket — agent loop breaks out of streaming
- Keeps whatever has been generated so far

**Regenerate response:**
- "Regenerate" button (circular arrow) below last assistant message after completion
- Deletes last assistant message from DB and UI, re-sends last user message through agent loop

**Edit & resend user messages:**
- Pencil icon on hover over any user message
- Click turns bubble into editable textarea pre-filled with original text
- "Save & Resend" button — deletes all messages after that point, updates edited message, re-sends to agent

**Copy full response:**
- Clipboard icon on hover in top-right of each assistant message
- Copies raw markdown text (not rendered HTML)

### 4.3 — File & Image Uploads

**Attach button:**
- Paperclip icon left of textarea
- Accepts: `.txt`, `.py`, `.js`, `.ts`, `.json`, `.csv`, `.md`, `.html`, `.css`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`

**Drag-drop:**
- Drop zone overlay on drag-over: "Drop file here"
- Same flow as attach button

**File handling by type:**
- Text/code: read contents, inject as fenced code block with filename header
- Images: base64 data URL, inline thumbnail in message bubble, note that model cannot analyze images
- Large files (>50KB): truncate with notice

**Preview in chat:**
- Text files: collapsed preview (filename + first 3 lines), "Show full file" toggle
- Images: thumbnail (max 300px wide)

**Storage:**
- Files saved to `SANDBOX_DIR/uploads/` with UUID filenames
- `attachments` JSON column on messages: `[{filename, path, type, size}]`
- Backend: `POST /api/upload` accepts multipart form data

### 4.4 — Memory & Context

**Per-conversation system prompt:**
- Brain icon button in input footer
- Modal with textarea: "Set instructions for this conversation"
- Stored in `system_prompt` column on `conversations` table
- Prepended to system prompt in agent loop (before tool definitions)

**Cross-conversation memory:**
- "Save to Memory" bookmark icon on hover for each assistant message
- Click opens small modal: "What should I remember?" pre-filled, user confirms
- Stored in `memories` table: id, content, created_at
- All memories injected into system prompt as "Things you know about the user:" section
- Max 20 memories, oldest auto-pruned

**Memory management UI:**
- Accessible from Settings modal — "Memory" tab
- List of saved memories with delete buttons
- "Clear all" button

### 4.5 — Model Switching

**Model selector:**
- "Bonsai 8B" label becomes clickable dropdown in input footer
- Lists available models from `GET /api/models`
- Selected model stored in `localStorage`, sent with each WebSocket message

**Discovery:**
- Scan configured models directory (`BONSAI_MODELS_DIR` env var) for `.gguf` files on startup
- Fallback: single model shown as non-interactive label

**Switching behavior:**
- Takes effect on next message
- If llama-server only supports one model at a time, show "Restart required" note
- `model` column on `messages` table tracks which model generated each response

### 4.6 — LaTeX Math Rendering

**Library:** KaTeX (synchronous rendering, streaming-friendly)

**Syntax:**
- Inline: `$...$`
- Block: `$$...$$`

**Integration:**
- Pre-process markdown before `marked.parse()` — same pattern as `preprocessMarkdown`
- Replace `$$...$$` blocks first, then inline `$...$`
- Inline `$` matching: require no space after opening and no space before closing (avoid currency false positives)

**Error handling:**
- KaTeX parse failure: fall back to raw LaTeX in styled `<code>` block with subtle error indicator

### 4.7 — Keyboard Shortcuts & Polish

**Shortcuts:**
- `Ctrl/Cmd+K` — open conversation search
- `Ctrl/Cmd+N` — new chat
- `Ctrl/Cmd+Shift+Backspace` — delete current conversation
- `Escape` — close search/modals, cancel edit
- `Up Arrow` (in empty input) — edit last user message
- `?` or `Ctrl/Cmd+/` — show shortcuts help overlay

**Implementation:** Single `keydown` listener on `document` in `shortcuts.js`. Guard against firing when typing in input/textarea (except Escape).

**UI Polish:**
- Messages: 150ms fade-in on appear
- Tool pills: smooth expand/collapse transition
- Modals: fade + scale-up (150ms)
- Search overlay: slide-down from top (200ms)
- Skeleton loading: pulsing gray placeholders before first token
- Smooth scroll: `scrollIntoView({behavior: 'smooth'})` during streaming

### 4.8 — Voice Input

**Web Speech API:**
- Mic icon button between textarea and Send button
- Click to start — button turns red with pulse animation
- Click again or stop speaking to end
- Transcribed text inserted into textarea (not auto-sent, user can edit)

**Feature detection:**
- `if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)`
- Hide mic button entirely if unsupported (Chrome/Edge supported, Firefox/Safari limited)

### 4.9 — Token & Performance Display

**Per-message stats:**
- Subtle muted text line below each assistant response after completion
- Format: `127 tokens · 18.3 tok/s · 6.9s`

**Implementation:**
- Frontend tracks `streamStartTime`, `tokenCount`, `streamEndTime`
- Calculated client-side from WebSocket stream events
- Not persisted to DB (ephemeral)

**Context usage (low priority):**
- Parse `usage` data from llama-server's final SSE chunk if available
- Display: `1.2K / 8K context`

### 4.10 — Settings (Updated)

**Tabbed modal:**
- **General** — API keys (SerpAPI, OpenWeatherMap), sandbox directory
- **Memory** — saved memories list with delete buttons, "Clear all"
- **Keyboard Shortcuts** — read-only reference list of all shortcuts

---

## Skipped Features (8B Model Limitations)

- **Mermaid diagrams** — small models produce malformed syntax
- **Artifacts panel with live code preview** — requires generating complete runnable code in one shot
- **Voice output (TTS)** — 8B responses too choppy for natural speech
- **Complex multi-file artifact generation** — beyond 8B capability

---

## Implementation Order (Suggested)

Priority based on demo impact and utility:

1. Response Controls (stop, regenerate, edit) — highest UX impact
2. Keyboard Shortcuts & Polish — makes the whole app feel professional
3. Conversation Management (search, export, folders) — essential for daily use
4. File Uploads — impressive in demos
5. Token & Performance Display — quick win, adds credibility
6. LaTeX Math — niche but differentiating
7. Memory & Context — useful for personal assistant mode
8. Model Switching — infrastructure feature
9. Voice Input — nice-to-have, easy to add
10. Settings Update — ties together memory + shortcuts tabs
