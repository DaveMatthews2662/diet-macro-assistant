# Technical Blueprint & Architecture Summary (Reusable Project Template)

This document captures the full stack, architecture, and design patterns used in Diet & Macro Assistant and Hunting Wabbits so any new project can be spun up using the exact same methodology.

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

## 2. Repository Layout Pattern

Every project follows a clean, categorized folder structure:

```text
project-root/
├── rules/
│   └── MasterRules.md             # Single source of truth for behavior, formatting, and domain rules
├── memory/ (or inventory/)
│   ├── ProjectMemory.md           # Structured human-readable state / inventory / knowledge base
│   ├── DecisionLog.md             # Chronological log of updates and decisions
│   └── persistent_overrides.json  # Runtime additions, removals, and Telegram notes synced to cloud
├── bot/
│   ├── telegram_agent.py          # Webhook + local polling server, batching, Gemini caller, cloud sync
│   ├── render.yaml                # Render blueprint
│   ├── requirements.txt           # Stdlib-only note
│   ├── .telegram_token            # Local gitignored bot token
│   └── .gemini_key                # Local gitignored Gemini API key
├── telegram_agent.py              # Root shim: from bot.telegram_agent import run_bot
├── PROJECT_SUMMARY.md             # Context overview for AI coding agents
└── TECHNICAL_BLUEPRINT.md         # This reusable architecture blueprint
```

---

## 3. Key Methodologies & Design Patterns

### A. File-Backed Context Injection (No Vector DB Overhead)
- Instead of maintaining an external SQL/vector database for personal-scale data, every turn loads `rules/MasterRules.md` and the structured Markdown/JSON data files directly into Gemini's `system_instruction`.
- Keeps retrieval 100% accurate with zero latency or synchronization bugs.

### B. 2-Second Per-Chat Message & Media Batching
- Incoming Telegram messages, screenshots, and voice notes are buffered per `chat_id` for `2.0` seconds (`threading.Timer`) before calling Gemini.
- Sending multiple screenshots or a screenshot followed by text produces one unified reply instead of overlapping responses.
- Telegram `update_id` values are deduplicated in memory (`SEEN_UPDATES`).

### C. Idea-Dump & Project-Communication Mode (`Roger Roger.`)
- The Telegram bot serves as both the domain assistant and a mobile bridge to the project while away from the PC.
- When Aaron sends an idea dump, a note/rule for when he gets back to his computer, or asks to save something as a project file without returning it in the chat message, the bot replies only `Roger Roger.` and persists the note to Telegram cloud storage and local project memory.

### D. Ephemeral Disk Survival via Telegram Cloud Storage
- Because Render's free tier wipes local disk on redeploy/restart, runtime state (inventory additions/removals, likes/dislikes, project notes, and rules) is JSON-serialized, base64-encoded into 240-char chunks, and stored in Telegram's cloud via `setMyCommands` / `getMyCommands` under a hidden scope (`all_chat_administrators`, `language_code: "eo"`).
- On container startup, the bot restores and merges cloud state automatically.

### E. Multi-Bot Hosting + Encrypted Vault Pattern (For Private Projects)
- Multiple Telegram bots can share one Render web service by routing webhook paths (`/webhook`, `/wabbits-webhook`, etc.) in `BotHTTPHandler.do_POST`.
- If a secondary project lives in a separate local repository, a local sync script (`bot/sync_to_render.py`) bundles and encrypts its context files using PBKDF2-HMAC-SHA256 keyed by `GEMINI_API_KEY` into a vault file (`wabbits_vault.json`) inside the Render-deployed repo.

### F. Rolling Multimodal Conversation Memory
- The last 12 turns per `chat_id` are kept in `CHAT_MEMORY`.
- Base64 images and audio are retained for the last 4 entries (so follow-up questions still see the screenshot or voice memo) and stripped from older turns (`[Earlier Screenshot]`) to keep requests fast and prevent timeouts.

---

## 4. Checklist for Starting a New Project With This Blueprint

1. Create the project folder under `c:\Users\aaron\OneDrive\Desktop\My Projects\<project-name>` with `rules/MasterRules.md`, `memory/`, and `bot/telegram_agent.py`.
2. Create a Telegram bot via `@BotFather` and save the token to `bot/.telegram_token` (gitignored).
3. Copy `bot/.gemini_key` (gitignored) from an existing project.
4. Define the project's domain rules, communication style (ultra-short, zero fluff, no markdown asterisk clutter), and `Roger Roger.` Idea-Dump Mode in `rules/MasterRules.md`.
5. Either deploy as a new Render web service (`bot/render.yaml`) or add a webhook route (`/newproject-webhook`) to the existing Render server for instant 24/7 hosting.
