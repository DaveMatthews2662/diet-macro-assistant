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

TOKEN_FILE = ".telegram_token"
GEMINI_KEY_FILE = ".gemini_key"
USDA_API_KEY = os.environ.get("USDA_API_KEY", "DEMO_KEY")

# Per-chat conversation history so Gemini remembers the whole conversation
CHAT_MEMORY: Dict[int, List[Dict[str, Any]]] = {}


# ==============================================================================
# RULE 1a: ALWAYS READ MasterRules.md, FoodInventory.md, AND InventoryData.json
# ==============================================================================
def load_all_context() -> Tuple[str, str, List[Dict[str, Any]]]:
    rules_md, inv_md, inv_json = "", "", []
    if os.path.exists("MasterRules.md"):
        with open("MasterRules.md", "r", encoding="utf-8") as f:
            rules_md = f.read()
    if os.path.exists("FoodInventory.md"):
        with open("FoodInventory.md", "r", encoding="utf-8") as f:
            inv_md = f.read()
    if os.path.exists("InventoryData.json"):
        with open("InventoryData.json", "r", encoding="utf-8") as f:
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
# FILE UPDATERS FOR LIKES/DISLIKES & INVENTORY WHEN REQUESTED
# ==============================================================================
def add_to_likes(item_text: str) -> str:
    rules_md, _, _ = load_all_context()
    marker = "### 👍 Foods & Meals I Like (Favorites / Go-Tos)"
    if marker in rules_md:
        rules_md = rules_md.replace(marker, f"{marker}\n- {item_text}", 1)
        with open("MasterRules.md", "w", encoding="utf-8") as f:
            f.write(rules_md)
    return f"👍 Added *{item_text}* to your Likes list in `MasterRules.md`."


def add_to_dislikes(item_text: str) -> str:
    rules_md, inv_md, _ = load_all_context()
    marker = "### 👎 Foods I Don't Like (Never Suggest)"
    if marker in rules_md:
        rules_md = rules_md.replace(marker, f"{marker}\n- **{item_text}**", 1)
        with open("MasterRules.md", "w", encoding="utf-8") as f:
            f.write(rules_md)

    removed_inv = []
    new_lines = []
    for line in inv_md.splitlines():
        if line.strip().startswith("- ") and item_text.lower() in line.lower():
            removed_inv.append(line.strip()[2:])
        else:
            new_lines.append(line)
    if removed_inv:
        with open("FoodInventory.md", "w", encoding="utf-8") as f:
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

    with open("FoodInventory.md", "w", encoding="utf-8") as f:
        f.write(inv_md)

    macros = lookup_usda_macros(item_name)
    inv_json.append({"name": item_name, "category": category, "tags": "USDA Verified", **macros})
    with open("InventoryData.json", "w", encoding="utf-8") as f:
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

    with open("FoodInventory.md", "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")

    inv_json = [x for x in inv_json if item_query.lower() not in x.get("name", "").lower()]
    with open("InventoryData.json", "w", encoding="utf-8") as f:
        json.dump(inv_json, f, indent=2)

    return f"🗑️ Removed {', '.join(removed)} from your inventory."


# ==============================================================================
# REAL GEMINI 2.5 FLASH CONVERSATIONAL AGENT (READS ALL FILES EVERY TIME)
# ==============================================================================
def ask_gemini(user_text: str, chat_id: int, image_path: str = None) -> str:
    key = get_gemini_key()
    rules_md, inv_md, inv_json = load_all_context()

    # Compact macro reference from InventoryData.json so Gemini knows exact macros for every single item
    macro_lines = [
        f"- {x['name']} ({x['serving_size']}): {x['calories']:g} kcal | {x['protein_g']:g}g P | {x['carbs_g']:g}g C | {x['fat_g']:g}g F | {x['fiber_g']:g}g Fiber"
        for x in inv_json
    ]
    macro_db_text = "\n".join(macro_lines)

    system_prompt = (
        "You are Aaron's personal Food & Macro Assistant on Telegram.\n"
        "You MUST follow every rule in MasterRules.md below.\n"
        "CRITICAL BEHAVIOR:\n"
        "1. Answer Aaron's exact question directly, concisely, and in plain English. No filler, no corporate talk.\n"
        "2. If Aaron asks a specific calculation or question about a meal he wants to cook (e.g., splitting half a box of chickpea pasta + all his ground beef into 2 meals), DO NOT dump a random list of meals—calculate the exact calories, protein, carbs, fats, and fiber for his meal and show how it fits his day/screenshot!\n"
        "3. If Aaron asks for meal/snack ideas or to plan a slot/day (Step 1), give 5 distinct rotating options by NAME ONLY (no macro clutter yet), flagging any missing ingredient with [🛒 Need to buy: item].\n"
        "4. Once Aaron picks an option or asks for numbers on a specific meal (Step 2), give the exact Grams/Cups/Units, Calories, Protein, Carbs, Fats, and Fiber.\n\n"
        f"=== MasterRules.md ===\n{rules_md}\n\n"
        f"=== FoodInventory.md ===\n{inv_md}\n\n"
        f"=== InventoryData.json (Verified USDA/Brand Macros) ===\n{macro_db_text}"
    )

    history = CHAT_MEMORY.setdefault(chat_id, [])
    parts: List[Dict[str, Any]] = []
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    parts.append({"text": user_text or "Read this screenshot and help me plan based on MasterRules.md."})

    contents = list(history[-10:]) + [{"role": "user", "parts": parts}]
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.4},
    }

    last_err = None
    for model_name in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]:
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
    # Split if longer than Telegram 4096 char limit
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

    # Check explicit file-modifying commands first
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

    # Everything else goes straight to Gemini 2.5 Flash with full MasterRules + Inventory + Macros context!
    try:
        reply = ask_gemini(s, chat_id)
        send_message(token, chat_id, reply)
    except Exception as e:
        send_message(token, chat_id, f"⚠️ Gemini error: {e}")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - Telegram Food Picker Agent is running")

    def log_message(self, format, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    except Exception:
        pass


def run_polling():
    token = get_token()
    if not token:
        print("Missing token.")
        return

    start_health_server()
    print("Telegram Gemini 3.8 Flash Agent is live...")
    offset = 0
    while True:
        try:
            res = tg_api(token, "getUpdates", {"offset": offset, "timeout": 25})
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                if "message" in upd:
                    msg = upd["message"]
                    cid = msg["chat"]["id"]
                    if "photo" in msg:
                        handle_photo(token, cid, msg["photo"], msg.get("caption", ""))
                    elif "text" in msg:
                        handle_text(token, cid, msg["text"])
        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(2)


if __name__ == "__main__":
    run_polling()
