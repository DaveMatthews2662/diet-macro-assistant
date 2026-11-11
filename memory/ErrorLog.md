# Error & Mistake Log: Diet & Macro Assistant

This document serves as the permanent historical error log, mistake registry, and continuous learning ledger for `diet-macro-assistant`.

---

## 1. Permanent Continuous Logging Protocol

> **MANDATORY RULE:** Starting immediately and in all future turns:
> Whenever Aaron corrects the agent, points out a mistake, or flags a forgotten rule, the agent **must automatically append it to this document (`memory/ErrorLog.md`) before replying**.
> **Never let an error go unrecorded.**

---

## 2. Standard Action Commands

The following standard trigger commands are codified for this workspace:
- **`pull backlog`** $\rightarrow$ Reads and displays current exploratory ideas, brainstorms, and unprocessed Telegram mobile idea dumps from `memory/ProjectMemory.md`.
- **`pull staging`** $\rightarrow$ Reads and displays concrete pending changes that are planned, designed, and strictly paused waiting for Aaron's `"go"` or `"execute"` from `memory/ProjectMemory.md`.
- **`pull error log`** $\rightarrow$ Reads and displays the top recurring mistakes, recent errors, and preventive guardrails from this file (`memory/ErrorLog.md`).

---

## 3. Harvested Error & Mistake Registry

### Entry 1: Cross-Project Pollution on `0` Shorthand Command (Code Red)
- **Date / Timestamp:** 2026-11-09 13:50:54 UTC
- **What Went Wrong & Aaron's Quote:**
  > *"Whoa, this is kind of a code red. I don't know what's going on, absolutely need to be fixed immediately. I sent Telegram messages to my diet macro assistant about this project. For some reason when I got home, you're talking about my hunting wabbits project, which is a different project. You're talking about learning book notes and cover letters, all of that is an entirely separate project. Why did this happen and make it never happen again?"*
- **Root Cause:**
  When Aaron triggered `0` (the shorthand command to pull mobile updates from Telegram cloud storage), the agent searched across all connected cloud storage namespaces and un-isolated workspace files, polluting `diet-macro-assistant` with notes from `hunting-wabbits`. There was no pinned workspace-level isolation rule stopping cross-repo queries.
- **Current Status:** **Resolved**
  Created and pinned `.agents/rules/strict_project_isolation.md` and Rule 2h/2i in `rules/MasterRules.md`, strictly enforcing zero cross-contamination and bounding `0` solely to `diet-macro-assistant`.

---

### Entry 2: Deploy Failure on Render due to Syntax Error in Shared Bot Code
- **Date / Timestamp:** 2026-11-09 14:37:48 UTC
- **What Went Wrong & Aaron's Quote:**
  > *"got this error today. please fix? could it possibly be because I changed the bot name? also. i want to start doing everything in here uniform. Can you change every naming to follow diet-macro-assistant (include -bot) if it makes sense. no more Macro Dave... 9 min ago. failure and MacroDave still showing up"*
- **Root Cause:**
  A multi-line raw string concatenation in `bot/lifting_agent.py` line 294 caused a `SyntaxError: unterminated string literal`, breaking Python compilation and causing Render build deployments to fail. In addition, the Render web service dashboard still carried the legacy service name `MacroDave`.
- **Current Status:** **Resolved**
  Fixed the syntax error with properly escaped newline characters, verified syntax with `python -m py_compile`, renamed the service across all configs to `diet-macro-assistant`, and confirmed live health check (`200 OK`).

---

### Entry 3: Telegram Bot Dumping Long Answers & Misidentifying Screenshots as Receipts
- **Date / Timestamp:** 2026-11-08 19:31:19 UTC
- **What Went Wrong & Aaron's Quote:**
  > *"How come when I sent it in my hunting rabbits project, it, it replied back just okay, like that's what I want. And then for some reason in my macro Telegram bot, it didn't listen to me. It sent the whole answer right there in the message when I specifically said not to. and then when I sent it a screenshot in the macro assistant bot, it pretended like I sent a receipt or something... I should be able to use my macro assistant Telegram bot to communicate with this project and make changes... Can you fix all of this now?"*
- **Root Cause:**
  1. `bot/telegram_agent.py` lacked an explicit idea-dump detection rule, causing Gemini to generate conversational essay replies even when Aaron explicitly asked to silently save notes for later.
  2. The image handler routed any uploaded image without a caption directly into the receipt OCR parsing routine instead of asking for context.
- **Current Status:** **Resolved**
  1. Established the explicit `Idea dump` trigger protocol: logs note to persistent storage and replies strictly with `Roger Roger.` + 1-line update summary.
  2. If an image is sent without text, the bot now responds `"I need more context."` while retaining the image in memory.

---

### Entry 4: Proactive File Edits Without Explicit Approval ("Go" / "Execute")
- **Date / Timestamp:** 2026-11-11 02:52:49 UTC
- **What Went Wrong & Aaron's Quote:**
  > *"New rule. I want you to ask me before ever making changes. Dont assume I want something. Unless I say go, or execute, ask me first."*
- **Root Cause:**
  An earlier rule (Rule 1c: "Autonomous Rule Evolution Protocol") gave the agent permission to autonomously modify rules and project files. This conflicted with Aaron's core requirement that changes must never be assumed or executed without explicit authorization ("go" or "execute").
- **Current Status:** **Resolved**
  Replaced Rule 1c with the **Mandatory Approval Rule** across `rules/MasterRules.md`, `memory/ProjectMemory.md`, and `.agents/rules/mandatory_approval.md`. All proposed changes are now held in Staging until explicit approval is given.

---

### Entry 5: Failure to Acknowledge Affirmations with "Roger Roger"
- **Date / Timestamp:** 2026-11-10 15:45:50 UTC
- **What Went Wrong & Aaron's Quote:**
  > Aaron instructed: *"For any rules where I asked you to just reply 'Okay', such as but not limited to the telegram idea dumps, change it to 'Roger Roger'. And whenever I do ask you to reply just ok or okay, actually respond with 'Roger Roger'."* -> Followed by: *"try again"*.
- **Root Cause:**
  The agent updated the backend bot code and rules but failed to immediately apply the conversational trigger to its own direct response back to Aaron in chat.
- **Current Status:** **Resolved**
  Pinned `.agents/rules/roger_roger.md` and Rule 2j in `rules/MasterRules.md` so all acknowledgments and confirmations consistently respond with `"Roger Roger."`.

---

### Entry 6: Receipt OCR Pipeline Crash on Initial Mobile Photo Upload
- **Date / Timestamp:** 2026-11-07 02:52:35 UTC
- **What Went Wrong & Aaron's Quote:**
  > *"Because I had an error today with my Telegram, I sent it a picture of a receipt and it gave me a failure, which I'll share with you once you're ready."*
- **Root Cause:**
  The receipt processor lacked robust error handling, JSON fallback cleaning, and graceful degradation when USDA FoodData Central lookups or image base64 conversions encountered unexpected mobile formats.
- **Current Status:** **Resolved**
  Added safe fallback parsing, timeout protection, and persistent override logging in `bot/telegram_agent.py`.

---

### Entry 7: IDE UI "Send All" Queue Loop
- **Date / Timestamp:** 2026-11-07 03:46:23 UTC
- **What Went Wrong & Aaron's Quote:**
  > *"also i keep having to click this send all button whenever i want to send a message. please fix that its annoying... im stuck in a send all loop rn"*
- **Root Cause:**
  VS Code / Antigravity input queue was capturing sequential user messages into an un-flushed batch queue instead of sending individual turns immediately.
- **Current Status:** **Resolved**

---

## 4. Redundant / Duplicate Files

| Item / Category | Files Involved | Nature of Redundancy / Sprawl | Recommended Action (Requires "Go") |
| :--- | :--- | :--- | :--- |
| **Requirements Files** | `requirements.txt` (root)<br>`bot/requirements.txt` | Both files only contain comments indicating standard library only (`# Uses Python standard library only`). `render.yaml` installs from root. | Consolidate to root `requirements.txt` and remove `bot/requirements.txt`. |
| **Agent Entry Point** | `telegram_agent.py` (root)<br>`bot/telegram_agent.py` | Root `telegram_agent.py` is a 4-line stub that simply imports and calls `bot/telegram_agent.py`. `render.yaml` points to root. | Keep root as the clean entry point, but ensure documentation clarifies it is an execution wrapper. |
| **Architectural Documentation** | `How it Works.md`<br>`TECHNICAL_BLUEPRINT.md` | Significant overlap between high-level project summary, Telegram webhook architecture, Render deployment steps, and cloud storage mechanics. | Merge unique blueprint sections into a single authoritative architecture document or establish clear separation (user guide vs. technical blueprint). |
| **Kitchen Inventory Databases** | `inventory/FoodInventory.md`<br>`inventory/InventoryData.json` | `FoodInventory.md` is human-readable markdown with food names; `InventoryData.json` is the exact macro database. Any new food must be kept in sync across both. | Retain both (one for human reading, one for exact math), but document single sync pipeline. |
| **Rules Duplication** | `rules/MasterRules.md`<br>`.agents/rules/*.md` | Rules like Strict Project Isolation, Mandatory Approval, and Roger Roger are mirrored in both locations (IDE agent rules vs. Telegram system prompt). | Intentional dual-layer architecture: IDE coding agent reads `.agents/rules/`, while Telegram bot injects `MasterRules.md`. Maintain sync. |
| **Multi-Project Vault Files** | `bot/lifting_vault.json`<br>`bot/sleep_vault.json`<br>`bot/wabbits_vault.json` | Encrypted data vaults from other projects stored inside `diet-macro-assistant/bot` to support multi-bot hosting on a single Render instance. | Keep isolated in `bot/` without permitting IDE agent to inspect or reference non-diet project logic. |
