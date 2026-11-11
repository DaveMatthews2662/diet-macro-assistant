# Technical Blueprint & Architecture Summary (Reusable Project Template)

This document captures the full stack, architecture, governance rules, and design patterns used across projects so any new project can be spun up using the exact same methodology.

---

## 1. Core Stack & Platforms

- Interface: Telegram Bot API (mobile + desktop chat, photos/screenshots, voice memos, zero frontend maintenance)
- AI Engine: Google Gemini REST API (`generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`)
  - Primary model: `gemini-3.5-flash`
  - Fallbacks: `gemini-3.5-flash-lite`, `gemini-3.6-flash`, `gemini-2.5-flash`
  - Internal reasoning: `thinkingConfig: {"thinkingBudget": 1024..2048}` (automatically stripped on retry for speed)
- Language & Runtime: Python 3 using standard library only (`http.server`, `urllib`, `json`, `threading`, `re`, `ssl`, `hashlib`, `hmac`, `base64`) — zero external `pip` dependencies required on the server
- 24/7 Cloud Hosting: Render.com Free Web Service (`bot/render.yaml`)
  - Self-pinging keep-alive thread every 8 minutes (`480s`) so the free container never sleeps
  - Single Render instance can host multiple project Telegram bots simultaneously on separate webhook paths (`/webhook`, `/wabbits-webhook`, etc.)
- Source Control & Continuous Deployment: Git + GitHub (`git push origin main` automatically triggers a Render redeploy in ~60 seconds)
- Development Environment: Antigravity IDE / VS Code with full local computer access

---

## 2. Standardized Repository Layout

Every project follows a clean, categorized folder structure:

```text
project-root/
├── rules/
│   └── MasterRules.md             # Single source of truth for behavior, formatting, and domain rules
├── memory/
│   ├── ProjectMemory.md           # Governance, Action Commands, Backlog, and Staging lists
│   ├── ErrorLog.md                # Permanent error log, mistake registry, and sprawl inventory
│   └── persistent_overrides.json  # Runtime additions, removals, and Telegram notes synced to cloud
├── inventory/
│   ├── FoodInventory.md           # Human-readable categorized inventory
│   └── InventoryData.json         # Exact macro database with verified decimal values
├── bot/
│   ├── telegram_agent.py          # Webhook server, message batching, Gemini caller, cloud sync
│   ├── render.yaml                # Render service blueprint
│   ├── .telegram_token            # Local gitignored bot token
│   └── .gemini_key                # Local gitignored Gemini API key
├── archive/                       # Superseded documents, duplicate configs, and deprecated files
├── .agents/rules/                 # Pinned IDE rules (workspace.md, mandatory_approval.md, roger_roger.md)
├── requirements.txt               # Single root requirements file (stdlib only)
├── telegram_agent.py              # Root shim: from bot.telegram_agent import run_bot
└── TECHNICAL_BLUEPRINT.md         # This reusable architecture blueprint
```

---

## 3. Core Governance & Action Commands

### A. Two-Beat Confirmation Rule
- Never modify files, code, configs, or system settings during diagnosis or explanation.
- Always stage proposed changes in Staging, explain what will be done, and ask: "Ready to execute?".
- Only execute when Aaron explicitly replies "go", "execute", or "3".

### B. Numbered Action Command System
Typing the number (1-7) or trigger phrase runs the action immediately:
- [1] pull backlog (or 1): Displays current exploratory ideas and Telegram dumps from memory/ProjectMemory.md.
- [2] pull staging (or 2): Displays concrete pending changes that are planned, designed, and strictly paused waiting for approval.
- [3] execute staging (or 3): The official green light. Applies all staged changes across files and configs.
- [4] sync all (or 4): Multi-level full sync across local files, GitHub, Telegram cloud, and Render.
- [5] pull error log (or 5): Displays the top recurring mistakes and guardrails from memory/ErrorLog.md.
- [6] status (or 6): Quick 3-bullet summary of project health, active files, and last sync timestamp.
- [7] list actions (or 7): Displays this numbered menu anytime.

### C. Continuous Error Logging
- Whenever Aaron corrects the agent or flags an issue, append it immediately to `memory/ErrorLog.md` before replying.

### D. No Asterisk Clutter & Readability
- Never use asterisks (* or **) in chat responses. Use clean dashes (-), numbers (1-7), and plain headers.
- Always format all lists and questions with explicit double line breaks so they never collapse into walls of text in the chat UI.

---

## 4. Key Methodologies & Design Patterns

### A. File-Backed Context Injection (No Vector DB Overhead)
- Every turn loads `rules/MasterRules.md` and structured JSON/Markdown data files directly into Gemini's `system_instruction`.
- Keeps retrieval 100% accurate with zero latency or synchronization bugs.

### B. 2-Second Per-Chat Message & Media Batching
- Incoming Telegram messages, screenshots, and voice notes are buffered per `chat_id` for `2.0` seconds (`threading.Timer`) before calling Gemini.
- Sending multiple screenshots or a screenshot followed by text produces one unified reply instead of overlapping responses.
- Telegram `update_id` values are deduplicated in memory (`SEEN_UPDATES`).

### C. Idea-Dump Protocol (`Roger Roger.`)
- When Aaron sends an idea dump or asks to silently save a note without returning it in chat, the bot replies strictly `Roger Roger.` plus a 1-line update summary and persists the note to Telegram cloud storage.

### D. Ephemeral Disk Survival via Telegram Cloud Storage
- State is JSON-serialized, base64-encoded into 240-char chunks, and stored in Telegram's cloud via `setMyCommands` / `getMyCommands` under a hidden scope (`all_chat_administrators`, `language_code: "eo"`).
- On container startup, the bot restores and merges cloud state automatically.

### E. Multi-Bot Hosting + Encrypted Vault Pattern
- Multiple Telegram bots share one Render web service by routing webhook paths (`/webhook`, `/wabbits-webhook`, etc.) in `BotHTTPHandler.do_POST`.
- Secondary project context files are encrypted using PBKDF2-HMAC-SHA256 into vault files (`wabbits_vault.json`, `lifting_vault.json`) inside the Render repo.

### F. Rolling Multimodal Conversation Memory
- The last 12 turns per `chat_id` are kept in `CHAT_MEMORY`.
- Base64 images and audio are retained for the last 4 entries and stripped from older turns (`[Earlier Screenshot]`) to keep requests fast and prevent timeouts.
