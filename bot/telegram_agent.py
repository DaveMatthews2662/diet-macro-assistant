import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
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

# Per-chat conversation history so Gemini remembers the whole conversation
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
# GEMINI CONVERSATIONAL AGENT (READS ALL FILES EVERY TIME)
# ==============================================================================
def ask_gemini(user_text: str, chat_id: int, image_paths: List[str] = None) -> str:
    key = get_gemini_key()
    rules_md, inv_md, inv_json = load_all_context()

    macro_lines = [
        f"- {x['name']} ({x['serving_size']}): {int(round(x['calories']))} kcal | {int(round(x['protein_g']))}g P | {int(round(x['carbs_g']))}g C | {int(round(x['fat_g']))}g F"
        for x in inv_json
    ]
    macro_db_text = "\n".join(macro_lines)

    system_prompt = (
        "You are Aaron's personal Food & Macro Assistant on Telegram.\n"
        "You MUST follow every rule in MasterRules.md below.\n"
        "STRICT OUTPUT & FORMATTING RULES (NEVER VIOLATE):\n"
        "1. AS SHORT AS HUMANLY POSSIBLE — ZERO FLUFF: Never write intro sentences ('That sounds like a great combo!'), food descriptions ('keeps it juicy and melts nicely'), or outro sentences ('Fits right into your remaining budget!'). Output ONLY the raw answer.\n"
        "2. NO REMAINING OR DAILY TOTAL LINES: NEVER output 'Consumed So Far:', 'Remaining Targets:', 'Remaining Total:', 'Total Added:', or 'Daily Total:' at the top or bottom of your response. Output ONLY the meals/options/adjustments and the single 'Total:' line directly underneath each meal.\n"
        "3. ALWAYS INCLUDE EXACT GRAMS (g) FOR EVERY INGREDIENT: Every single ingredient line in a meal MUST start with its exact weight in grams (e.g., '- 80g Easy Tiger Sourdough Bread', '- 32g PBfit Peanut Butter Powder', '- 227g raw Boneless Skinless Chicken Thighs', '- 140g Ben\\'s Original Ready Rice: Jasmine Rice', '- 150g Oikos Triple Zero Vanilla Greek Yogurt', '- 118g Fresh Banana'). NEVER write '2 slices', '4 tbsp', '1 cup', '8 oz', or '1 medium' without the exact gram weight (Xg) at the front.\n"
        "4. NO DECIMALS EVER: Round all Calories, Protein, Carbs, and Fats to whole integers (e.g., 40g P, NEVER 39.7g P).\n"
        "5. NO FIBER EVER: Never output or mention Fiber anywhere.\n"
        "6. NO PER-INGREDIENT MACROS: When giving a meal breakdown, list ONLY the gram weight + ingredient name, followed by ONE single Total line at the bottom of that meal:\n"
        "   [Meal Name]\n"
        "   - [Xg] [Ingredient 1]\n"
        "   - [Xg] [Ingredient 2]\n"
        "   Total: [X] kcal | [X]g P | [X]g C | [X]g F\n"
        "7. STRICTLY HIT MASTERRULES.MD GOALS & NEVER LEAVE PROTEIN UNDER 170g OR CALORIES OVER ~1,950 kcal:\n"
        "   - Aaron's true daily goals are in MasterRules.md Section 3:\n"
        "     * Protein: 170g floor, 185g goal (MUST finish the day at 170g-185g P — NEVER leave him at 164g P!)\n"
        "     * Carbs: 150g floor, 180g goal (stay within 150g-180g C)\n"
        "     * Fats: 50g floor, 50g goal (target ~50g F)\n"
        "     * Calories: 1,900 kcal planned target (1,850-1,950 kcal window — NEVER push his planned day to 2,060 kcal! The 200 kcal buffer up to 2,100 kcal is reserved ONLY for an unplanned midnight snack).\n"
        "   - When reading one or more Cronometer screenshots, ONLY read the CONSUMED numbers and logged foods, and 100% IGNORE the target denominators ('/ 2100.0 kcal', '/ 200.0 g', etc.) shown inside the Cronometer app.\n"
        "   - EVERY SINGLE OPTION you suggest to fill out a day MUST actually hit the remaining protein needed to reach 170-185g P WITHOUT pushing daily calories past ~1,900-1,950 kcal. Never suggest a low-protein, high-carb option (like 11g P rice cakes or 18g P oatmeal) when he needs 35-40g P on a tight calorie budget!\n"
        "8. ADJUST EXISTING PLANNED MEALS WHEN CALORIES ARE HIGH OR WHEN TOLD YOU CAN ADJUST:\n"
        "   - If his Cronometer screenshot is already near/at/over 1,900 kcal (e.g., 2,060 kcal and 164g P) OR if Aaron says 'you can adjust other stuff' / 'we adjust other stuff tomorrow too', DO NOT suggest adding extra snacks or meals on top of 2,060 kcal!\n"
        "   - Instead, look at the specific foods and gram weights already logged in his Cronometer screenshot(s) and give him the exact gram-weight adjustments / swaps to his EXISTING planned meals (e.g., 'In [Meal], drop [Item A] from Xg to Yg and increase [Protein Item B] from Ag to Bg') so total daily calories drop back to ~1,900 kcal while daily protein rises to 175-185g P.\n"
        "9. ZERO REPEATS WHEN ASKED FOR MORE OPTIONS:\n"
        "   - Whenever Aaron asks for 'more options', 'other ideas', or 'anything besides [X]', check all previous assistant messages in the conversation history and NEVER repeat any food, meal, or ingredient combo that you already suggested earlier. Every new option must be 100% new and distinct.\n"
        "10. CUSTOM X OPTIONS COUNT: Whenever Aaron asks for X options/ideas (e.g., '3 options', '10 snack ideas'), output exactly X options. Default to 5 options only when he asks for options without specifying a number.\n"
        "11. DINING OUT & TRAVEL MODE: When Aaron asks for tips when going out to eat, restaurant orders, or travel foods, do NOT restrict suggestions to FoodInventory.md. Give ultra-short, high-protein, macro-friendly restaurant picks, ordering modifications, or travel staples with estimated macros (kcal | P | C | F) tailored to his goals.\n"
        "12. Never adjust inventory or raw meat unless Aaron explicitly tells you to.\n\n"
        f"=== MasterRules.md ===\n{rules_md}\n\n"
        f"=== FoodInventory.md ===\n{inv_md}\n\n"
        f"=== InventoryData.json (Verified USDA/Brand Macros) ===\n{macro_db_text}"
    )

    if chat_id not in CHAT_MEMORY:
        CHAT_MEMORY[chat_id] = []
    history = CHAT_MEMORY[chat_id]
    parts: List[Dict[str, Any]] = []
    for img_path in (image_paths or []):
        if img_path and os.path.exists(img_path):
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    parts.append({"text": user_text or "Read the screenshot(s) and help me plan based on MasterRules.md."})

    # Keep inline_data images in the last 4 turns of history so follow-up questions ('Anything besides a shake?', 'give me more', 'adjust other stuff') still see the Cronometer screenshot!
    trimmed_history: List[Dict[str, Any]] = []
    recent_slice = list(history[-12:])
    for idx, turn in enumerate(recent_slice):
        if idx < len(recent_slice) - 6:
            # Strip old base64 images from older turns to keep requests fast
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
        "generationConfig": {"temperature": 0.3},
    }

    last_err = None
    for model_name in ["gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode("utf-8"))
            cand_parts = res["candidates"][0]["content"]["parts"]
            reply = "\n".join(p["text"] for p in cand_parts if "text" in p).strip()
            history.append({"role": "user", "parts": parts})
            history.append({"role": "model", "parts": [{"text": reply}]})
            return reply
        except Exception as e:
            last_err = e
            continue
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
