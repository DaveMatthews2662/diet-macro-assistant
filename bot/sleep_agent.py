import base64
from datetime import datetime, timedelta, timezone
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
import urllib.parse
import urllib.request
from typing import Dict, List, Any, Optional

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_FILE = os.path.join(BOT_DIR, "sleep_vault.json")

SSL_CTX = ssl.create_default_context()
SSL_UNVERIFIED_CTX = ssl._create_unverified_context()

CST = timezone(timedelta(hours=-6))

SLEEP_MEMORY: Dict[int, List[Dict[str, Any]]] = {}
SLEEP_BATCH_LOCK = threading.Lock()
SLEEP_BATCH: Dict[int, Dict[str, Any]] = {}
SLEEP_BATCH_DELAY = 2.0

SLEEP_CLOUD_DONE = False
SLEEP_CLOUD_LOCK = threading.Lock()
SLEEP_STATE_CACHE: Dict[str, Any] = {
    "medication_logs": [],
    "notes": [],
    "rules": [],
    "hunger_logs": {},
    "oura_tokens": {},
    "oura_cache": {},
}
SLEEP_VAULT_CACHE: Dict[str, Any] = {}
SLEEP_SEEN_UPDATES = set()
OURA_SYNC_RUNNING = False


def now_cst() -> datetime:
    return datetime.now(timezone.utc).astimezone(CST)


def format_seconds(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m:02d}m"


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
    # Keep setMyCommands compact & within Telegram's size limits by excluding large oura_cache (kept in RAM & vault)
    compact_data = {k: v for k, v in data.items() if k != "oura_cache"}
    raw_bytes = json.dumps(compact_data, separators=(",", ":")).encode("utf-8")
    b64_str = base64.b64encode(raw_bytes).decode("ascii")
    chunks = [b64_str[i : i + 240] for i in range(0, len(b64_str), 240)][:95]
    # Telegram BotCommand description must be 3-256 chars; pad short trailing chunks
    commands = [{"command": f"s{idx}", "description": ch.ljust(3)} for idx, ch in enumerate(chunks)]
    payload = {
        "commands": commands,
        "scope": {"type": "all_chat_administrators"},
        "language_code": "eo",
    }
    for attempt in range(2):
        try:
            tg_api(token, "setMyCommands", payload)
            return
        except Exception as e:
            print(f"[sleep] Cloud save attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(0.5)


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
                b64_str = "".join(str(c.get("description", "")).strip() for c in sorted_cmds)
                if b64_str:
                    cloud_data = json.loads(base64.b64decode(b64_str.encode("ascii")).decode("utf-8"))
                    if isinstance(cloud_data, dict):
                        SLEEP_STATE_CACHE = {
                            "medication_logs": list(cloud_data.get("medication_logs", [])),
                            "notes": list(cloud_data.get("notes", [])),
                            "rules": list(cloud_data.get("rules", [])),
                            "hunger_logs": dict(cloud_data.get("hunger_logs", {})),
                            "oura_tokens": dict(cloud_data.get("oura_tokens", {})),
                            "oura_cache": dict(cloud_data.get("oura_cache", {})),
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


def extract_time_taken(text: str, fallback_dt: datetime) -> str:
    """Extract time taken from messages like '9:20pm', '920pm', '1030pm', 'at 9', '9pm'."""
    def _format_hm(hour: int, minute: int, ampm_raw: Optional[str]) -> Optional[str]:
        if minute < 0 or minute > 59 or hour < 0 or hour > 23:
            return None
        if ampm_raw:
            ap = ampm_raw.upper()
            h12 = hour % 12 or 12
            return f"{h12}:{minute:02d} {ap}"
        if hour >= 13:
            h12 = hour - 12
            return f"{h12}:{minute:02d} PM"
        if hour == 0:
            return f"12:{minute:02d} AM"
        # No am/pm specified on 1-12 hour: sleep meds are almost always PM (except 12 -> AM/midnight or 1-4 AM)
        ap = "AM" if (hour == 12 or 1 <= hour <= 4) else "PM"
        return f"{hour}:{minute:02d} {ap}"

    # 1. Colon format: 9:20pm, 9:20 PM, 21:20, at 9:20
    m = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", text, re.IGNORECASE)
    if m:
        res = _format_hm(int(m.group(1)), int(m.group(2)), m.group(3))
        if res:
            return res

    # 2. Compact 3-4 digit time with am/pm OR preceded by at/@: 920pm, 1030pm, at 920, @ 844
    m = re.search(r"\b(\d{3,4})\s*(am|pm)\b", text, re.IGNORECASE)
    if not m:
        m = re.search(r"(?:at|@)\s*(\d{3,4})\b", text, re.IGNORECASE)
    if m:
        digits = m.group(1)
        ampm = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        h = int(digits[:-2])
        mins = int(digits[-2:])
        res = _format_hm(h, mins, ampm)
        if res:
            return res

    # 3. Hour-only with am/pm OR preceded by at/@: 9pm, at 9, @ 10
    m = re.search(r"\b(\d{1,2})\s*(am|pm)\b", text, re.IGNORECASE)
    if not m:
        m = re.search(r"(?:at|@)\s*(\d{1,2})\b", text, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        ampm = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        res = _format_hm(h, 0, ampm)
        if res:
            return res

    # Fallback to actual message timestamp instead of hardcoded 9:00 PM
    return fallback_dt.strftime("%I:%M %p").lstrip("0")


def parse_and_record_dose(text: str, gemini_key: str, token: str) -> Optional[str]:
    text_clean = text.strip()
    text_lower = text_clean.lower()

    now = now_cst()
    time_taken_str = extract_time_taken(text_clean, now)

    traz_mg = None
    quet_mg = None

    if "repeat" in text_lower or "same" in text_lower:
        state = sync_state_from_cloud(token)
        vault = load_vault(gemini_key)
        files = vault.get("files", {})
        all_logs = []
        try:
            base_logs = json.loads(files.get("data/medication_logs.json", "{}")).get("logs", [])
            all_logs.extend(base_logs)
        except Exception:
            pass
        all_logs.extend(state.get("medication_logs", []))
        if all_logs:
            last = all_logs[-1]
            traz_mg = last.get("trazodone_mg", 100)
            quet_mg = last.get("quetiapine_mg", 100)
        else:
            traz_mg = 100
            quet_mg = 100

    if traz_mg is None:
        t_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mg)?\s*(?:traz|trazodone|t\b)", text_lower)
        if t_m:
            traz_mg = int(float(t_m.group(1)))

    if quet_mg is None:
        q_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mg)?\s*(?:quet|quetiapine|seroquel|q\b)", text_lower)
        if q_m:
            quet_mg = int(float(q_m.group(1)))

    if traz_mg is None and quet_mg is None:
        split_m = re.search(r"\b(\d{2,3})\s*/\s*(\d{2,3})\b", text_lower)
        if split_m:
            traz_mg = int(split_m.group(1))
            quet_mg = int(split_m.group(2))

    if traz_mg is None and quet_mg is None:
        return None

    traz_val = f"{traz_mg}mg" if traz_mg is not None else "0mg"
    quet_val = f"{quet_mg}mg" if quet_mg is not None else "0mg"

    # Dose logged at night belongs to tonight (night_of = now, date = next morning)
    night_of_str = now.strftime("%Y-%m-%d")
    date_str = (now + timedelta(days=1)).strftime("%Y-%m-%d") if now.hour >= 16 else now.strftime("%Y-%m-%d")

    state = sync_state_from_cloud(token)
    new_entry = {
        "date": date_str,
        "night_of": night_of_str,
        "trazodone_mg": traz_mg or 0,
        "quetiapine_mg": quet_mg or 0,
        "time_taken": time_taken_str,
        "notes": f"Logged via cloud webhook: {text_clean}"
    }
    med_logs = state.setdefault("medication_logs", [])
    replaced = False
    for i, existing in enumerate(med_logs):
        if existing.get("night_of") == night_of_str or existing.get("date") == date_str:
            med_logs[i] = new_entry
            replaced = True
            break
    if not replaced:
        med_logs.append(new_entry)
    save_state_to_cloud(token, state)

    return (
        f"Roger Roger\n"
        f"Trazadone Dosage: {traz_val}\n"
        f"Quetiapine Dosage: {quet_val}\n"
        f"Date: {night_of_str}\n"
        f"Time taken: {time_taken_str}"
    )


def sync_oura_cloud(gemini_key: str, token: str) -> str:
    """Syncs Oura Ring data directly from Render cloud, auto-refreshing OAuth tokens."""
    global OURA_SYNC_RUNNING
    if OURA_SYNC_RUNNING:
        return "Oura sync is already running in background."
    OURA_SYNC_RUNNING = True
    try:
        vault = load_vault(gemini_key)
        files = vault.get("files", {})
        state = sync_state_from_cloud(token)

        cred_raw = files.get("bot/.oura_credentials.json", "{}")
        tokens_raw = files.get("bot/.oura_tokens.json", "{}")
        try:
            credentials = json.loads(cred_raw)
        except Exception:
            credentials = {}
        try:
            tokens = state.get("oura_tokens") or json.loads(tokens_raw)
        except Exception:
            tokens = {}

        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_at = tokens.get("expires_at", 0)

        if not client_id or not client_secret or not refresh_token:
            return "Oura sync skipped: OAuth credentials not available in vault."

        now_ts = int(time.time())
        if now_ts >= (expires_at - 300) or not access_token:
            try:
                refresh_data = urllib.parse.urlencode({
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                }).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.ouraring.com/oauth/token",
                    data=refresh_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                with _open_url(req, timeout=20) as resp:
                    new_tokens = json.loads(resp.read().decode("utf-8"))
                access_token = new_tokens.get("access_token")
                refresh_token = new_tokens.get("refresh_token", refresh_token)
                expires_in = new_tokens.get("expires_in", 2592000)
                tokens = {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_in": expires_in,
                    "expires_at": int(time.time()) + expires_in,
                    "created_at": datetime.now().isoformat()
                }
                state["oura_tokens"] = tokens
                save_state_to_cloud(token, state)
            except Exception as e:
                return f"Failed to refresh Oura token: {e}"

        # Fetch daily sleep, readiness, and sleep sessions for last 7 days
        end_dt = now_cst() + timedelta(days=1)
        start_dt = end_dt - timedelta(days=8)
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d")

        headers = {"Authorization": f"Bearer {access_token}"}

        req1 = urllib.request.Request(f"https://api.ouraring.com/v2/usercollection/daily_sleep?start_date={start_str}&end_date={end_str}", headers=headers)
        with _open_url(req1, timeout=20) as r:
            sleep_docs = json.loads(r.read().decode("utf-8")).get("data", [])

        req2 = urllib.request.Request(f"https://api.ouraring.com/v2/usercollection/daily_readiness?start_date={start_str}&end_date={end_str}", headers=headers)
        with _open_url(req2, timeout=20) as r:
            readiness_docs = json.loads(r.read().decode("utf-8")).get("data", [])

        req3 = urllib.request.Request(f"https://api.ouraring.com/v2/usercollection/sleep?start_date={start_str}&end_date={end_str}", headers=headers)
        with _open_url(req3, timeout=20) as r:
            session_docs = json.loads(r.read().decode("utf-8")).get("data", [])

        cache = {}
        raw_cache = state.get("oura_cache") or files.get("data/oura_cache.json", "{}")
        try:
            cache = json.loads(raw_cache).get("daily_records", {}) if isinstance(raw_cache, str) else raw_cache.get("daily_records", {})
        except Exception:
            cache = {}

        for item in sleep_docs:
            day = item.get("day")
            if day:
                entry = cache.setdefault(day, {"date": day})
                entry["sleep_score"] = item.get("score")
                entry["sleep_contributors"] = item.get("contributors", {})

        for item in readiness_docs:
            day = item.get("day")
            if day:
                entry = cache.setdefault(day, {"date": day})
                entry["readiness_score"] = item.get("score")
                entry["readiness_contributors"] = item.get("contributors", {})
                if "resting_heart_rate" in item.get("contributors", {}):
                    entry["resting_heart_rate"] = item["contributors"]["resting_heart_rate"]

        for session in session_docs:
            day = session.get("day")
            if not day:
                continue
            entry = cache.setdefault(day, {"date": day})
            dur = session.get("total_sleep_duration", 0)
            if dur >= entry.get("total_sleep_seconds", 0):
                entry["total_sleep_seconds"] = dur
                entry["total_sleep_formatted"] = format_seconds(dur)
                deep = session.get("deep_sleep_duration", 0)
                entry["deep_sleep_seconds"] = deep
                entry["deep_sleep_formatted"] = format_seconds(deep)
                entry["deep_sleep_pct"] = round((deep / dur * 100), 1) if dur > 0 else 0
                rem = session.get("rem_sleep_duration", 0)
                entry["rem_sleep_seconds"] = rem
                entry["rem_sleep_formatted"] = format_seconds(rem)
                entry["rem_sleep_pct"] = round((rem / dur * 100), 1) if dur > 0 else 0
                awake = session.get("awake_time", 0)
                entry["awake_seconds"] = awake
                entry["awake_formatted"] = format_seconds(awake)
                entry["awake_mins"] = round(awake / 60) if awake else 0

                phases_5m = session.get("sleep_phase_5_min", "")
                if phases_5m:
                    mid_5m = phases_5m.lstrip("4").rstrip("4")
                    entry["wakeups"] = len(re.findall(r"4+", mid_5m))
                else:
                    entry["wakeups"] = entry.get("wakeups", 0)

                entry["sleep_efficiency"] = session.get("efficiency", 0)
                entry["lowest_heart_rate"] = session.get("lowest_heart_rate")
                entry["average_heart_rate"] = round(session.get("average_heart_rate", 0)) if session.get("average_heart_rate") else None
                entry["average_hrv"] = session.get("average_hrv")
                entry["bedtime_start"] = session.get("bedtime_start")
                entry["bedtime_end"] = session.get("bedtime_end")
                lat_sec = session.get("latency")
                if lat_sec is not None:
                    entry["latency_seconds"] = lat_sec
                    entry["latency_mins"] = round(lat_sec / 60)

        state["oura_cache"] = {"last_synced": now_cst().isoformat(), "daily_records": cache}
        save_state_to_cloud(token, state)
        latest_day = sorted(cache.keys())[-1] if cache else "—"
        latest_rec = cache.get(latest_day, {})
        return (
            f"Roger Roger.\n\n"
            f"Oura Ring Sync Complete ({len(cache)} days in cache).\n"
            f"Latest Night: {latest_day}\n"
            f"- Sleep Score: {latest_rec.get('sleep_score', '—')}\n"
            f"- Readiness: {latest_rec.get('readiness_score', '—')}\n"
            f"- Wakeups: {latest_rec.get('wakeups', '—')}\n"
            f"- Duration: {latest_rec.get('total_sleep_formatted', '—')}\n"
            f"- Deep: {latest_rec.get('deep_sleep_pct', '—')}%\n"
            f"- Avg HRV: {latest_rec.get('average_hrv', '—')} ms"
        )
    except Exception as e:
        return f"Oura sync failed: {e}"
    finally:
        OURA_SYNC_RUNNING = False


def _auto_sync_loop(gemini_key: str, token: str):
    """Background loop: automatically syncs fresh Oura records during morning hours."""
    time.sleep(30)
    while True:
        try:
            now = now_cst()
            # If morning (5:30 AM to 10:30 AM CST), check if today's record exists in cache
            if 5 <= now.hour <= 10:
                state = sync_state_from_cloud(token)
                today_str = now.strftime("%Y-%m-%d")
                cache = (state.get("oura_cache") or {}).get("daily_records", {})
                if today_str not in cache or not cache[today_str].get("total_sleep_seconds"):
                    print(f"[sleep-cron] Auto-syncing Oura for morning {today_str}...", flush=True)
                    sync_oura_cloud(gemini_key, token)
        except Exception as e:
            print(f"[sleep-cron] Auto sync error: {e}", flush=True)
        time.sleep(1800)  # Check every 30 minutes


def build_context(gemini_key: str, token: str) -> str:
    vault = load_vault(gemini_key)
    files = dict(vault.get("files", {}))
    state = sync_state_from_cloud(token)

    sections = []
    for rel, content in files.items():
        if rel in ["dashboard.html", "bot/.oura_credentials.json", "bot/.oura_tokens.json"]:
            continue
        sections.append(f"=== {rel} ===\n{content}")

    if state.get("medication_logs"):
        sections.append("=== Cloud Synced Recent Doses ===\n" + json.dumps(state.get("medication_logs"), indent=2))
    if state.get("notes"):
        sections.append("=== Cloud Synced Notes ===\n" + json.dumps(state.get("notes"), indent=2))
    if state.get("hunger_logs"):
        sections.append("=== Cloud Synced Night Hunger ===\n" + json.dumps(state.get("hunger_logs"), indent=2))

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


def _parse_ampm_minutes(t_str: str) -> Optional[int]:
    if not t_str or t_str == "—":
        return None
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*(AM|PM)?\s*$", t_str, re.IGNORECASE)
    if not m:
        return None
    h = int(m.group(1))
    mins = int(m.group(2))
    ap = m.group(3).upper() if m.group(3) else None
    if ap == "PM" and h != 12:
        h += 12
    elif ap == "AM" and h == 12:
        h = 0
    return h * 60 + mins


def _calc_med_to_sleep_str(med_time_str: str, sleep_time_str: str) -> str:
    m1 = _parse_ampm_minutes(med_time_str)
    m2 = _parse_ampm_minutes(sleep_time_str)
    if m1 is None or m2 is None:
        return "—"
    if m1 < 720:
        m1 += 1440
    if m2 < 720:
        m2 += 1440
    diff = m2 - m1
    if diff < 0 or diff > 720:
        return "—"
    if diff >= 60:
        return f"{diff // 60}h {diff % 60:02d}m"
    return f"{diff}m"


def _calc_custom_scores_py(oura: Dict[str, Any], hunger_val: Optional[str]) -> Dict[str, Optional[int]]:
    if not oura:
        return {"continuity": None, "restoration": None, "balanced": None}
    wakeups = oura.get("wakeups") if oura.get("wakeups") is not None else 0
    awake_mins = oura.get("awake_mins") if oura.get("awake_mins") is not None else 0
    latency = oura.get("latency_mins") if oura.get("latency_mins") is not None else 10
    restfulness = (oura.get("sleep_contributors") or {}).get("restfulness")
    if restfulness is None:
        restfulness = oura.get("restfulness")

    cont = 100 - (wakeups * 8) - max(0, awake_mins - 20) * 0.5 - max(0, latency - 10) * 0.5
    if restfulness is not None:
        cont += (restfulness - 70) * 0.3

    deep_pct = round(oura.get("deep_sleep_pct") or 0)
    rem_pct = round(oura.get("rem_sleep_pct") or 0)
    hrv = oura.get("average_hrv") if oura.get("average_hrv") is not None else 50
    low_hr = oura.get("lowest_heart_rate") if oura.get("lowest_heart_rate") is not None else 50
    rest = (
        min(30, (deep_pct / 20) * 30)
        + min(25, (rem_pct / 20) * 25)
        + min(25, (hrv / 80) * 25)
        + max(0, min(20, 20 - max(0, low_hr - 44) * 1.1))
    )

    eff = oura.get("sleep_efficiency") if oura.get("sleep_efficiency") is not None else 85
    tot_hrs = round((oura.get("total_sleep_seconds") or 0) / 3600, 1)
    bal = (
        min(30, (eff / 92) * 30)
        + min(25, (tot_hrs / 8.0) * 25)
        + max(0, 25 - (wakeups * 2.8) - max(0, awake_mins - 25) * 0.25)
        + min(20, (hrv / 75) * 20)
    )

    if hunger_val:
        hl = hunger_val.lower()
        if hl == "high":
            cont -= 15
            bal -= 10
        elif hl in ("medium", "med"):
            cont -= 8
            bal -= 5
        elif hl == "low":
            cont -= 3
            bal -= 2

    return {
        "continuity": max(0, min(100, round(cont))),
        "restoration": max(0, min(100, round(rest))),
        "balanced": max(0, min(100, round(bal))),
    }


def format_sleep_status_reply(text: str, gemini_key: str, token: str) -> Optional[str]:
    """Handle /sleep, /lastnight, 'sleep status', 'last night', or '/sleep MM-DD' queries."""
    t_clean = text.strip()
    t_low = t_clean.lower()

    is_cmd = bool(re.match(r"^/(?:sleep|lastnight|status)\b", t_low))
    is_phrase = bool(
        re.match(r"^(?:sleep\s*status|last\s*night(?:\s+sleep)?|how\s+did\s+i\s+sleep(?:\s+(?:last\s+night|on\s+.+))?|sleep\s+report|status(?:\s+[\d/\-]+)?)$", t_low)
    )
    if not (is_cmd or is_phrase):
        return None

    now = now_cst()
    target_night_of = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    m_iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t_clean)
    m_md = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", t_clean)
    if m_iso:
        target_night_of = m_iso.group(1)
    elif m_md:
        mo, dy = int(m_md.group(1)), int(m_md.group(2))
        yr_raw = m_md.group(3)
        yr = int(yr_raw) + 2000 if (yr_raw and len(yr_raw) == 2) else (int(yr_raw) if yr_raw else now.year)
        try:
            cand = datetime(yr, mo, dy)
            if not yr_raw and cand.date() > now.date():
                cand = datetime(yr - 1, mo, dy)
            target_night_of = cand.strftime("%Y-%m-%d")
        except ValueError:
            pass

    try:
        wakeup_date = (datetime.strptime(target_night_of, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    except ValueError:
        return "Roger Roger.\n\nInvalid date format. Try /sleep or /sleep 11-12."

    vault = load_vault(gemini_key)
    files = vault.get("files", {})
    state = sync_state_from_cloud(token)

    def _collect_records():
        recs = {}
        try:
            recs.update(json.loads(files.get("data/oura_cache.json", "{}")).get("daily_records", {}))
        except Exception:
            pass
        recs.update((state.get("oura_cache") or {}).get("daily_records", {}))
        return recs

    daily_records = _collect_records()
    if wakeup_date not in daily_records and wakeup_date == now.strftime("%Y-%m-%d"):
        sync_oura_cloud(gemini_key, token)
        state = sync_state_from_cloud(token)
        daily_records = _collect_records()

    oura = daily_records.get(wakeup_date)

    # Merge medication logs
    med_by_night = {}
    try:
        for log in json.loads(files.get("data/medication_logs.json", "{}")).get("logs", []):
            if log.get("night_of"):
                med_by_night[log["night_of"]] = dict(log)
    except Exception:
        pass
    for log in state.get("medication_logs", []):
        if log.get("night_of"):
            med_by_night[log["night_of"]] = dict(log)

    med = med_by_night.get(target_night_of, {})
    hunger = (state.get("hunger_logs") or {}).get(target_night_of) or med.get("hunger_level") or "—"
    alcohol = (state.get("alcohol_logs") or {}).get(target_night_of) or med.get("alcohol") or "—"
    nicotine = (state.get("nicotine_logs") or {}).get(target_night_of) or med.get("nicotine") or "—"

    if not oura and not med:
        return f"Roger Roger.\n\nNo sleep or medication data found for night of {target_night_of}."

    def _fmt_iso(iso_s: Optional[str]) -> str:
        if not iso_s:
            return "—"
        try:
            return datetime.fromisoformat(iso_s).strftime("%I:%M %p").lstrip("0")
        except Exception:
            return "—"

    med_time = med.get("time_taken", "—")
    traz = f"{med.get('trazodone_mg')}mg" if med.get("trazodone_mg") is not None else "—"
    quet = f"{med.get('quetiapine_mg')}mg" if med.get("quetiapine_mg") is not None else "—"

    if not oura:
        return (
            f"Roger Roger.\n\n"
            f"Sleep Status — Night of {target_night_of} (Oura Pending)\n"
            f"- Meds: Traz {traz} / Quet {quet} @ {med_time}\n"
            f"- Hunger: {hunger} | Alcohol: {alcohol} | Nicotine: {nicotine}\n"
            f"- Oura data for {wakeup_date} is not synced yet."
        )

    b_start = oura.get("bedtime_start")
    b_end = oura.get("bedtime_end")
    lat_sec = oura.get("latency_seconds")
    lat_mins = oura.get("latency_mins")
    if lat_sec is None and lat_mins is not None:
        lat_sec = lat_mins * 60
    elif lat_sec is None:
        lat_sec = 0
        lat_mins = 0
    if lat_mins is None:
        lat_mins = round(lat_sec / 60)

    bedtime_str = _fmt_iso(b_start)
    wake_str = _fmt_iso(b_end)
    sleep_time_str = "—"
    if b_start:
        try:
            sleep_dt = datetime.fromisoformat(b_start) + timedelta(seconds=lat_sec)
            sleep_time_str = sleep_dt.strftime("%I:%M %p").lstrip("0")
        except Exception:
            pass

    med_to_sleep = _calc_med_to_sleep_str(med_time, sleep_time_str)
    custom = _calc_custom_scores_py(oura, None if hunger == "—" else hunger)
    restfulness = (oura.get("sleep_contributors") or {}).get("restfulness")
    if restfulness is None:
        restfulness = oura.get("restfulness", "—")

    return (
        f"Roger Roger.\n\n"
        f"Sleep Status — Night of {target_night_of} (Wake {wakeup_date})\n"
        f"- Scores: Sleep {oura.get('sleep_score', '—')} | Continuity {custom['continuity'] if custom['continuity'] is not None else '—'} | Restoration {custom['restoration'] if custom['restoration'] is not None else '—'} | Balanced {custom['balanced'] if custom['balanced'] is not None else '—'}\n"
        f"- Restfulness: {restfulness} | Efficiency: {oura.get('sleep_efficiency', '—')}%\n"
        f"- Sleep: {oura.get('total_sleep_formatted', '—')} | Wakeups: {oura.get('wakeups', '—')} | Awake: {oura.get('awake_mins', '—')}m\n"
        f"- Timing: Med {med_time} -> Bed {bedtime_str} -> Asleep {sleep_time_str} -> Wake {wake_str}\n"
        f"- Latency: {lat_mins}m | Med-to-Sleep: {med_to_sleep}\n"
        f"- Recovery: Deep {round(oura.get('deep_sleep_pct') or 0)}% | REM {round(oura.get('rem_sleep_pct') or 0)}% | Avg HR {oura.get('average_heart_rate', '—')} | Low HR {oura.get('lowest_heart_rate', '—')} | HRV {oura.get('average_hrv', '—')}ms\n"
        f"- Inputs: Traz {traz} / Quet {quet} | Hunger: {hunger} | Alcohol: {alcohol} | Nicotine: {nicotine}"
    )


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

    if text_lower in ["/sync", "sync", "sync oura", "/sync oura"]:
        send_message(token, chat_id, "Syncing with Oura Ring...")
        reply = sync_oura_cloud(gemini_key, token)
        send_message(token, chat_id, reply)
        return

    status_reply = format_sleep_status_reply(text, gemini_key, token)
    if status_reply:
        send_message(token, chat_id, status_reply)
        return

    dose_reply = parse_and_record_dose(text, gemini_key, token)
    if dose_reply:
        send_message(token, chat_id, dose_reply)
        return

    if text_lower.startswith("idea dump") or "idea dump" in text_lower:
        state = sync_state_from_cloud(token)
        state.setdefault("notes", []).append({
            "timestamp": now_cst().isoformat(),
            "note": text
        })
        save_state_to_cloud(token, state)
        send_message(token, chat_id, "Roger Roger.\n\nUpdate Summary:\n- Logged idea dump note to cloud memory.")
        return

    if "hunger" in text_lower or "alcohol" in text_lower or "nicotine" in text_lower:
        state = sync_state_from_cloud(token)
        now = now_cst()
        night_of_key = (now - timedelta(days=1)).strftime("%Y-%m-%d") if now.hour < 14 else now.strftime("%Y-%m-%d")
        logged_msgs = []

        if "hunger" in text_lower:
            level = "None"
            if "high" in text_lower:
                level = "High"
            elif "med" in text_lower:
                level = "Medium"
            elif "low" in text_lower:
                level = "Low"
            elif "none" in text_lower or "non" in text_lower or "zero" in text_lower or "no hunger" in text_lower:
                level = "None"
            state.setdefault("hunger_logs", {})[night_of_key] = level
            logged_msgs.append(f"Logged Night Hunger: {level}")

        if "alcohol" in text_lower:
            alc_val = "No" if re.search(r"\b(?:no|none|0|false)\b", text_lower) else "Yes"
            state.setdefault("alcohol_logs", {})[night_of_key] = alc_val
            logged_msgs.append(f"Logged Alcohol ({night_of_key}): {alc_val}")

        if "nicotine" in text_lower:
            if "unknown" in text_lower:
                nic_val = "Unknown"
            elif re.search(r"\b(?:no|none|0|false)\b", text_lower):
                nic_val = "No"
            else:
                nic_val = "Yes"
            state.setdefault("nicotine_logs", {})[night_of_key] = nic_val
            logged_msgs.append(f"Logged Nicotine ({night_of_key}): {nic_val}")

        save_state_to_cloud(token, state)
        send_message(token, chat_id, "Roger Roger.\n\n" + "\n".join(logged_msgs))
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
        # Start morning auto-sync background thread
        t = threading.Thread(target=_auto_sync_loop, args=(gemini_key, token), daemon=True)
        t.start()
    except Exception as e:
        print(f"[sleep] Webhook setup failed: {e}", flush=True)


def get_dashboard_html(gemini_key: str) -> str:
    vault = load_vault(gemini_key)
    token = get_sleep_token(gemini_key)
    state = sync_state_from_cloud(token)
    files: Dict[str, str] = vault.get("files", {})
    html = files.get("dashboard.html", "<h1>Sleep Dashboard not found in vault</h1>")
    hunger_map = state.get("hunger_logs", {})
    alcohol_map = state.get("alcohol_logs", {})
    nicotine_map = state.get("nicotine_logs", {})
    inject_parts = []
    if hunger_map:
        inject_parts.append(f"const CLOUD_HUNGER = {json.dumps(hunger_map)};")
    if alcohol_map:
        inject_parts.append(f"const CLOUD_ALCOHOL = {json.dumps(alcohol_map)};")
    if nicotine_map:
        inject_parts.append(f"const CLOUD_NICOTINE = {json.dumps(nicotine_map)};")
    if state.get("medication_logs"):
        inject_parts.append(f"const CLOUD_DOSES = {json.dumps(state['medication_logs'])};")
    if state.get("oura_cache"):
        inject_parts.append(f"const CLOUD_OURA = {json.dumps(state['oura_cache'])};")
    if inject_parts:
        inject_js = "<script>" + " ".join(inject_parts) + "</script>"
        html = html.replace("<script>", f"{inject_js}\n  <script>", 1)
    return html


def get_live_sleep_json(gemini_key: str) -> str:
    vault = load_vault(gemini_key)
    token = get_sleep_token(gemini_key)
    files: Dict[str, str] = dict(vault.get("files", {}))
    state = sync_state_from_cloud(token)
    raw_meds = files.get("data/medication_logs.json", "[]")
    raw_oura = files.get("data/oura_cache.json", "{}")
    try:
        med_dict = json.loads(raw_meds)
        meds = med_dict.get("logs", []) if isinstance(med_dict, dict) else med_dict
        meds.extend(state.get("medication_logs", []))
        oura = state.get("oura_cache") or json.loads(raw_oura)
        return json.dumps({"medication_logs": meds, "oura_cache": oura, "hunger_logs": state.get("hunger_logs", {})}, indent=2)
    except Exception:
        return raw_meds
