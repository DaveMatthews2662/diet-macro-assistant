import base64
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import random
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple, Any
try:
    from bot import wabbits_agent
except Exception:
    import wabbits_agent
try:
    from bot import lifting_agent
except Exception:
    import lifting_agent

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
OVERRIDES_FILE = resolve_path("persistent_overrides.json", "inventory")
TOKEN_FILE = resolve_path(".telegram_token", "bot")
GEMINI_KEY_FILE = resolve_path(".gemini_key", "bot")
USDA_API_KEY = os.environ.get("USDA_API_KEY", "DEMO_KEY")

# Per-chat conversation history so Gemini remembers the whole conversation + screenshots
CHAT_MEMORY: Dict[int, List[Dict[str, Any]]] = {}

# Per-chat batching so multi-screenshot uploads / rapid messages produce ONE single reply
BATCH_LOCK = threading.Lock()
CHAT_BATCH: Dict[int, Dict[str, Any]] = {}
BATCH_DELAY_SEC = 2.0

# Cloud sync flag so Render containers automatically restore Telegram-side inventory edits on wakeup
CLOUD_SYNC_DONE = False
CLOUD_SYNC_LOCK = threading.Lock()


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
# PERSISTENT OVERRIDES + TELEGRAM CLOUD STORAGE (SURVIVES RENDER RESTARTS)
# ==============================================================================
def item_matches_query(item_text: str, query: str) -> bool:
    q = query.strip().lower()
    t = item_text.strip().lower()
    if not q or not t:
        return False
    if q in t:
        return True
    # Normalize punctuation (e.g. "h-e-b" -> "heb", plural trailing 's')
    q_norm = re.sub(r"[^a-z0-9\s]", "", q)
    t_norm = re.sub(r"[^a-z0-9\s]", "", t)
    if q_norm and q_norm in t_norm:
        return True
    tokens = [w.rstrip("s") for w in q_norm.split() if len(w.rstrip("s")) >= 2]
    if tokens and all(tok in t_norm for tok in tokens):
        return True
    return False


def load_local_overrides() -> Dict[str, Any]:
    default_ov = {
        "removed": [
            "H-E-B Cage-Free 100% Liquid Egg Whites",
            "H-E-B Low-Fat Small Curd Cottage Cheese",
            "egg whites",
            "cottage cheese",
        ],
        "added": [],
        "likes": [],
        "dislikes": [],
        "notes": [],
    }
    if os.path.exists(OVERRIDES_FILE):
        try:
            with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in default_ov:
                if k not in data or not isinstance(data[k], list):
                    data[k] = list(default_ov[k])
            return data
        except Exception:
            pass
    return default_ov


def save_local_overrides(ov: Dict[str, Any]):
    try:
        with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
            json.dump(ov, f, indent=2)
    except Exception as e:
        print(f"[overrides] Failed to save local overrides: {e}", flush=True)


def save_overrides_to_telegram_cloud(ov: Dict[str, Any]):
    """Persist overrides in Telegram's cloud under a hidden command scope so Render restarts never lose state."""
    token = get_token()
    if not token:
        return
    try:
        raw_bytes = json.dumps(ov, separators=(",", ":")).encode("utf-8")
        b64_str = base64.b64encode(raw_bytes).decode("ascii")
        chunks = [b64_str[i : i + 240] for i in range(0, len(b64_str), 240)][:95]
        commands = [{"command": f"s{idx}", "description": ch} for idx, ch in enumerate(chunks)]
        res = tg_api(
            token,
            "setMyCommands",
            {
                "commands": commands,
                "scope": {"type": "all_chat_administrators"},
                "language_code": "eo",
            },
        )
        if res.get("ok"):
            print(f"[overrides] Saved overrides to Telegram cloud ({len(chunks)} chunks).", flush=True)
        else:
            print(f"[overrides] Telegram cloud save rejected: {res}", flush=True)
    except Exception as e:
        print(f"[overrides] Telegram cloud save FAILED: {e}", flush=True)


def sync_overrides_from_telegram_cloud() -> Dict[str, Any]:
    """Fetch cloud-persisted overrides from Telegram on container startup and merge with local overrides."""
    global CLOUD_SYNC_DONE
    local_ov = load_local_overrides()
    if CLOUD_SYNC_DONE:
        return local_ov

    with CLOUD_SYNC_LOCK:
        if CLOUD_SYNC_DONE:
            return load_local_overrides()
        CLOUD_SYNC_DONE = True
        token = get_token()
        if not token:
            return local_ov
        try:
            res = tg_api(
                token,
                "getMyCommands",
                {
                    "scope": {"type": "all_chat_administrators"},
                    "language_code": "eo",
                },
            )
            cmds = res.get("result", [])
            if cmds:
                cmds_sorted = sorted(
                    [c for c in cmds if str(c.get("command", "")).startswith("s")],
                    key=lambda x: int(x["command"][1:]) if x["command"][1:].isdigit() else 0,
                )
                b64_str = "".join(c.get("description", "") for c in cmds_sorted)
                if b64_str:
                    cloud_ov = json.loads(base64.b64decode(b64_str.encode("ascii")).decode("utf-8"))
                    # Merge cloud_ov and local_ov
                    for key in ["removed", "likes", "dislikes"]:
                        existing_low = {x.lower() for x in local_ov.get(key, [])}
                        for item in cloud_ov.get(key, []):
                            if isinstance(item, str) and item.lower() not in existing_low:
                                local_ov.setdefault(key, []).append(item)
                                existing_low.add(item.lower())
                    existing_added = {x.get("name", "").lower() for x in local_ov.get("added", []) if isinstance(x, dict)}
                    for item in cloud_ov.get("added", []):
                        if isinstance(item, dict):
                            nm = item.get("name", "")
                            if nm and nm.lower() not in existing_added:
                                if not any(item_matches_query(nm, r) for r in local_ov.get("removed", [])):
                                    local_ov.setdefault("added", []).append(item)
                                    existing_added.add(nm.lower())
                    existing_notes = {json.dumps(x, sort_keys=True) for x in local_ov.get("notes", [])}
                    for note_item in cloud_ov.get("notes", []):
                        s_note = json.dumps(note_item, sort_keys=True)
                        if s_note not in existing_notes:
                            local_ov.setdefault("notes", []).append(note_item)
                            existing_notes.add(s_note)
                    save_local_overrides(local_ov)
            # Push merged state back so cloud also has any newly committed repo removals
            save_overrides_to_telegram_cloud(local_ov)
            print(f"[overrides] Startup sync done ({len(cmds)} cloud chunks found).", flush=True)
        except Exception as e:
            print(f"[overrides] Telegram cloud sync FAILED: {e}", flush=True)
        return local_ov


def append_project_note(note_text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    ov = sync_overrides_from_telegram_cloud()
    entry = {"timestamp": ts, "text": note_text.strip()}
    ov.setdefault("notes", []).append(entry)
    save_local_overrides(ov)
    threading.Thread(target=save_overrides_to_telegram_cloud, args=(ov,), daemon=True).start()


# ==============================================================================
# RULE 1a: ALWAYS READ MasterRules.md, FoodInventory.md, AND InventoryData.json
# ==============================================================================
def load_all_context() -> Tuple[str, str, List[Dict[str, Any]]]:
    ov = sync_overrides_from_telegram_cloud()
    removed_queries: List[str] = list(ov.get("removed", [])) + list(ov.get("dislikes", []))

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

    # Enforce any cloud-persisted added items first
    existing_json_names = {x.get("name", "").lower() for x in inv_json}
    md_dirty = False
    json_dirty = False

    for add_obj in ov.get("added", []):
        if not isinstance(add_obj, dict):
            continue
        nm = add_obj.get("name", "").strip()
        cat = add_obj.get("category", "Pantry & Canned")
        if not nm or any(item_matches_query(nm, rq) for rq in removed_queries):
            continue
        if nm.lower() not in inv_md.lower():
            header = f"# {cat}"
            if header in inv_md:
                inv_md = inv_md.replace(header, f"{header}\n- {nm}", 1)
            else:
                inv_md = inv_md.rstrip() + f"\n\n{header}\n- {nm}\n"
            md_dirty = True
        if nm.lower() not in existing_json_names:
            inv_json.append(add_obj)
            existing_json_names.add(nm.lower())
            json_dirty = True

    # Enforce all removed & disliked items across both FoodInventory.md and InventoryData.json
    if removed_queries:
        filtered_md_lines = []
        for line in inv_md.splitlines():
            if line.strip().startswith("- "):
                item_label = line.strip()[2:]
                if any(item_matches_query(item_label, rq) for rq in removed_queries):
                    md_dirty = True
                    continue
            filtered_md_lines.append(line)
        if md_dirty:
            inv_md = "\n".join(filtered_md_lines) + "\n"

        new_inv_json = [
            x for x in inv_json if not any(item_matches_query(x.get("name", ""), rq) for rq in removed_queries)
        ]
        if len(new_inv_json) != len(inv_json):
            inv_json = new_inv_json
            json_dirty = True

    if md_dirty:
        try:
            with open(INV_MD_FILE, "w", encoding="utf-8") as f:
                f.write(inv_md)
        except Exception:
            pass
    if json_dirty:
        try:
            with open(INV_JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(inv_json, f, indent=2)
        except Exception:
            pass

    return rules_md, inv_md, inv_json


# ==============================================================================
# FILE UPDATERS FOR LIKES/DISLIKES & INVENTORY WHEN EXPLICITLY REQUESTED
# ==============================================================================
def split_multi_items(raw_query: str, inv_md: str, inv_json: List[Dict[str, Any]]) -> List[str]:
    cleaned = raw_query.strip()
    if not cleaned:
        return []
    # If the exact full phrase matches an existing item (e.g., "Bean & Cheese Burritos"), keep it as 1 item
    for line in inv_md.splitlines():
        if line.strip().startswith("- ") and cleaned.lower() in line.strip()[2:].lower():
            return [cleaned]
    for x in inv_json:
        if cleaned.lower() in x.get("name", "").lower():
            return [cleaned]

    # Otherwise split on commas, semicolons, "and", "&", "+"
    parts = re.split(r"\s*(?:,|;|\band\b|&|\+)\s*", cleaned, flags=re.I)
    results = []
    for p in parts:
        p_clean = re.sub(r"^(?:the|my|some)\s+", "", p.strip(), flags=re.I)
        p_clean = re.sub(r"\s+from\s+(?:my\s+)?inventory$", "", p_clean, flags=re.I).strip()
        if p_clean:
            results.append(p_clean)
    return results or [cleaned]


def add_to_likes(item_text: str) -> str:
    rules_md, _, _ = load_all_context()
    ov = load_local_overrides()
    marker = "### 👍 Foods & Meals I Like (Favorites / Go-Tos)"
    if marker in rules_md and item_text.lower() not in rules_md.lower():
        rules_md = rules_md.replace(marker, f"{marker}\n- {item_text}", 1)
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            f.write(rules_md)
    if item_text.lower() not in {x.lower() for x in ov.get("likes", [])}:
        ov.setdefault("likes", []).append(item_text)
        save_local_overrides(ov)
        threading.Thread(target=save_overrides_to_telegram_cloud, args=(ov,), daemon=True).start()
    return f"👍 Added *{item_text}* to your Likes list in `MasterRules.md`."


def add_to_dislikes(item_text: str) -> str:
    rules_md, inv_md, inv_json = load_all_context()
    ov = load_local_overrides()
    items = split_multi_items(item_text, inv_md, inv_json)

    marker = "### 👎 Foods I Don't Like (Never Suggest)"
    for it in items:
        if marker in rules_md and it.lower() not in rules_md.lower():
            rules_md = rules_md.replace(marker, f"{marker}\n- **{it}**", 1)
        if it.lower() not in {x.lower() for x in ov.get("dislikes", [])}:
            ov.setdefault("dislikes", []).append(it)
        if it.lower() not in {x.lower() for x in ov.get("removed", [])}:
            ov.setdefault("removed", []).append(it)

    with open(RULES_FILE, "w", encoding="utf-8") as f:
        f.write(rules_md)

    save_local_overrides(ov)
    threading.Thread(target=save_overrides_to_telegram_cloud, args=(ov,), daemon=True).start()
    load_all_context()
    return f"👎 Added *{', '.join(items)}* to your Dislikes list and removed from inventory."


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
    ov = load_local_overrides()
    low_type = item_name.lower()
    if any(k in low_type for k in ["raw", "steak", "ground beef", "chicken thigh", "chicken breast", "pork", "salmon"]):
        if "raw" in low_type or "lbs" in low_type or "lb" in low_type:
            category = "Raw Meat (Finite Tracked Stock)"

    # If this item was previously in the removed list, un-remove it
    ov["removed"] = [
        r for r in ov.get("removed", []) if not (item_matches_query(item_name, r) or item_matches_query(r, item_name))
    ]

    header = f"# {category}"
    if header in inv_md:
        inv_md = inv_md.replace(header, f"{header}\n- {item_name}", 1)
    else:
        inv_md = inv_md.rstrip() + f"\n\n{header}\n- {item_name}\n"

    with open(INV_MD_FILE, "w", encoding="utf-8") as f:
        f.write(inv_md)

    macros = lookup_usda_macros(item_name)
    new_entry = {"name": item_name, "category": category, "tags": "USDA Verified", **macros}
    inv_json.append(new_entry)
    with open(INV_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(inv_json, f, indent=2)

    ov.setdefault("added", []).append(new_entry)
    save_local_overrides(ov)
    threading.Thread(target=save_overrides_to_telegram_cloud, args=(ov,), daemon=True).start()

    return (
        f"✅ Added *{item_name}* (`{macros['serving_size']}`: "
        f"`{int(round(macros['calories']))} kcal` | `{int(round(macros['protein_g']))}g P` | `{int(round(macros['carbs_g']))}g C` | `{int(round(macros['fat_g']))}g F`)."
    )


def remove_item_from_inventory(item_query: str, chat_id: int = None) -> str:
    _, inv_md, inv_json = load_all_context()
    ov = load_local_overrides()
    queries = split_multi_items(item_query, inv_md, inv_json)

    removed_names: List[str] = []
    already_removed_queries: List[str] = []

    new_lines = []
    for line in inv_md.splitlines():
        if line.strip().startswith("- "):
            item_label = line.strip()[2:]
            if any(item_matches_query(item_label, q) for q in queries):
                if item_label not in removed_names:
                    removed_names.append(item_label)
                continue
        new_lines.append(line)

    remaining_json = []
    for x in inv_json:
        nm = x.get("name", "")
        if any(item_matches_query(nm, q) for q in queries):
            if nm and nm not in removed_names:
                removed_names.append(nm)
        else:
            remaining_json.append(x)

    # Track which requested queries were already removed vs newly removed
    for q in queries:
        if not any(item_matches_query(rn, q) for rn in removed_names):
            already_removed_queries.append(q)
        # Always add the query and any matched names to persistent `removed` list so they NEVER come back
        if q.lower() not in {r.lower() for r in ov.get("removed", [])}:
            ov.setdefault("removed", []).append(q)

    for rn in removed_names:
        if rn.lower() not in {r.lower() for r in ov.get("removed", [])}:
            ov.setdefault("removed", []).append(rn)

    # Also remove from `added` overrides if present
    ov["added"] = [
        a for a in ov.get("added", []) if not any(item_matches_query(a.get("name", ""), q) for q in queries)
    ]

    with open(INV_MD_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")

    with open(INV_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(remaining_json, f, indent=2)

    save_local_overrides(ov)
    threading.Thread(target=save_overrides_to_telegram_cloud, args=(ov,), daemon=True).start()

    if removed_names and already_removed_queries:
        reply = (
            f"🗑️ Removed {', '.join(removed_names)} from your inventory "
            f"(and confirmed {', '.join(already_removed_queries)} is already removed and blocked from suggestions)."
        )
    elif removed_names:
        reply = f"🗑️ Removed {', '.join(removed_names)} from your inventory."
    else:
        reply = (
            f"🗑️ Confirmed *{', '.join(queries)}* is removed from your inventory and blocked from all future suggestions."
        )

    if chat_id is not None:
        if chat_id not in CHAT_MEMORY:
            CHAT_MEMORY[chat_id] = []
        CHAT_MEMORY[chat_id].append({"role": "user", "parts": [{"text": f"Remove {item_query} from my inventory"}]})
        CHAT_MEMORY[chat_id].append({"role": "model", "parts": [{"text": reply}]})

    return reply


# ==============================================================================
# RECEIPT & PHOTO-TO-INVENTORY PARSER (FAST VISION EXTRACTION + PERSISTENCE)
# ==============================================================================
def is_photo_inventory_request(text: str, has_photos: bool = False) -> bool:
    if not text:
        return False
    s = text.strip().lower()
    if any(w in s for w in ["receipt", "groceries", "grocery haul"]):
        return True
    if "inventory" in s and any(
        w in s
        for w in [
            "add",
            "update",
            "put",
            "save",
            "new",
            "not already",
            "missing",
            "sync",
            "import",
            "from this",
            "anything",
            "everything",
            "these",
            "this",
        ]
    ):
        return True
    return False


def is_generic_photo_reference(text: str) -> bool:
    """Returns True if an 'add X to inventory' message refers to a photo/receipt rather than a named food."""
    s = text.strip().lower()
    generic_phrases = [
        "anything",
        "everything",
        "not already",
        "whatever",
        "this",
        "these",
        "those",
        "receipt",
        "screenshot",
        "photo",
        "pic",
        "picture",
        "image",
        "items",
        "groceries",
    ]
    return any(gp in s for gp in generic_phrases)


def get_recent_memory_images(chat_id: int) -> List[str]:
    history = CHAT_MEMORY.get(chat_id, [])
    for turn in reversed(history[-4:]):
        if turn.get("role") == "user":
            b64s = [
                p["inline_data"]["data"]
                for p in turn.get("parts", [])
                if "inline_data" in p and isinstance(p["inline_data"], dict) and p["inline_data"].get("data")
            ]
            if b64s:
                return b64s
    return []


def call_gemini_generate(payload: Dict[str, Any], timeout_sec: int = 75) -> str:
    key = get_gemini_key()
    models = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash"]
    bad_models = set()
    last_err = None

    for attempt in range(2):
        for model_name in models:
            if model_name in bad_models:
                continue
            req_payload = json.loads(json.dumps(payload))
            if attempt == 1 and "thinkingConfig" in req_payload.get("generationConfig", {}):
                # On retry, drop thinkingConfig so fallback/lite models respond as fast as possible
                req_payload["generationConfig"].pop("thinkingConfig", None)
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(req_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                cand_parts = res["candidates"][0]["content"]["parts"]
                visible_texts = [p["text"] for p in cand_parts if "text" in p and not p.get("thought")]
                if not visible_texts:
                    visible_texts = [p["text"] for p in cand_parts if "text" in p]
                return "\n".join(visible_texts).strip()
            except urllib.error.HTTPError as he:
                last_err = he
                if he.code in (400, 404):
                    bad_models.add(model_name)
                    continue
                time.sleep(1.0)
            except Exception as e:
                last_err = e
                time.sleep(1.0)
                continue
    raise RuntimeError(f"Gemini API error: {last_err}")


def process_inventory_photo(
    user_text: str,
    chat_id: int,
    image_paths: List[str] = None,
    image_b64_list: List[str] = None,
) -> str:
    _, inv_md, inv_json = load_all_context()
    ov = load_local_overrides()

    b64_images: List[str] = list(image_b64_list or [])
    for img_path in (image_paths or []):
        if img_path and os.path.exists(img_path):
            with open(img_path, "rb") as f:
                b64_images.append(base64.b64encode(f.read()).decode("utf-8"))

    if not b64_images:
        return "⚠️ No receipt or food image found to add to inventory."

    existing_items_lines = [f"- [{x.get('category', '')}] {x.get('name', '')}" for x in inv_json]
    existing_items_text = "\n".join(existing_items_lines)

    prompt = (
        "You are reading a grocery receipt or food photo to update Aaron's kitchen inventory.\n"
        f"User instruction: {user_text or 'Add anything not already in my inventory'}\n\n"
        "EXISTING INVENTORY ITEMS:\n"
        f"{existing_items_text}\n\n"
        "INSTRUCTIONS:\n"
        "1. Read every food or drink item in the image(s). Decode abbreviated store receipt codes (e.g. H-E-B / Costco codes like "
        "'FRESH BAGD SGR SNAP PEAS' -> 'Fresh Bagged Sugar Snap Peas', "
        "'BB ZERO SUGAR ADDED BAKD' -> 'Bush\\'s Zero Sugar Added Baked Beans', "
        "'HERSHEY SPECIAL DK CHIPS' -> 'Hershey\\'s Special Dark Chocolate Chips', "
        "'BULK RUSSET POTATOES' -> 'Bulk Russet Potatoes', "
        "'CELERY STICKS' -> 'Fresh Celery Sticks', "
        "'EZ TIGER SOURDOUGH ROUND' -> 'Easy Tiger Sourdough Bread', "
        "'GM CHEERIOS HNY NT PRO FS' -> 'General Mills Cheerios Protein: Honey Nut', "
        "'OLD EL PASO GREEN ENCHILA' -> 'Green Chile Enchilada Sauce'). Ignore non-food items, taxes, coupons, or totals.\n"
        "2. Compare each decoded food against EXISTING INVENTORY ITEMS above:\n"
        "   - If the same product is already in the existing inventory (e.g. 'PREMIUM BANANAS' matches 'Fresh Bananas (Raw)', "
        "'FAIRLIFE MILK FAT FREE' matches 'Fairlife Fat-Free Ultra-Filtered Lactose-Free Milk', "
        "'FP CF DT COKE CN' / 'FP SPRITE ZERO CN' match 'Zero-Calorie Diet Soda (A&W Zero Sugar Root Beer, etc.)'), put its clean name in `already_in_inventory`.\n"
        "   - If it is NOT in the existing inventory (or is a distinct variety with different macros not yet in the list, such as 'Bush\\'s Zero Sugar Added Baked Beans' vs regular 'Bush\\'s Original / Homestyle Baked Beans', or 'Hershey\\'s Special Dark Chocolate Chips' vs 'Semi-Sweet'), include it in `added`.\n"
        "3. For every item in `added`, provide accurate nutrition facts per standard serving (with `serving_size` starting with exact grams `Xg`, and `carbs_g` as Net Carbs = Total Carbs minus Fiber to match Cronometer).\n"
        "4. Return ONLY valid JSON (no markdown code fences, no extra commentary) in this exact schema:\n"
        "{\n"
        '  "added": [\n'
        "    {\n"
        '      "name": "Clean Descriptive Product Name",\n'
        '      "category": "Produce",\n'
        '      "tags": "Good Carb Options, Good Fiber Options",\n'
        '      "serving_size": "100g",\n'
        '      "calories": 40.0,\n'
        '      "protein_g": 2.0,\n'
        '      "fat_g": 0.2,\n'
        '      "carbs_g": 5.0,\n'
        '      "fiber_g": 2.0\n'
        "    }\n"
        "  ],\n"
        '  "already_in_inventory": ["Clean Name 1", "Clean Name 2"]\n'
        "}\n"
        "Valid categories: Raw Meat (Finite Tracked Stock), Frozen Meat & Seafood, Dairy & Refrigerated, Produce, Bakery & Bread, Pantry & Canned, Frozen, Desserts, Candy & Snacks, Oils & Condiments, Baking & Grains, Drinks, Spices & Seasonings."
    )

    parts: List[Dict[str, Any]] = [
        {"inline_data": {"mime_type": "image/jpeg", "data": b64}} for b64 in b64_images
    ]
    parts.append({"text": prompt})

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "thinkingConfig": {"thinkingBudget": 512},
        },
    }

    raw_reply = call_gemini_generate(payload, timeout_sec=75)
    cleaned_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_reply.strip(), flags=re.I)
    m_obj = re.search(r"\{.*\}", cleaned_json, flags=re.S)
    if m_obj:
        cleaned_json = m_obj.group(0)

    try:
        parsed = json.loads(cleaned_json)
    except Exception:
        # Fallback if model returned plain text instead of JSON
        return raw_reply

    new_items = parsed.get("added", []) if isinstance(parsed, dict) else []
    skipped_items = parsed.get("already_in_inventory", []) if isinstance(parsed, dict) else []

    existing_names_lower = {x.get("name", "").strip().lower() for x in inv_json}
    added_confirmations: List[str] = []

    for item in new_items:
        if not isinstance(item, dict):
            continue
        nm = str(item.get("name", "")).strip()
        if not nm:
            continue
        if nm.lower() in existing_names_lower:
            if nm not in skipped_items:
                skipped_items.append(nm)
            continue

        cat = str(item.get("category", "Pantry & Canned")).strip() or "Pantry & Canned"
        serv = str(item.get("serving_size", "100g")).strip() or "100g"
        tags = str(item.get("tags", "")).strip()
        try:
            cal = round(float(item.get("calories", 100.0)), 1)
            p = round(float(item.get("protein_g", 5.0)), 1)
            fat = round(float(item.get("fat_g", 2.0)), 1)
            carbs = round(float(item.get("carbs_g", 15.0)), 1)
            fib = round(float(item.get("fiber_g", 1.0)), 1)
        except Exception:
            macros = lookup_usda_macros(nm)
            serv = macros["serving_size"]
            cal = macros["calories"]
            p = macros["protein_g"]
            fat = macros["fat_g"]
            carbs = macros["carbs_g"]
            fib = macros["fiber_g"]

        # Un-remove if previously in removed list
        ov["removed"] = [
            r for r in ov.get("removed", []) if not (item_matches_query(nm, r) or item_matches_query(r, nm))
        ]

        header = f"# {cat}"
        if header in inv_md:
            inv_md = inv_md.replace(header, f"{header}\n- {nm}", 1)
        else:
            inv_md = inv_md.rstrip() + f"\n\n{header}\n- {nm}\n"

        new_entry = {
            "name": nm,
            "category": cat,
            "tags": tags or "Receipt Verified",
            "serving_size": serv,
            "calories": cal,
            "protein_g": p,
            "fat_g": fat,
            "carbs_g": carbs,
            "fiber_g": fib,
        }
        inv_json.append(new_entry)
        existing_names_lower.add(nm.lower())
        ov.setdefault("added", []).append(new_entry)
        added_confirmations.append(
            f"- {nm} ({serv}: {int(round(cal))} kcal | {int(round(p))}g P | {int(round(carbs))}g C | {int(round(fat))}g F)"
        )

    if added_confirmations:
        with open(INV_MD_FILE, "w", encoding="utf-8") as f:
            f.write(inv_md)
        with open(INV_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(inv_json, f, indent=2)
        save_local_overrides(ov)
        threading.Thread(target=save_overrides_to_telegram_cloud, args=(ov,), daemon=True).start()

    lines_out: List[str] = []
    if added_confirmations:
        lines_out.append(f"✅ Added {len(added_confirmations)} new item(s) to inventory:")
        lines_out.extend(added_confirmations)
    elif skipped_items:
        lines_out.append("ℹ️ Everything on this receipt is already in your inventory.")
    else:
        return ""

    if skipped_items:
        lines_out.append(f"\nAlready in inventory (skipped): {', '.join(str(s) for s in skipped_items)}")

    reply = "\n".join(lines_out).strip()
    if chat_id not in CHAT_MEMORY:
        CHAT_MEMORY[chat_id] = []
    CHAT_MEMORY[chat_id].append({"role": "user", "parts": [{"text": user_text or "[Receipt photo uploaded]"}]})
    CHAT_MEMORY[chat_id].append({"role": "model", "parts": [{"text": reply}]})
    return reply


# ==============================================================================
# GEMINI 4 ARGON CONVERSATIONAL AGENT (WITH INVENTORY SHUFFLING & MEMORY)
# ==============================================================================
def ask_gemini(user_text: str, chat_id: int, image_paths: List[str] = None) -> str:
    rules_md, inv_md, inv_json = load_all_context()
    ov = load_local_overrides()
    removed_list = list(ov.get("removed", [])) + list(ov.get("dislikes", []))
    removed_block = ", ".join(removed_list) if removed_list else "None"

    # Shuffle inventory order on every turn so the model doesn't fixate on the first 10 items in the file!
    shuffled_inv = list(inv_json)
    random.shuffle(shuffled_inv)

    macro_lines = [
        f"- [{x.get('category', '')}] {x['name']} ({x['serving_size']}): {x['calories']:g} kcal | {x['protein_g']:g}g P | {x['carbs_g']:g}g C | {x['fat_g']:g}g F"
        for x in shuffled_inv
    ]
    macro_db_text = "\n".join(macro_lines)

    # Pick a random spotlight of 25 non-spice foods from across the inventory to inspire fresh rotation
    food_candidates = [
        x["name"]
        for x in shuffled_inv
        if x.get("calories", 0) >= 10 and "Spices" not in x.get("category", "")
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
        "You are Aaron's personal Diet & Macro Assistant on Telegram (@diet-macro-assistant-bot).\n"
        "You have the exact same deep reasoning and macro-math intelligence as normal Gemini chat, PLUS full access to Aaron's kitchen inventory (`FoodInventory.md` and `InventoryData.json`) and rules (`MasterRules.md`).\n\n"
        "CRITICAL REMOVED-INVENTORY GUARDRAIL (NEVER VIOLATE):\n"
        f"- The following items have been REMOVED from Aaron's inventory and MUST NEVER BE SUGGESTED under any circumstances (even if they appeared in earlier chat messages or screenshots): [{removed_block}].\n"
        "- For home meals/snacks/options, ONLY suggest foods that currently exist in `InventoryData.json` below!\n\n"
        "HOW TO THINK & SOLVE MACRO MATH (USE YOUR INTERNAL THINKING STEP):\n"
        "0. CRONOMETER-EXACT DECIMAL MATH (CRITICAL): InventoryData.json contains Aaron's exact Cronometer per-serving values (with Net Carbs so they match Cronometer's Net Carbs target bar). When calculating any meal or daily plan in your internal thinking step, ALWAYS multiply and sum the exact unrounded decimal values (e.g. 2.4g P per 40g Sourdough = 4.8g P for 80g; 22.8g P per 112g Steak = 45.4g P for 223g; 9.0g P per 56g Honey Turkey = 13.66g P for 85g) across each meal and across the whole day FIRST, and ONLY round to the nearest whole integer at the very end when formatting `Total:` and `Daily Total:`! Never round individual ingredients before summing.\n"
        "1. Read all meals, gram weights, and Consumed totals from the Cronometer screenshot(s) in the conversation (100% ignore Cronometer's right-side target denominators like '/ 2100 kcal' or '/ 200g P').\n"
        "2. Compare against Aaron's true daily goals from MasterRules.md Section 3:\n"
        "   - Protein: 170g floor, 185g goal (MUST end the day between 170g and 185g P — never leave him under 170g P! Aim for ~175-185g P so even after rounding he is comfortably above 170g P).\n"
        "   - Carbs: 150g floor, 180g goal (stay between 150g and 180g C)\n"
        "   - Fats: 50g floor, 50g goal (target ~50g F)\n"
        "   - Calories: ~1,900 kcal target for planned food (1,850-1,950 kcal window — never leave him at 2,060 kcal with 164g P!).\n"
        "3. SMART ADJUSTMENTS, HARD USER LOCKS & PRE-WORKOUT MEALS:\n"
        "   - Look at the whole day holistically!\n"
        "   - If his current plan is ALREADY high in calories (e.g. ~1,900-2,060 kcal) or if adding a snack would push calories over ~1,950 kcal while leaving protein short, OR whenever Aaron says you can adjust other stuff in his day: DO NOT just dump 5 extra snacks on top! Instead, adjust the gram weights or swap items in his existing planned meals on the screenshot so the whole day lands right on ~1,900 kcal | 175-185g P | 150-180g C | ~50g F.\n"
        "   - OBEY ALL USER LOCKS & NON-DECREASE FLOORS: If Aaron says e.g. 'remove/adjust anything except the steak', 'do not decrease the sourdough amount (126g)', and 'keep yogurt/granola and cereal', treat those as 100% locked constraints! Never lower total daily sourdough below 126g (you can split the 126g across Pre-Workout and Breakfast/Lunch), never change the locked steak amount, and keep his yogurt+granola and cereal bowl. Free up fats/carbs by removing or adjusting UNLOCKED items (like dropping butter or removing/reducing unlocked fruit/extras) so there is room for a real Dinner side with the steak!\n"
        "   - TOP-TIER PRE-WORKOUT MEALS: When Aaron asks for an early-morning Pre-Workout meal, create a `Pre-Workout` slot at the top using fast-digesting carbs + lean protein + minimal fat (e.g., part of his locked Sourdough Toast with Strawberry Jelly/Jam, Banana, or PBfit + Fairlife Milk / Whey / Greek Yogurt).\n"
        "   - DAILY SUPER LOW-CAL VEGGIE SNACKS (EVERY SINGLE DAY — NEVER SKIP): Aaron wants to incorporate his super low-calorie veggie options as snacks every single day — currently `Fresh Celery Sticks`, `Fresh Bagged Sugar Snap Peas`, and `Fresh Whole / Baby Carrots`. Whenever building a full-day plan, filling in the remaining day from a Cronometer screenshot (unless already logged on the screenshot), or suggesting `Snacks`, ALWAYS include at least one or a combination of `Fresh Celery Sticks`, `Fresh Bagged Sugar Snap Peas`, and `Fresh Whole / Baby Carrots` (in exact grams `Xg`) in his `Snacks` every single day!\n"
        "   - If he has calories/macros open and asks for options to fill a slot/day, make sure EVERY option you give is scaled so that choosing it actually hits his 170-185g P and ~1,900 kcal goals.\n"
        "4. DINNER PAIRING OPTIONS VS. SINGLE SWAP (NEVER REPEAT ASSUMED STEAK IN EVERY OPTION):\n"
        "   - ALWAYS respect Aaron's exact math (e.g., if he says 'I have 446g of steak, I'd like to split that for a meal', half of 446g is 223g pre-cooked / 167g cooked — NEVER make up 300g!).\n"
        "   - IF AARON ASKS TO SWAP A SIDE WHILE TUNING HIS DAY (e.g. 'also I want something else with dinner' without asking for multiple options): DO NOT output 5 Dinner options! Just replace the unwanted side (e.g. carrots) with 1 normal, appetizing side (like White Rice, Potatoes, or Beans) inside the single `Dinner` block and show 1 single `Daily Total:` at the bottom.\n"
        "   - IF AARON EXPLICITLY ASKS FOR 'options for with the steak': The steak is ALREADY ASSUMED — NEVER repeat the steak line inside every option! List the steak ONCE under `Dinner`, and then list ONLY the side dish under `Option 1..5` (with the side's `Total:` and resulting `Daily Total:`).\n"
        "5. NATURAL CONVERSATIONAL QUESTIONS, PROJECT COMMUNICATION & IDEA-DUMP MODE:\n"
        "   - You are a full conversational Gemini AI AND Aaron's direct bridge to this project (`diet-macro-assistant`): Aaron can ask you ANY random question, send screenshots of chats/apps/issues, discuss project behavior, or give instructions/rules/notes for this project.\n"
        "   - IDEA-DUMP & SAVE-TO-PROJECT-FILE RULE (CRITICAL): Whenever Aaron is purely dumping ideas, notes, or project requirements for when he gets back to his computer without asking a question, OR whenever he explicitly says he does NOT want the answer returned in the chat message (e.g. 'I don\\'t need this return to me in this message', 'save it as a project file'), reply ONLY `Okay.` (zero other words, never dump a long document in chat when he told you not to!).\n"
        "   - When he asks a 'why' or general question (including about a screenshot he sent), answer it directly in 1–2 ultra-short sentences with zero fluff.\n"
        "6. WIDE KITCHEN VARIETY & ZERO REPEATS:\n"
        "   - Actively use the full kitchen inventory! Draw from his frozen meats/shrimp/chicken strips/meatballs, rotisserie chicken, canned tuna/chicken, edamame, protein bars, beef sticks, cheeses, breads, bagels, tortillas, beans, rices, pastas, fruits, and snacks.\n"
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
        "   - Always tell ready-to-drink protein shakes as whole shakes/bottles with grams in parentheses (never raw '341g Premier Protein'):\n"
        "     * `- 1 shake (341g) Premier Protein 30g Chocolate Protein Shakes`\n"
        "     * `- 1 shake (340g) Fairlife Nutrition Plan 30g Chocolate Protein Shakes`\n"
        "4. STEAK & RAW MEATS -> ALWAYS GIVE BOTH PRE-COOKED AND COOKED GRAMS:\n"
        "   - Raw meats (steak, ground beef, chicken thighs, chicken breast, shrimp) lose ~25% moisture when cooked (`cooked_g = round(raw_g * 0.75)`).\n"
        "   - ALWAYS show BOTH pre-cooked and cooked grams on the ingredient line:\n"
        "     * `- 223g pre-cooked / 167g cooked Kirkland Signature USDA Prime Top Sirloin Steak (Boneless, Cap-Off)`\n"
        "     * `- 227g pre-cooked / 170g cooked Boneless Skinless Chicken Thighs`\n"
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

    # Keep inline_data images in the last 4 history entries so follow-up messages see the Cronometer screenshot without bloating payload size
    trimmed_history: List[Dict[str, Any]] = []
    recent_slice = list(history[-12:])
    for idx, turn in enumerate(recent_slice):
        if idx < len(recent_slice) - 4:
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
            "thinkingConfig": {"thinkingBudget": 2048},
        },
    }

    reply = call_gemini_generate(payload, timeout_sec=75)
    history.append({"role": "user", "parts": parts})
    history.append({"role": "model", "parts": [{"text": reply}]})

    s_lower = (user_text or "").strip().lower()
    if reply.strip() in ("Okay.", "Okay") or any(
        s_lower.startswith(p) for p in ("note:", "log:", "remember:", "rule:", "add rule", "save note")
    ):
        if user_text and user_text.strip():
            append_project_note(user_text.strip())

    return reply


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
        # Rule 2g: If image/screenshot is sent with no text, save image(s) in memory and ask for context
        if photos and not combined_text:
            if chat_id not in CHAT_MEMORY:
                CHAT_MEMORY[chat_id] = []
            img_parts: List[Dict[str, Any]] = []
            for img_path in photos:
                if img_path and os.path.exists(img_path):
                    with open(img_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    img_parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
            img_parts.append({"text": "[User uploaded screenshot(s) without text]"})
            CHAT_MEMORY[chat_id].append({"role": "user", "parts": img_parts})
            CHAT_MEMORY[chat_id].append({"role": "model", "parts": [{"text": "I need more context."}]})
            send_message(token, chat_id, "I need more context.")
            return

        if photos and combined_text and is_photo_inventory_request(combined_text, has_photos=True):
            reply = process_inventory_photo(combined_text, chat_id, image_paths=photos)
            if reply:
                send_message(token, chat_id, reply)
                return

        # Explicit 'Idea dump' Trigger: When Aaron says 'Idea dump', log to cloud and reply with Okay + Update Summary
        s_lower = combined_text.strip().lower()
        if combined_text and 'idea dump' in s_lower:
            append_project_note(combined_text.strip())
            try:
                clean_content = re.sub(r'(?i)^idea\s*dump[:\s-]*', '', combined_text.strip()).strip()
                summary_prompt = f'Summarize this update in 1 simple sentence with zero fluff:\n{clean_content}'
                p_payload = {'contents': [{'role': 'user', 'parts': [{'text': summary_prompt}]}], 'generationConfig': {'temperature': 0.2, 'maxOutputTokens': 80}}
                brief_sum = call_gemini_generate(p_payload, timeout_sec=15).strip()
            except Exception:
                brief_sum = 'Logged idea dump to persistent project notes.'
            reply_text = f'Okay.\n\nUpdate Summary:\n{brief_sum}'
            if chat_id not in CHAT_MEMORY:
                CHAT_MEMORY[chat_id] = []
            CHAT_MEMORY[chat_id].append({'role': 'user', 'parts': [{'text': combined_text}]})
            CHAT_MEMORY[chat_id].append({'role': 'model', 'parts': [{'text': reply_text}]})
            send_message(token, chat_id, reply_text)
            return

        if not photos and combined_text:
            s = combined_text.strip()
            m_dis = re.search(r"^add\s+(.+?)\s+to\s+(?:my\s+)?(?:don'?t\s+like|dislike)\s*(?:list)?[.!]*$", s, re.I)
            if m_dis:
                send_message(token, chat_id, add_to_dislikes(m_dis.group(1).strip()))
                return

            m_like = re.search(r"^add\s+(.+?)\s+to\s+(?:my\s+)?like\s*(?:list)?[.!]*$", s, re.I)
            if m_like:
                send_message(token, chat_id, add_to_likes(m_like.group(1).strip()))
                return

            m_add_inv = re.search(r"^add\s+(.+?)\s+to\s+(?:my\s+)?inventory[.!]*$", s, re.I)
            if is_photo_inventory_request(s, has_photos=False) and (
                not m_add_inv or is_generic_photo_reference(m_add_inv.group(1))
            ):
                recent_b64s = get_recent_memory_images(chat_id)
                if recent_b64s:
                    reply = process_inventory_photo(s, chat_id, image_b64_list=recent_b64s)
                    send_message(token, chat_id, reply)
                    return

            if m_add_inv:
                send_message(token, chat_id, add_item_to_inventory(m_add_inv.group(1).strip()))
                return

            m_rem_exact = re.search(
                r"^(?:remove|delete|take\s+off)\s+(.+?)\s+from\s+(?:my\s+)?inventory[.!]*$", s, re.I
            )
            if m_rem_exact:
                send_message(token, chat_id, remove_item_from_inventory(m_rem_exact.group(1).strip(), chat_id=chat_id))
                return

            # Also support conversational removal inside a longer message (e.g. "I removed X from my inventory! ... return new plan")
            m_rem_conv = re.search(
                r"(?:i\s+removed|remove|delete)\s+([a-z0-9\s,'&-]+?)\s+from\s+(?:my\s+)?inventory", s, re.I
            )
            if m_rem_conv:
                remove_item_from_inventory(m_rem_conv.group(1).strip(), chat_id=chat_id)

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
        if self.path.startswith("/weightlifting-tracker-data.json") or self.path.startswith("/lifting-data.json"):
            body = lifting_agent.get_live_workout_json(get_gemini_key()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/weightlifting-tracker") or self.path.startswith("/lifting"):
            body = lifting_agent.get_dashboard_html(get_gemini_key()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - Diet Macro Assistant Bot is awake")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
        if self.path.startswith("/wabbits-webhook"):
            threading.Thread(
                target=wabbits_agent.process_wabbits_webhook,
                args=(get_gemini_key(), body),
                daemon=True,
            ).start()
            return
        if self.path.startswith("/weightlifting-tracker-webhook") or self.path.startswith("/lifting-webhook"):
            threading.Thread(
                target=lifting_agent.process_lifting_webhook,
                args=(get_gemini_key(), body),
                daemon=True,
            ).start()
            return
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

    # Sync persistent inventory overrides from Telegram cloud on boot
    try:
        load_all_context()
    except Exception:
        pass

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
        try:
            wabbits_agent.register_wabbits_webhook(get_gemini_key(), external_url)
        except Exception as e:
            print(f"Wabbits webhook setup failed ({e})")
        try:
            lifting_agent.register_lifting_webhook(get_gemini_key(), external_url)
        except Exception as e:
            print(f"Lifting webhook setup failed ({e})")

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
