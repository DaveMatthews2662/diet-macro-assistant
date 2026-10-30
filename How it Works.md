# How It Works — Diet & Macro Assistant

I built a personal AI nutritionist that lives in Telegram. I text it (or send a Cronometer screenshot) and it tells me exactly what to eat, down to the gram, to hit my daily macros.

---

## Part 1: How to Explain It

### Simple version
> "I built my own AI nutritionist inside Telegram. It knows everything in my kitchen and the exact nutrition facts for each item. It also knows my goals (about 1,900 calories and 170–185g of protein a day) and what I like and hate. I text it, or send a screenshot of my Cronometer log, and it tells me what to make and how many grams to weigh out."

### Casual / tech-savvy version
> "I built a custom Python agent on Telegram, hosted 24/7 on Render, that calls Google's Gemini API. It's grounded in a JSON nutrition database of my real kitchen inventory plus a strict rules file. I can send a Cronometer screenshot and its vision model reads my consumed macros and calculates options for what's left. I can also add or remove foods by text."

### Technical version
> "It's a stateful multimodal agent written in stdlib-only Python. It runs as a webhook service on Render and deploys from GitHub on every push.
> - **Interface:** Telegram Bot API (webhook `POST /webhook`, polling fallback locally) with an 8-minute self-ping to keep the free tier awake. Messages and photos arriving within 2 seconds are batched into one reply.
> - **LLM and vision:** Gemini via REST `generateContent`. Models in order: `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`. `thinkingBudget` is 8192, with 2 retry rounds.
> - **Grounding (no vector DB, since there are only ~154 items):** each turn injects `rules/MasterRules.md`, `inventory/FoodInventory.md`, and a shuffled copy of `inventory/InventoryData.json`, plus a random 25-food spotlight, a 'recently suggested' block, and a removed-items blocklist.
> - **Persistence:** `inventory/persistent_overrides.json` stores removed, added, liked, and disliked items. It is re-applied on every context load, and it is also backed up to Telegram's cloud storage so it can survive Render's ephemeral disk."

---

## Part 2: Tools and Platforms

| Role | Tool |
| :--- | :--- |
| Chat interface | **Telegram** + **Telegram Bot API** |
| AI (text + vision) | **Google Gemini API** (`gemini-3.6-flash`, with `gemini-3.5-flash` and `gemini-3.5-flash-lite` fallbacks) |
| Language | **Python 3**, standard library only (`http.server`, `urllib`, `json`, `threading`, `re`) |
| 24/7 hosting | **Render.com** (free web service, `bot/render.yaml`) |
| Code backup and deploy trigger | **Git + GitHub** (`DaveMatthews2662/diet-macro-assistant`) |
| Daily food logging | **Cronometer** (external; I send screenshots) |
| Macros for newly added items | **USDA FoodData Central API** |
| Build environment | **Antigravity IDE** with an AI coding agent |
| Extra state backup | **Telegram cloud storage** (via `setMyCommands`/`getMyCommands`) |

I use **no** n8n, Zapier, or Make. The automation is plain Python.

---

## Part 3: Where Things Are Saved

1. **My PC** — the working folder I edit in Antigravity. API keys (`bot/.telegram_token`, `bot/.gemini_key`) live only here and in Render's environment variables. They are gitignored.
2. **GitHub** — the backup of all code, rules, and inventory.
3. **Render** — the live bot. It redeploys automatically after each push.
4. **Telegram cloud** — a backup of `persistent_overrides.json`.

> **Important:** Render's free tier has an ephemeral disk. Any file the bot edits while running (inventory, overrides) reverts to the GitHub version after a restart or redeploy. That is why removals are re-applied from `persistent_overrides.json` on every load.

---

## Part 4: Repo Structure

```text
diet-macro-assistant/
├── rules/
│   └── MasterRules.md             # Macro goals, formatting rules, likes/dislikes, workflow
├── inventory/
│   ├── FoodInventory.md           # Human-readable kitchen inventory
│   ├── InventoryData.json         # Nutrition database (~154 items, Cronometer/USDA values)
│   └── persistent_overrides.json  # Removed/added/liked/disliked items that must persist
├── bot/
│   ├── telegram_agent.py          # The whole bot
│   ├── render.yaml                # Render deployment blueprint
│   └── requirements.txt
├── telegram_agent.py              # Small shim that calls bot.telegram_agent.run_bot
└── How it Works.md                # This file
```

---

## Part 5: What Happens When I Send a Message

1. I send text or a screenshot on Telegram.
2. Telegram forwards it to my Render server (`POST /webhook`).
3. The bot waits about 2 seconds to batch any follow-up messages or photos.
4. If the text is a command (`add/remove X ... inventory`, add to like/dislike list), the bot handles it directly. Otherwise it continues.
5. The bot loads the rules, inventory, and macro database, and applies the persistent removals.
6. It builds the prompt: system rules, the removed-items blocklist, a random food spotlight, recent suggestions, and the last 12 chat turns (images kept for the last 6).
7. Gemini reads it all, does the macro math, and writes the plan.
8. The reply goes back to my phone through Telegram.

## Commands
- `add X to inventory` / `remove X from inventory` (multiple items like "X and Y" work)
- `add X to like list` / `add X to don't like list`
- Any question, for example "what gets me to 180g protein?" or "what should I order at Chipotle?" (restaurant answers are estimates from Gemini's general knowledge, with no live menu lookup)

## Known Limitations
- Telegram-cloud backup of removals is implemented but not yet verified against the live Telegram API. The bot logs `[overrides] ...` lines in Render's logs, so success or failure is visible there.
- Chat memory and batching state are in RAM and reset on each restart.
- New-item macros come from the USDA API (`DEMO_KEY`, rate limited) and fall back to generic values if the lookup fails.
