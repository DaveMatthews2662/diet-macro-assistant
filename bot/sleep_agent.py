import base64
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os
import re
import ssl
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Dict, List, Any, Optional

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_FILE = os.path.join(BOT_DIR, "sleep_vault.json")

SSL_CTX = ssl.create_default_context()
SSL_UNVERIFIED_CTX = ssl._create_unverified_context()

SLEEP_MEMORY: Dict[int, List[Dict[str, Any]]] = {}
SLEEP_BATCH_LOCK = threading.Lock()
SLEEP_BATCH: Dict[int, Dict[str, Any]] = {}
SLEEP_BATCH_DELAY = 2.0

SLEEP_CLOUD_DONE = False
SLEEP_CLOUD_LOCK = threading.Lock()
SLEEP_STATE_CACHE: Dict[str, Any] = {
    "medication_logs": [],
    "notes": [],
    "rules": []
}
SLEEP_VAULT_CACHE: Dict[str, Any] = {}
SLEEP_SEEN_UPDATES = set()


def _open_url(req, timeout: int = 25):
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX)
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            return urllib.request.urlopen(req, timeout=timeout, context=SSL_UNVERIFIED_CTX)
        raise


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def load_vault(gemini_key: str) -> Dict[str, Any]:
    global SLEEP_VAULT_CACHE
    if SLEEP_VAULT_CACHE:
        return SLEEP_VAULT_CACHE
    if not gemini_key or not os.path.exists(VAULT_FILE):
        return {}
    try:
        with open(VAULT_FILE, "r", encoding="utf-8") as f:
            enc = json.load(f)
        salt = base64.b64decode(enc["salt"])
        nonce = base64.b64decode(enc["nonce"])
        ct = base64.b64decode(enc["ct"])
        tag = base64.b64decode(enc["tag"])
        derived = hashlib.pbkdf2_hmac("sha256", gemini_key.encode("utf-8"), salt, 100000, dklen=64)
        enc_key, mac_key = derived[:32], derived[32:]
        expected_tag = hmac.new(mac_key, salt + nonce + ct, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            print("[sleep] Vault HMAC mismatch!", flush=True)
            return {}
        stream = _keystream(enc_key, nonce, len(ct))
        pt = bytes(a ^ b for a, b in zip(ct, stream))
        SLEEP_VAULT_CACHE = json.loads(pt.decode("utf-8"))
        return SLEEP_VAULT_CACHE
    except Exception as e:
        print(f"[sleep] Vault load failed: {e}", flush=True)
        return {}


def get_sleep_token(gemini_key: str) -> str:
    env_tok = os.environ.get("SLEEP_BOT_TOKEN", "").strip()
    if env_tok:
        return env_tok
    vault = load_vault(gemini_key)
    return str(vault.get("token", "")).strip()


def tg_api(token: str, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with _open_url(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_message(token: str, chat_id: int, text: str):
    chunks = [text[i : i + 3900] for i in range(0, len(text), 3900)] or [text]
    for chunk in chunks:
        tg_api(token, "sendMessage", {"chat_id": chat_id, "text": chunk})


def save_state_to_cloud(token: str, data: Dict[str, Any]):
    if not token:
        return
    try:
        raw_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")
        b64_str = base64.b64encode(raw_bytes).decode("ascii")
        chunks = [b64_str[i : i + 240] for i in range(0, len(b64_str), 240)][:95]
        commands = [{"command": f"s{idx}", "description": ch} for idx, ch in enumerate(chunks)]
        tg_api(
            token,
            "setMyCommands",
            {
                "commands": commands,
                "scope": {"type": "all_chat_administrators"},
                "language_code": "eo",
            },
        )
    except Exception as e:
        print(f"[sleep] Cloud save failed: {e}", flush=True)


def sync_state_from_cloud(token: str) -> Dict[str, Any]:
    global SLEEP_CLOUD_DONE, SLEEP_STATE_CACHE
    if SLEEP_CLOUD_DONE:
        return SLEEP_STATE_CACHE
    with SLEEP_CLOUD_LOCK:
        if SLEEP_CLOUD_DONE:
            return SLEEP_STATE_CACHE
        if not token:
            SLEEP_CLOUD_DONE = True
            return SLEEP_STATE_CACHE
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
            if cmds and isinstance(cmds, list):
                sorted_cmds = sorted(
                    [c for c in cmds if str(c.get("command", "")).startswith("s")],
                    key=lambda x: int(str(x["command"])[1:] or "0"),
                )
                b64_str = "".join(str(c.get("description", "")) for c in sorted_cmds)
                if b64_str:
                    cloud_data = json.loads(base64.b64decode(b64_str.encode("ascii")).decode("utf-8"))
                    if isinstance(cloud_data, dict):
                        SLEEP_STATE_CACHE = {
                            "medication_logs": list(cloud_data.get("medication_logs", [])),
                            "notes": list(cloud_data.get("notes", [])),
                            "rules": list(cloud_data.get("rules", [])),
                        }
        except Exception as e:
            print(f"[sleep] Cloud sync warning: {e}", flush=True)
        SLEEP_CLOUD_DONE = True
    return SLEEP_STATE_CACHE


def strip_markdown_asterisks(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    lines = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("* "):
            line = line.replace("* ", "- ", 1)
        lines.append(line)
    return "\n".join(lines)


def parse_and_record_dose(text: str, gemini_key: str, token: str) -> Optional[str]:
    text_clean = text.strip()
    text_lower = text_clean.lower()

    time_match = re.search(r"(\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b)", text_clean, re.IGNORECASE)
    time_taken_str = "9:00 PM"
    if time_match:
        t_raw = time_match.group(1).strip()
        if "am" in t_raw.lower() or "pm" in t_raw.lower():
            time_taken_str = t_raw.upper()
        else:
            time_taken_str = f"{t_raw} PM"

    traz_mg = None
    quet_mg = None

    if "repeat" in text_lower or "same" in text_lower:
        state = sync_state_from_cloud(token)
        vault = load_vault(gemini_key)
        files = vault.get("files", {})
        all_logs = []
        try:
            base_logs = json.loads(files.get("data/medication_logs.json", "[]"))
            all_logs.extend(base_logs)
        except Exception:
            pass
        all_logs.extend(state.get("medication_logs", []))
        if all_logs:
            last = all_logs[-1]
            traz_mg = last.get("trazodone_mg", 100)
            quet_mg = last.get("quetiapine_mg", 50)
        else:
            traz_mg = 100
            quet_mg = 50

    if traz_mg is None:
        t_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mg)?\s*(?:traz|trazodone|t\b)", text_lower)
        if t_m:
            traz_mg = int(float(t_m.group(1)))

    if quet_mg is None:
        q_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mg)?\s*(?:quet|quetiapine|seroquel|q\b)", text_lower)
        if q_m:
            quet_mg = int(float(q_m.group(1)))

    if traz_mg is None and quet_mg is None:
        # Check standard format e.g. 100 / 50 or 100 / 100
        split_m = re.search(r"\b(\d{2,3})\s*/\s*(\d{2,3})\b", text_lower)
        if split_m:
            traz_mg = int(split_m.group(1))
            quet_mg = int(split_m.group(2))

    if traz_mg is None and quet_mg is None:
        return None

    traz_val = f"{traz_mg}mg" if traz_mg is not None else "0mg"
    quet_val = f"{quet_mg}mg" if quet_mg is not None else "0mg"

    today_dt = datetime.now()
    date_str = today_dt.strftime("%Y-%m-%d")

    # Persist into state cache & Telegram cloud storage
    state = sync_state_from_cloud(token)
    new_entry = {
        "date": date_str,
        "night_of": date_str,
        "trazodone_mg": traz_mg or 0,
        "quetiapine_mg": quet_mg or 0,
        "time_taken": time_taken_str,
        "notes": f"Logged via cloud webhook: {text_clean}"
    }
    state.setdefault("medication_logs", []).append(new_entry)
    save_state_to_cloud(token, state)

    return (
        f"Roger Roger\n"
        f"Trazadone Dosage: {traz_val}\n"
        f"Quetiapine Dosage: {quet_val}\n"
        f"Date: {date_str}\n"
        f"Time taken: {time_taken_str}"
    )


def build_context(gemini_key: str, token: str) -> str:
    vault = load_vault(gemini_key)
    files = dict(vault.get("files", {}))
    state = sync_state_from_cloud(token)

    sections = []
    for rel, content in files.items():
        if rel == "dashboard.html":
            continue
        sections.append(f"=== {rel} ===\n{content}")

    if state.get("medication_logs"):
        sections.append("=== Cloud Synced Recent Doses ===\n" + json.dumps(state.get("medication_logs"), indent=2))
    if state.get("notes"):
        sections.append("=== Cloud Synced Notes ===\n" + json.dumps(state.get("notes"), indent=2))

    return "\n\n".join(sections)


def call_gemini(gemini_key: str, prompt: str, system_inst: str) -> str:
    models = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
    payload = {
        "system_instruction": {"parts": [{"text": system_inst}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600}
    }
    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with _open_url(req, timeout=25) as resp:
                res = json.loads(resp.read().decode("utf-8"))
            parts = res.get("candidates", [])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if "text" in p)
            if text:
                return strip_markdown_asterisks(text)
        except Exception:
            continue
    return "Roger Roger. Processed your message."


def _handle_sleep_batch(gemini_key: str, token: str, chat_id: int):
    with SLEEP_BATCH_LOCK:
        item = SLEEP_BATCH.pop(chat_id, None)
    if not item:
        return

    text = item.get("text", "").strip()
    text_lower = text.lower()

    if text_lower in ["ok", "okay", "roger"]:
        send_message(token, chat_id, "Roger Roger.")
        return

    dose_reply = parse_and_record_dose(text, gemini_key, token)
    if dose_reply:
        send_message(token, chat_id, dose_reply)
        return

    if text_lower.startswith("idea dump") or "idea dump" in text_lower:
        state = sync_state_from_cloud(token)
        state.setdefault("notes", []).append({
            "timestamp": datetime.now().isoformat(),
            "note": text
        })
        save_state_to_cloud(token, state)
        send_message(token, chat_id, "Roger Roger.\n\nUpdate Summary:\n- Logged idea dump note to cloud memory.")
        return

    # Question or conversation turn
    system_inst = (
        "You are Aaron's personal Sleep Tracker AI Assistant. "
        "Strict rules:\n"
        "1. Be as short, direct, and scannable as humanly possible.\n"
        "2. Use brief bullet points with dashes (-). Zero fluff.\n"
        "3. NEVER use markdown asterisks (* or **). No bolding asterisks.\n"
        "4. Focus exclusively on sleep tracking, Trazodone & Quetiapine dosages, awakenings, and Oura biometrics.\n"
        "5. Affirmations are always 'Roger Roger.'\n\n"
        + build_context(gemini_key, token)
    )
    reply = call_gemini(gemini_key, text, system_inst)
    send_message(token, chat_id, reply)


def _enqueue_sleep(gemini_key: str, token: str, chat_id: int, text: str):
    with SLEEP_BATCH_LOCK:
        existing = SLEEP_BATCH.get(chat_id)
        if existing:
            combined = existing["text"] + "\n" + text if text else existing["text"]
            existing["text"] = combined
            if existing.get("timer"):
                existing["timer"].cancel()
        else:
            SLEEP_BATCH[chat_id] = {"text": text}

        timer = threading.Timer(SLEEP_BATCH_DELAY, _handle_sleep_batch, args=(gemini_key, token, chat_id))
        SLEEP_BATCH[chat_id]["timer"] = timer
        timer.daemon = True
        timer.start()


def process_sleep_webhook(gemini_key: str, body_bytes: bytes):
    token = get_sleep_token(gemini_key)
    if not token:
        return
    try:
        upd = json.loads(body_bytes.decode("utf-8"))
        uid = upd.get("update_id")
        if uid:
            if uid in SLEEP_SEEN_UPDATES:
                return
            SLEEP_SEEN_UPDATES.add(uid)
        if "message" in upd:
            msg = upd["message"]
            cid = msg["chat"]["id"]
            if "text" in msg:
                _enqueue_sleep(gemini_key, token, cid, text=msg["text"])
    except Exception as e:
        print(f"[sleep] Webhook error: {e}", flush=True)


def register_sleep_webhook(gemini_key: str, external_url: str):
    token = get_sleep_token(gemini_key)
    if not token or not external_url:
        return
    webhook_url = f"{external_url.rstrip('/')}/sleep-webhook"
    try:
        tg_api(token, "setWebhook", {"url": webhook_url})
        sync_state_from_cloud(token)
        print(f"[sleep] Webhook registered at {webhook_url}", flush=True)
    except Exception as e:
        print(f"[sleep] Webhook setup failed: {e}", flush=True)


def get_dashboard_html(gemini_key: str) -> str:
    vault = load_vault(gemini_key)
    files: Dict[str, str] = vault.get("files", {})
    return files.get("dashboard.html", "<h1>Sleep Dashboard not found in vault</h1>")


def get_live_sleep_json(gemini_key: str) -> str:
    vault = load_vault(gemini_key)
    token = get_sleep_token(gemini_key)
    files: Dict[str, str] = dict(vault.get("files", {}))
    state = sync_state_from_cloud(token)
    raw_meds = files.get("data/medication_logs.json", "[]")
    raw_oura = files.get("data/oura_cache.json", "{}")
    try:
        meds = json.loads(raw_meds)
        meds.extend(state.get("medication_logs", []))
        oura = json.loads(raw_oura)
        return json.dumps({"medication_logs": meds, "oura_cache": oura}, indent=2)
    except Exception:
        return raw_meds
