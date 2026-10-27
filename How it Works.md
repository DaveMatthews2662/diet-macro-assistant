# How It Works — Diet & Macro Assistant

This document explains everything about what you built, the exact tech stack behind it, where your data lives, and **three ready-to-use ways to explain it to anyone** (ELI12, Casual / Cocktail Party, and Technical).

---

## Part 1: How to Explain What You Built (3 Versions)

### 1. The ELI12 Answer (Explain Like I'm 12)
> "I built my own personal AI nutritionist that lives inside a text message chat on my phone (Telegram).
>
> It has a complete list of every food, snack, and spice in my kitchen, plus the exact nutrition facts for all of them. It also knows my exact daily fitness goals (1,900 calories and 180g of protein) and what foods I like or hate.
>
> Anytime I'm hungry, I just text it—or send it a screenshot of my food tracker app (Cronometer) or a grocery receipt—and in one second it tells me the exact meals to make and the exact gram weights to put on my food scale so I hit my goals on the dot."

---

### 2. The Casual / "Tech-Savvy" Answer (What to Tell Friends or Co-Workers)
> "I got tired of generic meal apps and ChatGPT forgetting what's actually in my fridge, so I built a custom, cloud-hosted AI agent wired into Telegram.
>
> Instead of using a basic no-code wrapper like Zapier or n8n, I built a custom Python backend deployed on Render that runs 24/7 and hits Google's Gemini 3.5 Flash multimodal API.
>
> It's grounded in a custom JSON nutrition database of my actual kitchen inventory—Costco steaks, H-E-B groceries, spices, everything—and a strict rules engine. I can text it a screenshot of my Cronometer log mid-day, and its vision model reads my remaining macros and calculates meal options down to the exact gram for my food scale. I can even snap a photo of a grocery receipt and it OCRs the items straight into my database."

---

### 3. The Full Technical Answer (What to Tell Software Engineers)
> "It's a custom, stateful multimodal AI agent written in Python and deployed as a 24/7 containerized web service on Render via a GitHub CI/CD pipeline.
>
> **Architecture & Stack:**
> - **Interface Layer:** Telegram Bot API running in hybrid Webhook (`POST /webhook`) + HTTP health-check mode with an internal 8-minute self-ping keep-alive loop to prevent container spin-down.
> - **LLM & Vision Engine:** Google `gemini-3.5-flash` (with automatic failover to `gemini-3-flash-preview` and `gemini-3.5-flash-lite`) via the REST `generateContent` endpoint.
> - **Context & Grounding (RAG-Lite / File-Backed State):** Rather than using a heavy vector database for a ~160-item domain, the agent injects deterministic structured state on every turn from three local sources of truth:
>   1. `rules/MasterRules.md` — System prompt constraints, macro targets (`1,900 kcal | 180g P | 190g C | 55–60g F`), finite raw-meat tracking, and output formatting rules.
>   2. `inventory/FoodInventory.md` — Categorized kitchen inventory.
>   3. `inventory/InventoryData.json` — Verified USDA FoodData Central & Cronometer-synced nutrition schema with gram-first serving weights.
> - **Multimodal Capabilities:** Handles both Cronometer screenshot parsing (extracting consumed macros while ignoring app target denominators) and grocery receipt OCR (mutating both the Markdown inventory and JSON macro store in real time)."

---

## Part 2: Quick Answers to Your Questions

### 1. Are we using n8n?
**No.** We are **not** using n8n, Zapier, Make, or any third-party drag-and-drop automation tool.
- **Why?** Tools like n8n add a middleman server, monthly subscription limits, and extra delay. Instead, we wrote the automation directly in Python ([`bot/telegram_agent.py`](bot/telegram_agent.py)). Your code talks directly from Telegram → your Render server → Google Gemini → back to your phone in ~1 second for free.

---

### 2. What Tools, Platforms, AI Models & Agents Are We Using?

You are actually using **two separate AI agents** that work as a team:

| Role | Tool / Platform | AI Model Used | What It Does |
| :--- | :--- | :--- | :--- |
| **1. The "Builder" Agent (On Your PC)** | **Google Antigravity IDE** (what you're typing in right now) | **Gemini 4 Argon (Medium)** | Your AI software engineer. It edits your code, updates your rules/inventory files, tests the math, and pushes updates to GitHub. |
| **2. The "Live Nutritionist" Agent (On Your Phone)** | **Telegram App** + **Render.com Cloud Server** | **Google Gemini 3.5 Flash** (`gemini-3.5-flash`) | Your 24/7 personal food picker. It reads your texts/screenshots on Telegram and replies in ~1 second using your kitchen database. |

#### Full List of Platforms & Frameworks:
- **Programming Language:** **Python 3** (standard library `http.server`, `urllib`, `json`, `threading`—zero bloated frameworks so it runs fast and never breaks).
- **Chat Frontend:** **Telegram** (Mobile + Desktop app) via the **Telegram Bot API**.
- **AI / Vision Engine:** **Google Gemini API** (`gemini-3.5-flash` for instant multimodal vision + math).
- **Code Repository & Version Control:** **Git & GitHub** (`https://github.com/DaveMatthews2662/diet-macro-assistant`).
- **24/7 Cloud Hosting:** **Render.com** (Cloud Web Service connected to your GitHub repo).
- **Daily Macro Logger (External):** **Cronometer** (you log food there and send screenshots to the bot).

---

### 3. Where Is Everything Being Saved?

Everything is saved in **three synced places**:

1. **On Your Computer (Local Workspace):**
   - Folder: `C:\Users\Aaron\Desktop\diet-macro-assistant`
   - This is where we make edits inside Antigravity IDE.
   - *(Note: Your secret API keys `.telegram_token` and `.gemini_key` are saved **only** on your computer in `bot/` and in Render's encrypted Environment Variables—they are blocked by `.gitignore` so they are never exposed publicly on GitHub).*
2. **On GitHub (Cloud Code Backup):**
   - Repo: `github.com/DaveMatthews2662/diet-macro-assistant`
   - Every time we finish an update here in chat, I run `git commit` and `git push` to save a permanent backup of your rules, inventory, and bot code to GitHub.
3. **On Render.com (Live 24/7 Cloud Server):**
   - Render watches your GitHub repo. The moment we push an update to GitHub, Render automatically downloads the latest files and restarts your live bot in ~60 seconds.

---

### 4. How Does the Repo Work? (Folder Structure)

Your repository is organized into **3 clean folders**:

```text
diet-macro-assistant/
│
├── rules/
│   └── MasterRules.md        <-- The "Brain Rules": your macro goals (1900 kcal / 180P / 190C / 55-60F),
│                                 formatting rules (grams only, no decimals, no fiber), and Likes/Dislikes.
│
├── inventory/
│   ├── FoodInventory.md      <-- Human-readable list of every food, meat, snack, and spice in your kitchen.
│   └── InventoryData.json    <-- The nutrition database: exact gram weights, calories, protein, carbs, and fat
│                                 for all 156+ items in your kitchen (synced with USDA & Cronometer).
│
└── bot/
    ├── telegram_agent.py     <-- The Python engine that connects Telegram, Render, and Gemini 3.5 Flash.
    ├── meal_catalog.py       <-- Pre-built meal templates and macro calculation helpers.
    ├── render.yaml           <-- Cloud blueprint telling Render how to run the server.
    └── requirements.txt      <-- Python package list for Render.
```

---

### 5. Step-by-Step: What Happens When You Send a Text on Telegram?

1. **You send a text or screenshot** on Telegram (e.g., *"Give me 3 dinner options"* or a Cronometer screenshot).
2. **Telegram's servers** instantly forward that message to your **Render.com cloud server** via a Webhook (`POST /webhook`).
3. **Your Python script (`bot/telegram_agent.py`)** wakes up and bundles together:
   - Your message or screenshot image
   - Your recent chat history
   - All of `rules/MasterRules.md`
   - All of `inventory/FoodInventory.md`
   - All 156+ items from `inventory/InventoryData.json`
4. **Google Gemini 3.5 Flash** reads that entire bundle, does the gram-weight and macro math against your `1,900 kcal | 180g P | 190g C | 55–60g F` goals, formats it with zero fluff, and sends the answer back through Render to your Telegram app in ~1 second.

