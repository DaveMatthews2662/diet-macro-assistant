# Master Rules (Must Review Before Any Work or Answer)

Before performing any task, writing any code, or returning any answer, I **must** review and follow every rule in this file.

> **Definition:** Throughout this file, **"Food"** means individual foods, snacks, ingredients, meals, and recipes.

---

## 1. Pre-Work Mandate
- **1a.** Before performing any task, writing any code, or returning any answer, I must read **[MasterRules.md](MasterRules.md)** and **fully review [FoodInventory.md](FoodInventory.md)** (along with **[InventoryData.json](InventoryData.json)**) from top to bottom every single time.

---

## 2. Communication Style
- **2a.** Explain everything simply and directly. Zero corporate jargon or filler.
- **2b.** Get straight to the point.
- **2c.** If anything about a request is unclear, ask a quick clarifying question before building the wrong thing.

---

## 3. Daily Macro Goals
- **Calories:** `1,900 kcal` target for the day's planned food, leaving a `200 kcal` buffer for a midnight snack if needed (`2,100 kcal` max).
- **Protein:** `180g`
- **Carbs:** `180g` minimum (prefer `190g`)
- **Fats:** `50g` minimum (prefer `55g–60g`)
- **Fiber:** `38g`

---

## 4. Project Scope & Core Purpose
- **4a. Not a Macro Tracker:** We are **not** building a daily food logger or macro tracker. Daily tracking is done in **Cronometer**.
- **4b. Maximize Kitchen Variety & Rotation (Top Priority):** The #1 purpose of this project is to help pick food using the **full variety** of **[FoodInventory.md](FoodInventory.md)** and actively **rotate** options so the same meals aren't suggested over and over.
- **4c. Prioritize Inventory + Flag Needed Grocery Items:**
  - Base suggestions primarily on **[FoodInventory.md](FoodInventory.md)** and your **Liked Foods** in Section 8.
  - Because you go to the grocery store a few times a week, you can also suggest meals that need a missing ingredient (e.g., sweet potatoes, potatoes, or a quick grocery pickup)—just flag it clearly with a note like **`[🛒 Need to buy: item]`**.
- **4d. Unlimited Pantry vs. Tracked Raw Meat:**
  - **Regular Inventory = Unlimited:** Treat every regular item in **[FoodInventory.md](FoodInventory.md)** as unlimited/always in stock.
  - **Raw Meat = Finite & Tracked:** Only suggest fresh/raw meat that you explicitly have on hand, and track the remaining weight/count as you use it.
  - **Current Raw Meat on Hand:**
    - **In Fridge (Ready to Cook):**
      - `1 steak` (~14 oz / ~0.88 lb) — **Kirkland Signature USDA Prime Top Sirloin Steak (Boneless, Cap-Off)** *(the other 3 steaks from the 3.54 lb pack are in the freezer)*
      - `1.09 lbs` — **93/7 Lean Ground Beef**
      - `1.085 lbs` — **Boneless Skinless Chicken Thighs**
- **4e. Dead-Simple Prep:** Keep all recipes and preparation instructions as simple as possible.
- **4f. 100% Macro Coverage (USDA & Brand Databases):**
  - Every single item in **[FoodInventory.md](FoodInventory.md)** must have its verified USDA FoodData Central or exact brand nutrition data (`serving_size`, `calories`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`) stored in **[InventoryData.json](InventoryData.json)** at all times.
  - Whenever any new food is added to the inventory, its macros must be looked up from USDA / brand nutrition databases and saved into **[InventoryData.json](InventoryData.json)** immediately so no item ever has missing macros.
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
- **Mode 2 — Fill In Remaining Day (Cronometer Screenshot):** The user sends a Cronometer screenshot showing Calories, Protein, Carbs, Fats, and Fiber eaten so far, and the agent suggests food to fill in the remaining slots for the day.

---

## 6. Two-Step Food Selection Workflow
- **6a. Step 1 — 5 Options Per Slot (Names Only):** When planning a day or picking for a slot, give **5 distinct options per category/slot** (unless asked for more) by name/idea only (e.g., *Chicken Tacos*, *Chicken Teriyaki*, *Bagel*, *Avocado Toast*) **without** grams, cups, or macros cluttering the list.
- **6b. Step 2 — Exact Amounts & Macros Once Picked:** After the user picks their option(s), provide the exact numbers scaled to fit their day:
  - **Portion Size** (`Grams` / `Cups` / `Units`)
  - **Calories**
  - **Protein**
  - **Carbs**
  - **Fats**
  - **Fiber**

---

## 7. Interface (Telegram Agent for Phone + PC)
- **7a. Single Simple Interface (Telegram Only):** No extra web dashboard to maintain. You interact with your food-planning agent directly through **Telegram** (which works on both your phone on the go and your PC via the Telegram Desktop/Web app).
- **7b. Interactive Meal Picking & Cronometer Screenshots:**
  - Send a message to plan a full day from scratch, or send a **Cronometer screenshot** to fill in the rest of your day.
  - The Telegram agent shows **5 rotating options per meal slot** (as clickable buttons/names first, with zero macro clutter).
  - Once you tap/pick your choices, the agent replies with the exact **Grams/Cups, Calories, Protein, Carbs, Fats, and Fiber**.
- **7c. Inventory, Receipt OCR & Preference Commands via Telegram:**
  - **Manage Likes & Dislikes:** Text *"add [food] to like list"* or *"add [food] to don't like list"* to update Section 8 automatically.
  - **View Likes & Dislikes:** Text *"can I see my like and dislike list"* to view all current favorites and dislikes.
  - **View Kitchen Inventory:** Text *"can I see my inventory"* (or a category/raw meat check) to see what is in **[FoodInventory.md](FoodInventory.md)**.
  - **Receipt Screenshot to Inventory:** Send a **screenshot or photo of a grocery receipt** (or text *"add [item] to inventory"* / *"remove [item] from inventory"*) and the agent extracts the items, adds them to **[FoodInventory.md](FoodInventory.md)**, and saves their USDA/brand macros into **[InventoryData.json](InventoryData.json)**.

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
