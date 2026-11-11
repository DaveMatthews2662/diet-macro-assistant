# Workspace Rules: Diet & Macro Assistant

## 1. Core Operating Protocols

### Two-Beat Confirmation Rule
- Never modify files, code, configs, or system settings during a diagnosis, explanation, or review.
- Always stage proposed changes in Staging (in memory/ProjectMemory.md), explain what will be done, and ask: "Ready to execute?".
- Only execute when Aaron explicitly replies "go", "execute", or "3".

### Heavy Lifting
- Once approved with "go", "execute", or "3", handle all edits, configs, script executions, and cloud syncs directly on Aaron's behalf.
- Never ask Aaron to manually run commands or edit files.

### Continuous Error Logging
- Whenever Aaron corrects you, points out a mistake, or flags a forgotten rule, automatically append it to memory/ErrorLog.md before replying.
- Never let an error go unrecorded.

### No Asterisk Clutter
- Never use asterisks (* or **) for bolding or bullet points in chat responses.
- Use clean dashes (-), numbers (1, 2, 3), and plain text headers.
- Always format all lists and questions with explicit double line breaks so they never collapse into walls of text in the chat UI.

### Strict Project Isolation
- This chat, agent, and workspace MUST ALWAYS stick strictly and exclusively to diet-macro-assistant (c:\Users\aaron\OneDrive\Desktop\My Projects\diet-macro-assistant).
- Never inspect, query, read, edit, execute commands for, or reference any other project on Aaron's computer unless Aaron explicitly names it in the prompt.
- The 0 shorthand command in this chat ONLY checks Telegram cloud notes for diet-macro-assistant.

---

## 2. Numbered Action Command System

Typing the number (1-7) or the exact phrase triggers the action immediately:

- [1] pull backlog (or 1):
  Displays current exploratory ideas and Telegram dumps from memory/ProjectMemory.md.

- [2] pull staging (or 2):
  Displays concrete pending changes that are planned, designed, and strictly paused waiting for approval.

- [3] execute staging (or 3):
  The official green light. Applies all staged changes across files and configs.

- [4] sync all (or 4):
  Multi-level full sync. Ensures all layers are updated: local files <-> cloud bot/Render <-> Telegram cloud <-> GitHub.

- [5] pull error log (or 5):
  Displays the top recurring mistakes and guardrails from memory/ErrorLog.md.

- [6] status (or 6):
  Quick 3-bullet summary of project health, active files, and last sync timestamp.

- [7] list actions (or 7):
  Displays this numbered menu anytime.
