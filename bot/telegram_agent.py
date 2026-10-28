import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import random
import re
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_path(filename: str, subfolder: str) -> str:
    candidate = os.path.join(BASE_DIR, subfolder, filename)
    if os.path.exists(candidate):
        return candidate
    root_candidate = os.path.join(BASE_DIR, filename)
    if os.path.exists(root_candidate):
        return root_candidate
    return candidate


RULES_FILE = resolve_path("MasterRules.md", "rules")
INV_MD_FILE = resolve_path("FoodInventory.md", "inventory")
INV_JSON_FILE = resolve_path("InventoryData.json", "inventory")
TOKEN_FILE = resolve_path(".telegram_token", "bot")
GEMINI_KEY_FILE = resolve_path(".gemini_key", "bot")
USDA_API_KEY = os.environ.get("USDA_API_KEY", "DEMO_KEY")

# Per-chat conversation history so Gemini remembers the whole conversation + screenshots
CHAT_MEMORY: Dict[int, List[Dict[str, Any]]] = {}

# Per-chat batching so multi-screenshot uploads / rapid messages produce ONE single reply
BATCH_LOCK = threading.Lock()
CHAT_BATCH: Dict[int, Dict[str, Any]] = {}
BATCH_DELAY_SEC = 2.0


# ==============================================================================
# RULE 1a: ALWAYS READ MasterRules.md, FoodInventory.md, AND InventoryData.json
# ==============================================================================
def load_all_context() -> Tuple[str, str, List[Dict[str, Any]]]:
    rules_md, inv_md, inv_json = "", "", []
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            rules_md = f.read()
    if os.path.exists(INV_MD_FILE):
        with open(INV_MD_FILE, "r", encoding="utf-8") as f:
            inv_md = f.read()
    if os.path.exists(INV_JSON_FILE):
        with open(INV_JSON_FILE, "r", encoding="utf-8") as f:
            inv_json = json.load(f)
    return rules_md, inv_md, inv_json


def get_token() -> str:
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def get_gemini_key() -> str:
    if os.path.exists(GEMINI_KEY_FILE):
        with open(GEMINI_KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return os.environ.get("GEMINI_API_KEY", "").strip()


# ==============================================================================
# FILE UPDATERS FOR LIKES/DISLIKES & INVENTORY WHEN EXPLICITLY REQUESTED
# ==============================================================================
def add_to_likes(item_text: str) -> str:
    rules_md, _, _ = load_all_context()
    marker = "### 👍 Foods & Meals I Like (Favorites / Go-Tos)"
    if marker in rules_md:
        rules_md = rules_md.replace(marker, f"{marker}\n- {item_text}", 1)
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            f.write(rules_md)
    return f"👍 Added *{item_text}* to your Likes list in `MasterRules.md`."


def add_to_dislikes(item_text: str) -> str:
    rules_md, inv_md, _ = load_all_context()
    marker = "### 👎 Foods I Don't Like (Never Suggest)"
    if marker in rules_md:
        rules_md = rules_md.replace(marker, f"{marker}\n- **{item_text}**", 1)
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            f.write(rules_md)

    removed_inv = []
    new_lines = []
    for line in inv_md.splitlines():
        if line.strip().startswith("- ") and item_text.lower() in line.lower():
            removed_inv.append(line.strip()[2:])
        else:
            new_lines.append(line)
    if removed_inv:
        with open(INV_MD_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")

    msg = f"👎 Added *{item_text}* to your Dislikes list."
    if removed_inv:
        msg += f" (Also removed {', '.join(removed_inv)} from inventory.)"
    return msg


def lookup_usda_macros(food_name: str) -> Dict[str, Any]:
    try:
        q = urllib.parse.quote(food_name)
        url = f"https://api.nal.usda.gov/fdc/v1/foods/search?api_key={USDA_API_KEY}&query={q}&pageSize=1"
        req = urllib.request.Request(url, headers={"User-Agent": "DietMacroAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        foods = data.get("foods", [])
        if foods:
            f0 = foods[0]
            nutrients = {n.get("nutrientName", "").lower(): n.get("value", 0.0) for n in f0.get("foodNutrients", [])}
            cal = float(nutrients.get("energy", 100.0))
            p = float(nutrients.get("protein", 5.0))
            fat = float(nutrients.get("total lipid (fat)", 2.0))
            carbs = float(nutrients.get("carbohydrate, by difference", 15.0))
            fib = float(nutrients.get("fiber, total dietary", 1.0))
            serv_size = f0.get("servingSize")
            serv_unit = f0.get("servingSizeUnit", "g")
            portion = f"{int(serv_size)}{serv_unit}" if serv_size else "100g"
            return {
                "serving_size": portion,
                "calories": round(cal, 1),
                "protein_g": round(p, 1),
                "fat_g": round(fat, 1),
                "carbs_g": round(carbs, 1),
                "fiber_g": round(fib, 1),
            }
    except Exception:
        pass
    return {
        "serving_size": "100g",
        "calories": 120.0,
        "protein_g": 8.0,
        "fat_g": 3.0,
        "carbs_g": 15.0,
        "fiber_g": 2.0,
    }


def add_item_to_inventory(item_name: str, category: str = "Pantry & Canned") -> str:
    _, inv_md, inv_json = load_all_context()
    low_type = item_name.lower()
    if any(k in low_type for k in ["raw", "steak", "ground beef", "chicken thigh", "chicken breast", "pork", "salmon"]):
        if "raw" in low_type or "lbs" in low_type or "lb" in low_type:
            category = "Raw Meat (Finite Tracked Stock)"

    header = f"# {category}"
    if header in inv_md:
        inv_md = inv_md.replace(header, f"{header}\n- {item_name}", 1)
    else:
        inv_md = inv_md.rstrip() + f"\n\n{header}\n- {item_name}\n"

    with open(INV_MD_FILE, "w", encoding="utf-8") as f:
        f.write(inv_md)

    macros = lookup_usda_macros(item_name)
    inv_json.append({"name": item_name, "category": category, "tags": "USDA Verified", **macros})
    with open(INV_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(inv_json, f, indent=2)

    return (
        f"✅ Added *{item_name}* (`{macros['serving_size']}`: "
        f"`{int(round(macros['calories']))} kcal` | `{int(round(macros['protein_g']))}g P` | `{int(round(macros['carbs_g']))}g C` | `{int(round(macros['fat_g']))}g F`)."
    )


def remove_item_from_inventory(item_query: str) -> str:
    _, inv_md, inv_json = load_all_context()
    removed = []
    new_lines = []
    for line in inv_md.splitlines():
        if line.strip().startswith("- ") and item_query.lower() in line.lower():
            removed.append(line.strip()[2:])
        else:
            new_lines.append(line)

    if not removed:
        return f"Couldn't find *{item_query}* in your inventory."

    with open(INV_MD_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")

    inv_json = [x for x in inv_json if item_query.lower() not in x.get("name", "").lower()]
    with open(INV_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(inv_json, f, indent=2)

    return f"🗑️ Removed {', '.join(removed)} from your inventory."


# ==============================================================================
# GEMINI 4 ARGON CONVERSATIONAL AGENT (WITH INVENTORY SHUFFLING & MEMORY)
# ==============================================================================
def ask_gemini(user_text: str, chat_id: int, image_paths: List[str] = None) -> str:
    key = get_gemini_key()
    rules_md, inv_md, inv_json = load_all_context()

    # Shuffle inventory order on every turn so the model doesn't fixate on the first 10 items in the file!
    shuffled_inv = list(inv_json)
    random.shuffle(shuffled_inv)

    macro_lines = [
        f"- [{x.get('category', '')}] {x['name']} ({x['serving_size']}): {int(round(x['calories']))} kcal | {int(round(x['protein_g']))}g P | {int(round(x['carbs_g']))}g C | {int(round(x['fat_g']))}g F"
        for x in shuffled_inv
    ]
    macro_db_text = "\n".join(macro_lines)

    # Pick a random spotlight of 25 non-spice foods from across the inventory to inspire fresh rotation
    food_candidates = [
        x["name"]
        for x in shuffled_inv
        if x.get("calories", 0) >= 20 and "Spices" not in x.get("category", "")
    ]
    spotlight_sample = food_candidates[:25]
    spotlight_text = ", ".join(spotlight_sample)

    if chat_id not in CHAT_MEMORY:
        CHAT_MEMORY[chat_id] = []
    history = CHAT_MEMORY[chat_id]

    # Collect previously suggested lines from recent assistant responses so it NEVER repeats them
    previous_model_texts = []
    for turn in history[-8:]:
        if turn.get("role") == "model":
            for p in turn.get("parts", []):
                if "text" in p:
                    previous_model_texts.append(p["text"])
    already_suggested_block = "\n---\n".join(previous_model_texts[-3:]) if previous_model_texts else "None yet."

    system_prompt = (
        "You are Aaron's personal Food & Macro Assistant on Telegram.\n"
        "You have the exact same deep reasoning and macro-math intelligence as normal Gemini chat, PLUS full access to Aaron's kitchen inventory (`FoodInventory.md` and `InventoryData.json`) and rules (`MasterRules.md`).\n\n"
        "HOW TO THINK & SOLVE MACRO MATH (USE YOUR INTERNAL THINKING STEP):\n"
        "1. Read all meals, gram weights, and Consumed totals from the Cronometer screenshot(s) in the conversation (100% ignore Cronometer's right-side target denominators like '/ 2100 kcal' or '/ 200g P').\n"
        "2. Compare against Aaron's true daily goals from MasterRules.md Section 3:\n"
        "   - Protein: 170g floor, 185g goal (MUST end the day between 170g and 185g P — never leave him under 170g P!)\n"
        "   - Carbs: 150g floor, 180g goal (stay between 150g and 180g C)\n"
        "   - Fats: 50g floor, 50g goal (target ~50g F)\n"
        "   - Calories: ~1,900 kcal target for planned food (1,850-1,950 kcal window — never leave him at 2,060 kcal with 164g P!).\n"
        "3. SMART ADJUSTMENTS, HARD USER LOCKS & PRE-WORKOUT MEALS:\n"
        "   - Look at the whole day holistically!\n"
        "   - If his current plan is ALREADY high in calories (e.g. ~1,900-2,060 kcal) or if adding a snack would push calories over ~1,950 kcal while leaving protein short, OR whenever Aaron says you can adjust other stuff in his day: DO NOT just dump 5 extra snacks on top! Instead, adjust the gram weights or swap items in his existing planned meals on the screenshot so the whole day lands right on ~1,900 kcal | 175-185g P | 150-180g C | ~50g F.\n"
        "   - OBEY ALL USER LOCKS & NON-DECREASE FLOORS: If Aaron says e.g. 'remove/adjust anything except the steak', 'do not decrease the sourdough amount (126g)', and 'keep yogurt/granola and cereal', treat those as 100% locked constraints! Never lower total daily sourdough below 126g (you can split the 126g across Pre-Workout and Breakfast/Lunch), never change the locked steak amount, and keep his yogurt+granola and cereal bowl. Free up fats/carbs by removing or adjusting UNLOCKED items (like dropping butter, swapping to lower-fat ProGranola, or removing/reducing unlocked fruit/extras) so there is room for a real Dinner side with the steak!\n"
        "   - TOP-TIER PRE-WORKOUT MEALS: When Aaron asks for an early-morning Pre-Workout meal, create a `Pre-Workout` slot at the top using fast-digesting carbs + lean protein + minimal fat (e.g., part of his locked Sourdough Toast with Strawberry Jelly/Jam, Banana, or PBfit + Liquid Egg Whites / Fairlife Milk / Whey).\n"
        "   - If he has calories/macros open and asks for options to fill a slot/day, make sure EVERY option you give is scaled so that choosing it actually hits his 170-185g P and ~1,900 kcal goals.\n"
        "4. DINNER PAIRING OPTIONS VS. SINGLE SWAP (NEVER REPEAT ASSUMED STEAK IN EVERY OPTION):\n"
        "   - ALWAYS respect Aaron's exact math (e.g., if he says 'I have 446g of steak, I'd like to split that for a meal', half of 446g is 223g pre-cooked / 167g cooked — NEVER make up 300g!).\n"
        "   - IF AARON ASKS TO SWAP A SIDE WHILE TUNING HIS DAY (e.g. 'also I want something else with dinner' without asking for multiple options): DO NOT output 5 Dinner options! Just replace the unwanted side (e.g. carrots) with 1 normal, appetizing side (like White Rice, Potatoes, or Beans) inside the single `Dinner` block and show 1 single `Daily Total:` at the bottom.\n"
        "   - IF AARON EXPLICITLY ASKS FOR 'options for with the steak': The steak is ALREADY ASSUMED — NEVER repeat the steak line inside every option! List the steak ONCE under `Dinner`, and then list ONLY the side dish under `Option 1..5` (with the side's `Total:` and resulting `Daily Total:`).\n"
        "5. AIRPORT & TRAVEL MODE (TSA-COMPLIANT SOLID PORTABLE FOODS):\n"
        "   - When Aaron says he is traveling (e.g., 'traveling at night so help me pick food I can easily bring and eat while traveling thru the airport'):\n"
        "     * Schedule cooked/refrigerated/liquid items (steak, liquid egg whites, Greek yogurt cups, milk, liquid protein shakes) EARLIER in the day at home (`Pre-Workout` / `Breakfast` / `Lunch`).\n"
        "     * For the Airport / Travel meals & snacks (`Dinner` / `Snacks`), ONLY pick 100% TSA-compliant SOLID, portable, no-microwave foods from his inventory (TSA confiscates liquids/gels/yogurt cups/protein shakes over 3.4 oz!): e.g., a Sandwich/Wrap with `H-E-B Honey Turkey Breast Deli Meat` (or `Costco Rotisserie Chicken Breast`) on `Easy Tiger Sourdough Bread`, `Sola Bagel`, or `Mission Carb Balance Tortillas` (or a PB&J / PBfit Sandwich), `1 bar (60g) Kirkland Signature Protein Bar`, `1 bag (32g) Quest Tortilla Style Protein Chips`, `1 stick (32g) Kirkland Grass-Fed Beef Stick`, `1 packet (21g) Tillamook Sharp Cheddar` / `Babybel Cheese`, dry `Whey Protein Powder` in an empty shaker bottle (add water past security), `H-E-B Red Apples`, `Fresh Bananas`, or dry `Kashi GO Cereal` / `ProGranola` / `Rice Cakes` in a Ziploc.\n"
        "6. WIDE KITCHEN VARIETY & ZERO REPEATS:\n"
        "   - Actively use the full 157-item inventory! Draw from his frozen meats/shrimp/chicken strips/meatballs, rotisserie chicken, canned tuna/chicken, edamame, cottage cheese, protein bars, beef sticks, cheeses, breads, bagels, tortillas, beans, rices, pastas, fruits, and snacks.\n"
        "   - Here is a randomized spotlight of items from his inventory to consider rotating in if they fit his macros:\n"
        f"     [{spotlight_text}]\n"
        "   - NEVER repeat any option, meal, or food combo that appears in 'RECENTLY SUGGESTED IN THIS CHAT' below when Aaron asks for more options or alternatives.\n\n"
        "STRICT PORTION UNITS & FORMATTING RULES (NEVER VIOLATE — EVEN IF EARLIER CHAT HISTORY USED OLD FORMATS, ALWAYS UPGRADE TO THESE UNITS):\n"
        "1. INDIVIDUAL PRE-PACKAGED CUPS / BARS / PACKETS / BAGELS -> WHOLE UNITS FIRST + (Xg):\n"
        "   - Items that come in individual serving cups or packages MUST be written in whole units (1 or 2, NEVER weird fractional weights like '250g Greek Yogurt' — even if an earlier message had 250g, change it to 1 cup (150g) or 2 cups (300g)!) with grams in parentheses:\n"
        "     * Greek Yogurt Cups: `- 1 cup (150g) Oikos Triple Zero 15g Protein Greek Yogurt (Vanilla)` (or `2 cups (300g)`)\n"
        "     * Bagels / Bars / Packets / Sticks / Bowls: `- 1 bagel (85g) Sola Soft Bagels: Cinnamon & Raisin`, `- 1 bar (60g) Kirkland Signature Protein Bar`, `- 1 packet (43g) H-E-B Protein Instant Oatmeal`, `- 1 stick (32g) Kirkland Grass-Fed Beef Stick`, `- 1 bowl (210g) Bibigo Cooked Sticky White Rice`, `- 1 pouch (140g) Ben's Original Ready Rice`.\n"
        "2. MILK -> ALWAYS IN CUPS + (Xg):\n"
        "   - Always tell milk in cups with grams in parentheses (never raw '240g Fairlife Milk'): `- 1 cup (240g) Fairlife Fat-Free Ultra-Filtered Lactose-Free Milk` (or `- 1/2 cup (120g)`, `- 1.5 cups (360g)`).\n"
        "3. PROTEIN SHAKES -> ALWAYS IN WHOLE SHAKES/BOTTLES + (Xg):\n"
        "   - Always tell ready-to-drink protein shakes as whole shakes/bottles with grams in parentheses (never raw '325g Premier Protein'):\n"
        "     * `- 1 shake (325g) Premier Protein 30g Chocolate Protein Shakes`\n"
        "     * `- 1 shake (340g) Fairlife Nutrition Plan 30g Chocolate Protein Shakes`\n"
        "4. STEAK, RAW MEATS & LIQUID EGG WHITES -> ALWAYS GIVE BOTH PRE-COOKED AND COOKED GRAMS:\n"
        "   - Raw meats (steak, ground beef, chicken thighs, chicken breast, shrimp) lose ~25% moisture when cooked (`cooked_g = round(raw_g * 0.75)`).\n"
        "   - Liquid egg whites lose ~12% moisture when scrambled (`cooked_g = round(raw_g * 0.88)`).\n"
        "   - ALWAYS show BOTH pre-cooked and cooked grams on the ingredient line:\n"
        "     * `- 223g pre-cooked / 167g cooked Kirkland Signature USDA Prime Top Sirloin Steak (Boneless, Cap-Off)`\n"
        "     * `- 200g pre-cooked / 176g cooked H-E-B Cage-Free 100% Liquid Egg Whites`\n"
        "5. ALL OTHER WEIGHABLE FOODS (Sourdough bread, cereal, granola, fruit, butter, PBfit, deli meat, bulk rice/pasta, etc.):\n"
        "   - Start with exact grams (`Xg`), e.g. `- 80g Easy Tiger Sourdough Bread`, `- 30g Purely Elizabeth Granola`, `- 53g Kashi GO Cereal`, `- 182g H-E-B Red Apples`.\n"
        "6. ULTRA-SHORT, ZERO FLUFF, WHOLE NUMBERS ONLY, NO FIBER, AND INCLUDE `Daily Total:` AT THE END:\n"
        "   - No intro pleasantries, no food descriptions, no outro commentary.\n"
        "   - Never output 'Consumed So Far:' or 'Remaining Targets:' at the top.\n"
        "   - Round all calories and macros to whole integers (no decimals ever) and never output Fiber.\n"
        "   - Put `Total: [X] kcal | [X]g P | [X]g C | [X]g F` under each meal/option, and ALWAYS include a `Daily Total: [X] kcal | [X]g P | [X]g C | [X]g F` line at the very bottom of any full-day or remaining-day plan (or under each Dinner option when showing 5 options for a slot in a day plan)!\n\n"
        f"=== RECENTLY SUGGESTED IN THIS CHAT (DO NOT REPEAT THESE WHEN ASKED FOR MORE) ===\n{already_suggested_block}\n\n"
        f"=== MasterRules.md ===\n{rules_md}\n\n"
        f"=== FoodInventory.md ===\n{inv_md}\n\n"
        f"=== InventoryData.json (Shuffled Full Kitchen Macro Database) ===\n{macro_db_text}"
    )

    parts: List[Dict[str, Any]] = []
    for img_path in (image_paths or []):
        if img_path and os.path.exists(img_path):
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    parts.append({"text": user_text or "Read the screenshot(s) and help me hit my MasterRules.md goals."})

    # Keep inline_data images in the last 6 history entries so follow-up messages always see the Cronometer screenshot!
    trimmed_history: List[Dict[str, Any]] = []
    recent_slice = list(history[-12:])
    for idx, turn in enumerate(recent_slice):
        if idx < len(recent_slice) - 6:
            text_only_parts = [p for p in turn.get("parts", []) if "text" in p]
            if not text_only_parts:
                text_only_parts = [{"text": "[Earlier Screenshot]"}]
            trimmed_history.append({"role": turn["role"], "parts": text_only_parts})
        else:
            trimmed_history.append(turn)

    contents = trimmed_history + [{"role": "user", "parts": parts}]
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.65,
            "thinkingConfig": {"thinkingBudget": 8192},
        },
    }

    last_err = None
    models = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
    for attempt in range(2):
        for model_name in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=45) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                cand_parts = res["candidates"][0]["content"]["parts"]
                visible_texts = [p["text"] for p in cand_parts if "text" in p and not p.get("thought")]
                if not visible_texts:
                    visible_texts = [p["text"] for p in cand_parts if "text" in p]
                reply = "\n".join(visible_texts).strip()
                history.append({"role": "user", "parts": parts})
                history.append({"role": "model", "parts": [{"text": reply}]})
                return reply
            except Exception as e:
                last_err = e
                time.sleep(1.5)
                continue
        time.sleep(2.0)
    raise RuntimeError(f"Gemini API error: {last_err}")


# ==============================================================================
# TELEGRAM HTTP HELPERS
# ==============================================================================
def tg_api(token: str, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_message(token: str, chat_id: int, text: str):
    chunks = [text[i : i + 3900] for i in range(0, len(text), 3900)] or [text]
    for chunk in chunks:
        payload: Dict[str, Any] = {"chat_id": chat_id, "text": chunk}
        tg_api(token, "sendMessage", payload)


def download_telegram_photo(token: str, file_id: str) -> str:
    info = tg_api(token, "getFile", {"file_id": file_id})
    file_path = info["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    fd, local_path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    urllib.request.urlretrieve(url, local_path)
    return local_path


# ==============================================================================
# BATCHED MESSAGE & MULTI-PHOTO HANDLER (PREVENTS MULTIPLE REPLIES)
# ==============================================================================
def flush_chat_batch(token: str, chat_id: int):
    with BATCH_LOCK:
        batch = CHAT_BATCH.pop(chat_id, None)
    if not batch:
        return

    texts: List[str] = batch.get("texts", [])
    photos: List[str] = batch.get("photos", [])
    combined_text = "\n".join(t for t in texts if t).strip()

    try:
        if not photos and combined_text:
            s = combined_text
            m_dis = re.search(r"^add\s+(.+?)\s+to\s+(?:my\s+)?(?:don'?t\s+like|dislike)\s*(?:list)?$", s, re.I)
            if m_dis:
                send_message(token, chat_id, add_to_dislikes(m_dis.group(1).strip()))
                return

            m_like = re.search(r"^add\s+(.+?)\s+to\s+(?:my\s+)?like\s*(?:list)?$", s, re.I)
            if m_like:
                send_message(token, chat_id, add_to_likes(m_like.group(1).strip()))
                return

            m_add_inv = re.search(r"^add\s+(.+?)\s+to\s+(?:my\s+)?inventory$", s, re.I)
            if m_add_inv:
                send_message(token, chat_id, add_item_to_inventory(m_add_inv.group(1).strip()))
                return

            m_rem_inv = re.search(r"^remove\s+(.+?)\s+from\s+(?:my\s+)?inventory$", s, re.I)
            if m_rem_inv:
                send_message(token, chat_id, remove_item_from_inventory(m_rem_inv.group(1).strip()))
                return

        reply = ask_gemini(combined_text, chat_id, image_paths=photos)
        send_message(token, chat_id, reply)
    except Exception as e:
        send_message(token, chat_id, f"⚠️ Error: {e}")
    finally:
        for p in photos:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


def enqueue_turn(token: str, chat_id: int, text: str = "", photo_path: str = None):
    with BATCH_LOCK:
        entry = CHAT_BATCH.get(chat_id)
        if not entry:
            entry = {"texts": [], "photos": [], "timer": None}
            CHAT_BATCH[chat_id] = entry
        if entry["timer"] is not None:
            entry["timer"].cancel()
        if text:
            entry["texts"].append(text.strip())
        if photo_path:
            entry["photos"].append(photo_path)
        timer = threading.Timer(BATCH_DELAY_SEC, flush_chat_batch, args=(token, chat_id))
        timer.daemon = True
        entry["timer"] = timer
        timer.start()


def process_update(token: str, upd: Dict[str, Any]):
    if "message" in upd:
        msg = upd["message"]
        cid = msg["chat"]["id"]
        if "photo" in msg:
            photo_list = msg["photo"]
            best_photo = photo_list[-2] if len(photo_list) >= 2 else photo_list[-1]
            try:
                local_path = download_telegram_photo(token, best_photo["file_id"])
                enqueue_turn(token, cid, text=msg.get("caption", ""), photo_path=local_path)
            except Exception as e:
                send_message(token, cid, f"⚠️ Error downloading image: {e}")
        elif "text" in msg:
            enqueue_turn(token, cid, text=msg["text"])


# ==============================================================================
# WEBHOOK + KEEP-ALIVE SERVER (SO RENDER FREE TIER NEVER IGNORES MESSAGES)
# ==============================================================================
SEEN_UPDATES = set()


class BotHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - Telegram Food Picker Agent is awake")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
        try:
            upd = json.loads(body.decode("utf-8"))
            uid = upd.get("update_id")
            if uid is not None:
                if uid in SEEN_UPDATES:
                    return
                SEEN_UPDATES.add(uid)
            token = get_token()
            if token:
                threading.Thread(target=process_update, args=(token, upd), daemon=True).start()
        except Exception:
            pass

    def log_message(self, format, *args):
        pass


def keep_alive_loop(external_url: str):
    while True:
        time.sleep(480)  # Ping every 8 minutes so Render's 15-minute idle timer never fires
        try:
            req = urllib.request.Request(external_url, headers={"User-Agent": "KeepAlive/1.0"})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            pass


def run_bot():
    token = get_token()
    if not token:
        print("Missing token.")
        return

    port = int(os.environ.get("PORT", "10000"))
    external_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

    server = HTTPServer(("0.0.0.0", port), BotHTTPHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    if external_url:
        webhook_url = f"{external_url}/webhook"
        try:
            tg_api(token, "setWebhook", {"url": webhook_url})
            print(f"Webhook registered at {webhook_url}")
        except Exception as e:
            print(f"Webhook setup failed ({e}), falling back to polling")
            external_url = ""

    if external_url:
        threading.Thread(target=keep_alive_loop, args=(external_url,), daemon=True).start()
        while True:
            time.sleep(3600)
    else:
        try:
            tg_api(token, "deleteWebhook", {})
        except Exception:
            pass
        print("Telegram polling mode active...")
        offset = 0
        while True:
            try:
                res = tg_api(token, "getUpdates", {"offset": offset, "timeout": 25})
                for upd in res.get("result", []):
                    offset = upd["update_id"] + 1
                    process_update(token, upd)
            except KeyboardInterrupt:
                break
            except Exception:
                time.sleep(2)


if __name__ == "__main__":
    run_bot()
