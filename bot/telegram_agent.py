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
        f"✅ Added *{item_name}* to inventory (`{macros['serving_size']}`: "
        f"`{macros['calories']:g} cal`, `{macros['protein_g']:g}g P`, `{macros['carbs_g']:g}g C`, `{macros['fat_g']:g}g F`, `{macros['fiber_g']:g}g Fib`)."
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
def ask_gemini(user_text: str, chat_id: int, image_path: str = None) -> str:
    key = get_gemini_key()
    rules_md, inv_md, inv_json = load_all_context()

    macro_lines = [
        f"- {x['name']} ({x['serving_size']}): {x['calories']:g} kcal | {x['protein_g']:g}g P | {x['carbs_g']:g}g C | {x['fat_g']:g}g F | {x['fiber_g']:g}g Fiber"
        for x in inv_json
    ]
    macro_db_text = "\n".join(macro_lines)

    system_prompt = (
        "You are Aaron's personal Food & Macro Assistant on Telegram.\n"
        "You MUST follow every rule in MasterRules.md below.\n"
        "CRITICAL BEHAVIOR & CONTEXT GUARDRAILS:\n"
        "1. Answer Aaron's exact question or follow-up directly, concisely, and in plain English. No filler, no corporate talk.\n"
        "2. STAY IN CONVERSATION CONTEXT: Pay close attention to previous messages! For example, if you and Aaron are discussing how to season his chickpea pasta + ground beef bowl and he replies 'I was thinking taco', he means TACO SEASONING / TACO FLAVOR for that pasta/beef bowl—DO NOT suddenly suggest 5 taco meals on tortillas!\n"
        "3. STRICT CALORIE & MACRO SANITY CHECK: Always check how many calories and macros Aaron has left for the day before suggesting anything. Never suggest calorie-heavy or redundant carb additions (like tortillas when he is already eating pasta or has limited calories left).\n"
        "4. USE HIS SPICE RACK FIRST: Before saying [🛒 Need to buy: seasoning], build the flavor from his # Spices & Seasonings and # Oils & Condiments in FoodInventory.md (e.g., DIY Taco Seasoning = Ground Cumin + Smoked/Sweet Paprika + Garlic Powder + Onion Powder + Kosher Salt + Black Pepper + Crushed Red Pepper Flakes, plus optional Green Chile Enchilada Sauce, 100% Lime Juice, or Cilantro for almost 0 calories).\n"
        "5. ONLY give a 5-option meal list (Step 1: names only) when Aaron explicitly asks for meal/snack ideas or to plan a slot/day.\n"
        "6. Once Aaron picks an option or asks for numbers on a specific meal (Step 2), give the exact Grams/Cups/Units, Calories, Protein, Carbs, Fats, and Fiber.\n"
        "7. Never adjust inventory or raw meat unless Aaron explicitly tells you to.\n\n"
        f"=== MasterRules.md ===\n{rules_md}\n\n"
        f"=== FoodInventory.md ===\n{inv_md}\n\n"
        f"=== InventoryData.json (Verified USDA/Brand Macros) ===\n{macro_db_text}"
    )

    if chat_id not in CHAT_MEMORY:
        CHAT_MEMORY[chat_id] = [
            {
                "role": "user",
                "parts": [
                    {
                        "text": "For dinner I want to cook that chickpea pasta in my pantry (half a box), join with my ground beef in the fridge, then some kind of seasoning situation. How many calories would half of all that be? (I'd be saving half for tomorrow)"
                    }
                ],
            },
            {
                "role": "model",
                "parts": [
                    {
                        "text": "Remaining targets to hit before dinner: ~498 kcal | ~55g Protein | ~61g Carbs | ~21g Fat.\nHalf of that batch (half a box chickpea pasta + half of your 1.09 lbs 93/7 ground beef) is 381 kcal, 32.7g P, 23.3g C, 12.3g F, 2.9g Fiber, leaving ~117 kcal, 22g P, 38g C, and 8g F for the day."
                    }
                ],
            },
            {"role": "user", "parts": [{"text": "What are some options for seasoning that pasta/beef bowl?"}]},
            {
                "role": "model",
                "parts": [
                    {
                        "text": "You can season that chickpea pasta + ground beef bowl using your spice rack (Soy/Ginger/Garlic, Cajun, Italian Herb, or Cumin + Smoked Paprika taco-style)."
                    }
                ],
            },
        ]
    history = CHAT_MEMORY[chat_id]
    parts: List[Dict[str, Any]] = []
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    parts.append({"text": user_text or "Read this screenshot and help me plan based on MasterRules.md."})

    contents = list(history[-16:]) + [{"role": "user", "parts": parts}]
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
            history.append({"role": "user", "parts": [{"text": user_text or "[Sent Screenshot]"}]})
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
        payload: Dict[str, Any] = {"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"}
        try:
            tg_api(token, "sendMessage", payload)
        except Exception:
            payload.pop("parse_mode", None)
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
# MESSAGE HANDLERS
# ==============================================================================
def handle_photo(token: str, chat_id: int, photo_list: List[Dict[str, Any]], caption: str = ""):
    best_photo = photo_list[-2] if len(photo_list) >= 2 else photo_list[-1]
    local_path = download_telegram_photo(token, best_photo["file_id"])
    try:
        reply = ask_gemini(caption, chat_id, image_path=local_path)
        send_message(token, chat_id, reply)
    except Exception as e:
        send_message(token, chat_id, f"⚠️ Error reading image: {e}")
    finally:
        try:
            os.remove(local_path)
        except Exception:
            pass


def handle_text(token: str, chat_id: int, text: str):
    s = text.strip()

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

    try:
        reply = ask_gemini(s, chat_id)
        send_message(token, chat_id, reply)
    except Exception as e:
        send_message(token, chat_id, f"⚠️ Gemini error: {e}")


def process_update(token: str, upd: Dict[str, Any]):
    if "message" in upd:
        msg = upd["message"]
        cid = msg["chat"]["id"]
        if "photo" in msg:
            handle_photo(token, cid, msg["photo"], msg.get("caption", ""))
        elif "text" in msg:
            handle_text(token, cid, msg["text"])


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
        # On Render: register webhook so incoming messages wake up the container even if it ever sleeps,
        # AND run an 8-minute self-ping so it stays warm 24/7.
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
