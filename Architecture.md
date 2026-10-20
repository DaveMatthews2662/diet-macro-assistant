# Component Specifications

## 1. Interaction Layer (Telegram + n8n)
- Feature A (Interactive Meal Picker): Telegram `/plan` command triggers n8n workflow. The AI evaluates FoodInventory.md and returns interactive Telegram inline keyboard buttons displaying 4–5 distinct options per slot. Selecting an option locks it in and triggers dynamic balancing for the rest of the day.
- Feature D (Receipt-to-Pantry OCR): Users upload a grocery receipt photo or paste item text in Telegram. n8n passes the image to Gemini Vision to extract line items and automatically append or update FoodInventory.md.

## 2. Core Engine & Rule Layer (VS Code & Antigravity)
- GEMINI.md: Master rules, simple recipe directive, equal-weight macro calculations, and meal slot allocation.
- MacroTargets.md: Calorie boundaries, midnight buffer logic, and whole vs. gummy fiber limits.
- FoodInventory.md: Current categorized pantry inventory.
- WorkoutPlan.md: 4-day rolling split for pre-workout and post-workout meal coordination.

## 3. Data & Analytics Layer (Streamlit Dashboard)
- Feature C (Analyst Dashboard): Local Streamlit web app consuming "DailyLogs.json".
- Visualizations:
  - Real-time macro adherence gauges (Calories, Protein, Fat, Carbs, Fiber).
  - Fiber source breakdown (whole food vs. gummy supplement tracker).
  - Workout Split vs. Macro Intake correlation (Push vs. Pull vs. Legs vs. Rest).
  - Pantry item utilization tracking.

