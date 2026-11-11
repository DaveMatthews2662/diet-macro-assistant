# Project Memory: Diet & Macro Assistant

This document tracks all long-term project context, governance rules, action commands, future ideas (Backlog), and pending implementations (Staging) for diet-macro-assistant.

---

## 1. Operating Rules & Governance

### Two-Beat Confirmation Rule
- Never modify files, code, configs, or system settings during a diagnosis or explanation.
- Always stage proposed changes in Staging, explain what will be done, and ask: "Ready to execute?".
- Only execute when Aaron explicitly replies "go", "execute", or "3".

### Heavy Lifting
- Once approved, execute all changes, configuration updates, and deployments directly without asking Aaron to do manual work.

### Continuous Error Logging
- Whenever Aaron corrects the agent or flags an issue, append it immediately to memory/ErrorLog.md before replying.

### No Asterisk Clutter
- Avoid all asterisk markdown (* or **) in chat responses. Use clean dashes (-), numbers, and plain headers.

---

## 2. Numbered Action Command System

Typing the number (1-7) or trigger phrase runs the action:

- [1] pull backlog (or 1):
  Displays current exploratory ideas and Telegram dumps from memory/ProjectMemory.md.

- [2] pull staging (or 2):
  Displays concrete pending changes that are planned, designed, and strictly paused waiting for approval.

- [3] execute staging (or 3):
  The official green light. Applies all staged changes across files and configs.

- [4] sync all (or 4):
  Multi-level full sync across local files, GitHub, Telegram cloud, and Render.

- [5] pull error log (or 5):
  Displays the top recurring mistakes and guardrails from memory/ErrorLog.md.

- [6] status (or 6):
  Quick 3-bullet summary of project health, active files, and last sync timestamp.

- [7] list actions (or 7):
  Displays this numbered menu anytime.

---

## 3. Tracking Lists

### Staging (Concrete & Ready to Implement — Paused for Approval)
> Pending changes that are planned, designed, and ready to implement, but strictly paused waiting for Aaron's explicit "go", "execute", or "3".

- Status: Currently Clean / Empty. No pending staged changes waiting for execution.

---

### Backlog (Exploratory / Ideas & Brainstorms)
> Future ideas, feature brainstorms, and Telegram mobile idea dumps. Items here are exploratory and not scheduled for immediate work.

- Status: Currently Clean / Empty. All previous mobile idea dumps (shorthand 0 check, Idea Dump format, Roger Roger protocol) have been fully integrated.

---

## 4. Architecture & File Structure

Definitive project file map for external AI review:

- rules/MasterRules.md:
  Authoritative rules for diet assistant, macro math, portion units, and Telegram prompts.

- memory/ProjectMemory.md:
  Governance, Action Command System, Backlog, and Staging lists.

- memory/ErrorLog.md:
  Permanent historical mistake registry and redundancy inventory.

- inventory/FoodInventory.md:
  Human-readable kitchen inventory categorized by meal and protein type.

- inventory/InventoryData.json:
  Verified USDA and brand macro database with exact grams and decimal macros.

- inventory/persistent_overrides.json:
  Local cache of dynamic additions, removals, likes, dislikes, and mobile notes.

- bot/telegram_agent.py:
  Core Python implementation of the 24/7 Telegram assistant, vision OCR, Cronometer reading, and multi-bot webhook dispatcher.

- bot/render.yaml:
  Infrastructure-as-code specification for Render free web service deployment.

- telegram_agent.py (root):
  Minimal entry point wrapper used by Render startCommand.

- archive/:
  Houses superseded documents and dead files (How it Works.md, bot/requirements.txt).
