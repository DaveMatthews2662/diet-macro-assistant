# Master Rules (Must Review Before Any Work or Answer)

Before performing any task, writing any code, or returning any answer, I **must** review and follow every rule in this file.

> **Definition:** Throughout this file, **"Food"** means individual foods, snacks, ingredients, meals, and recipes.

---

## 1. Pre-Work Mandate & Folder Structure
- **1a.** Before performing any task, writing any code, or returning any answer, I must read **[MasterRules.md](MasterRules.md)** and **fully review [FoodInventory.md](../inventory/FoodInventory.md)** (along with **[InventoryData.json](../inventory/InventoryData.json)**) from top to bottom every single time.
- **1b. Categorized Project Folders:**
  - `rules/` — **[MasterRules.md](MasterRules.md)** (all project rules, macro targets, and liked/disliked foods)
  - `inventory/` — **[FoodInventory.md](../inventory/FoodInventory.md)** (human-readable kitchen inventory) and **[InventoryData.json](../inventory/InventoryData.json)** (verified USDA/brand macro database)
  - `bot/` — **[telegram_agent.py](../bot/telegram_agent.py)**, **[meal_catalog.py](../bot/meal_catalog.py)**, **[render.yaml](../bot/render.yaml)**, **[requirements.txt](../bot/requirements.txt)**, and local gitignored key files (`.telegram_token`, `.gemini_key`)

---

## 2. Communication Style (Ultra-Short, Zero Fluff)
- **2a. Short as Humanly Possible:** Every response must be as short and direct as humanly possible.
- **2b. Zero Fluff / Commentary:** Never include intro pleasantries (*"That sounds like a great combo!"*), food descriptions (*"keeps it juicy and melts nicely"*), or outro filler (*"Fits right into your remaining budget!"*). Output **only** the requested names, ingredient amounts, and total numbers.
- **2c. Whole Numbers Only (No Decimals):** Round all calories and macros (`Protein`, `Carbs`, `Fats`) to the nearest **whole integer** (e.g., `40g P`, never `39.7g P`).
- **2d. Never Output Fiber:** Do **not** include Fiber in any macro breakdown, meal summary, or response. Aaron tracks fiber separately.
- **2e.** If anything about a request is unclear, ask a quick 1-line clarifying question.

---

## 3. Daily Macro Goals
- **Calories:** `1,900 kcal` target for the day's planned food, leaving a `200 kcal` buffer for a midnight snack if needed (`2,100 kcal` max).
- **Protein:** `180g`
- **Carbs:** `180g` minimum (prefer `190g`)
- **Fats:** `50g` minimum (prefer `55g–60g`)
*(Fiber is tracked separately by Aaron—do not output or track fiber.)*

---

## 4. Project Scope & Core Purpose
- **4a. Not a Macro Tracker:** We are **not** building a daily food logger or macro tracker. Daily tracking is done in **Cronometer**.
- **4b. Maximize Kitchen Variety & Rotation (Top Priority):** The #1 purpose of this project is to help pick food using the **full variety** of **[FoodInventory.md](../inventory/FoodInventory.md)** and actively **rotate** options so the same meals aren't suggested over and over.
- **4c. Prioritize Inventory + Flag Needed Grocery Items:**
  - Base suggestions primarily on **[FoodInventory.md](../inventory/FoodInventory.md)** and your **Liked Foods** in Section 8.
  - Because you go to the grocery store a few times a week, you can also suggest meals that need a missing ingredient (e.g., sweet potatoes, potatoes, or a quick grocery pickup)—just flag it clearly with **`[🛒 Need to buy: item]`**.
- **4d. Unlimited Pantry vs. Tracked Raw Meat:**
  - **Regular Inventory = Unlimited:** Treat every regular item in **[FoodInventory.md](../inventory/FoodInventory.md)** as unlimited/always in stock.
  - **Raw Meat = Finite & Tracked (Only Adjust When Explicitly Told):** Only suggest fresh/raw meat that you explicitly have on hand. **Never** automatically deduct or adjust raw meat or inventory unless Aaron explicitly tells you to.
  - **Current Raw Meat on Hand:**
    - **In Fridge (Ready to Cook):**
      - `1 steak` (~14 oz / ~0.88 lb) — **Kirkland Signature USDA Prime Top Sirloin Steak (Boneless, Cap-Off)** *(the other 3 steaks from the 3.54 lb pack are in the freezer)*
      - `1.09 lbs` — **93/7 Lean Ground Beef**
      - `1.085 lbs` — **Boneless Skinless Chicken Thighs**
- **4e. Dead-Simple Prep:** Keep all recipes and preparation instructions as simple as possible.
- **4f. 100% Macro Coverage (USDA & Brand Databases):**
  - Every single item in **[FoodInventory.md](../inventory/FoodInventory.md)** must have its verified USDA FoodData Central or exact brand nutrition data (`serving_size`, `calories`, `protein_g`, `carbs_g`, `fat_g`) stored in **[InventoryData.json](../inventory/InventoryData.json)** at all times.
- **4g. Likes & Dislikes Tracking:** Always maintain and respect the user's list of **Liked / Go-To Foods & Meals** and **Disliked Foods (Never Suggest)** in Section 8 below.

---

## 5. Meal Slots & Planning Modes
### 5a. The 5 Meal Slots (In Order)
1. **Pre-Workout** *(skip/ignore on Rest Days)*
2. **Breakfast**
3. **Lunch**
4. **Dinner**
5. **Snacks**

### 5b. Two Ways to Plan
- **Mode 1 — Full Day from Scratch (No Screenshot):** Plan the whole day across the meal slots to hit the daily macro goals in Section 3.
- **Mode 2 — Fill In Remaining Day (Cronometer Screenshot):** The user sends a Cronometer screenshot showing Calories, Protein, Carbs, and Fats eaten so far, and the agent suggests food to fill in the remaining slots for the day.

---

## 6. Two-Step Food Selection Workflow & Formatting Rules
- **6a. Step 1 — 5 Options Per Slot (Names Only):** When planning a day or picking for a slot, give **5 distinct options per category/slot** (unless asked for more) by name/idea only (e.g., *Chicken Tacos*, *Chicken Teriyaki*, *Bagel*, *Avocado Toast*) **without** grams, cups, or macros cluttering the list.
- **6b. Step 2 — Ingredient Amounts First, Total Macros Only at the Bottom:**
  - When showing numbers for a meal (or once an option is picked), **never** list macros next to each individual ingredient.
  - List **only the portion size (`Grams` / `Cups` / `Units`) of each ingredient**, followed by **one single Total Macros line** at the bottom with **whole numbers only** and **no fiber**:
    ```text
    [Meal Name]
    - [Amount] [Ingredient 1]
    - [Amount] [Ingredient 2]

    Total: [X] kcal | [X]g P | [X]g C | [X]g F
    ```
- **6c. Direct Question / Follow-Up Context Override (Never Dump Random 5-Meal Lists):**
  - **Only** output a 5-option meal list when Aaron explicitly asks for meal/snack ideas or to plan a meal slot/day.
  - If Aaron is asking a specific question, doing meal math, or replying with a follow-up (e.g., asking how to season a pasta/beef bowl and following up with *"I was thinking taco"*), stay focused on that exact dish and conversation context.
- **6d. Strict Remaining-Calorie & Macro Guardrail + DIY Spice Blends:**
  - Every suggestion **must** fit the calories and macros Aaron actually has left for the day (e.g., never suggest tortillas or heavy extras when calories are tight or when he already has a carb base like chickpea pasta).
  - Before flagging `[🛒 Need to buy: seasoning]`, check `# Spices & Seasonings` and `# Oils & Condiments` in **[FoodInventory.md](../inventory/FoodInventory.md)** to build the flavor from spices already on hand (e.g., homemade taco seasoning from Cumin, Paprika, Garlic Powder, Onion Powder, Salt, Black Pepper, Red Pepper Flakes, Lime Juice, Cilantro, or Green Chile Enchilada Sauce).

---

## 7. Interface & 24/7 Cloud Hosting (Telegram Agent)
- **7a. Single Simple Interface (Telegram Only):** No extra web dashboard to maintain. You interact with your food-planning agent directly through **Telegram** (on both your phone and your PC).
- **7b. Clean Conversational Text (Zero Button Spam):**
  - Do **not** spam clunky Telegram inline button menus when a screenshot or message is sent.
  - Reply in ultra-short, plain text powered by Gemini (`gemini-3.5-flash` with `gemini-3-flash-preview` and `gemini-3.5-flash-lite` fallbacks) with full access to **[MasterRules.md](MasterRules.md)**, **[FoodInventory.md](../inventory/FoodInventory.md)**, and **[InventoryData.json](../inventory/InventoryData.json)**.
- **7c. Inventory, Receipt OCR & Preference Commands via Telegram:**
  - **Manage Likes & Dislikes:** Text *"add [food] to like list"* or *"add [food] to don't like list"* to update Section 8 automatically.
  - **View Likes & Dislikes:** Text *"can I see my like and dislike list"* to view all current favorites and dislikes.
  - **View Kitchen Inventory:** Text *"can I see my inventory"* (or a category/raw meat check) to see what is in **[FoodInventory.md](../inventory/FoodInventory.md)**.
  - **Receipt Screenshot to Inventory:** Send a **screenshot or photo of a grocery receipt** (or text *"add [item] to inventory"* / *"remove [item] from inventory"*) and the agent extracts the items, adds them to **[FoodInventory.md](../inventory/FoodInventory.md)**, and saves their USDA/brand macros into **[InventoryData.json](../inventory/InventoryData.json)**.
- **7d. 24/7 Cloud Hosting (Works When PC Is Off):**
  - The Telegram bot runs 24/7 on **Render.com** (connected to GitHub `DaveMatthews2662/diet-macro-assistant`) so it works anytime from your phone even when your computer is turned off.
  - **Single Polling Rule:** Keep local `telegram_agent.py` stopped while Render is active so two instances never fight over the same Telegram bot token.

---

## 8. Food Preferences (Likes & Dislikes)
### 👍 Foods & Meals I Like (Favorites / Go-Tos)
- Avocado on Sourdough Toast
- PBfit Peanut Butter (mixed with water) on Sourdough Toast
- Chicken Teriyaki
- Soy-flavored dishes (anything with soy sauce / teriyaki / savory Asian-style seasoning)
- Greek Yogurt and Granola
- Milk (`Fairlife Fat-Free Ultra-Filtered Milk`)
- Cereal (`Kashi GO Protein + Fiber Cereal`, `Cheerios Protein`)
- Peanut Butter and Jelly Sandwiches (including with PBfit or Creamy Peanut Butter)
- white rice
- sweet potatoes
- potatoes

### 👎 Foods I Don't Like (Never Suggest)
- **Frank's RedHot / Buffalo Sauce** *(verified removed from inventory)*
