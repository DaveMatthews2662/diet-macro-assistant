import base64
from datetime import datetime
import hashlib
import hmac
import json
import os
import ssl
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Dict, List, Any, Tuple

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_FILE = os.path.join(BOT_DIR, "wabbits_vault.json")

SSL_CTX = ssl.create_default_context()
SSL_UNVERIFIED_CTX = ssl._create_unverified_context()

WABBITS_MEMORY: Dict[int, List[Dict[str, Any]]] = {}
WABBITS_BATCH_LOCK = threading.Lock()
WABBITS_BATCH: Dict[int, Dict[str, Any]] = {}
WABBITS_BATCH_DELAY = 2.0

WABBITS_CLOUD_DONE = False
WABBITS_CLOUD_LOCK = threading.Lock()
WABBITS_NOTES_CACHE: Dict[str, Any] = {"notes": [], "rules": []}
WABBITS_VAULT_CACHE: Dict[str, Any] = {}
WABBITS_SEEN_UPDATES = set()


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
    global WABBITS_VAULT_CACHE
    if WABBITS_VAULT_CACHE:
        return WABBITS_VAULT_CACHE
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
            print("[wabbits] Vault HMAC mismatch!", flush=True)
            return {}
        stream = _keystream(enc_key, nonce, len(ct))
        pt = bytes(a ^ b for a, b in zip(ct, stream))
        WABBITS_VAULT_CACHE = json.loads(pt.decode("utf-8"))
        return WABBITS_VAULT_CACHE
    except Exception as e:
        print(f"[wabbits] Vault load failed: {e}", flush=True)
        return {}


def get_wabbits_token(gemini_key: str) -> str:
    env_tok = os.environ.get("WABBITS_BOT_TOKEN", "").strip()
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


def download_file(token: str, file_id: str, suffix: str = ".dat") -> str:
    info = tg_api(token, "getFile", {"file_id": file_id})
    file_path = info["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    fd, local_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    req = urllib.request.Request(url)
    with _open_url(req, timeout=30) as resp, open(local_path, "wb") as out_f:
        out_f.write(resp.read())
    return local_path


def save_notes_to_cloud(token: str, data: Dict[str, Any]):
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
        print(f"[wabbits] Cloud save failed: {e}", flush=True)


def sync_notes_from_cloud(token: str) -> Dict[str, Any]:
    global WABBITS_CLOUD_DONE, WABBITS_NOTES_CACHE
    if WABBITS_CLOUD_DONE:
        return WABBITS_NOTES_CACHE
    with WABBITS_CLOUD_LOCK:
        if WABBITS_CLOUD_DONE:
            return WABBITS_NOTES_CACHE
        if not token:
            WABBITS_CLOUD_DONE = True
            return WABBITS_NOTES_CACHE
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
                        WABBITS_NOTES_CACHE = {
                            "notes": list(cloud_data.get("notes", [])),
                            "rules": list(cloud_data.get("rules", [])),
                        }
        except Exception as e:
            print(f"[wabbits] Cloud sync warning: {e}", flush=True)
        WABBITS_CLOUD_DONE = True
    return WABBITS_NOTES_CACHE


def build_context(gemini_key: str, token: str, user_text: str = "") -> str:
    vault = load_vault(gemini_key)
    files: Dict[str, str] = vault.get("files", {})
    notes_data = sync_notes_from_cloud(token)
    q_lower = (user_text or "").lower()

    sections: List[str] = []
    for rel, content in files.items():
        if rel.startswith("companies/job_postings/"):
            fname = rel.split("/")[-1]
            kw = fname.split("_")[0].split(".")[0].lower()
            if kw not in q_lower and "posting" not in q_lower and "rundown" not in q_lower and "hippo" not in kw:
                continue
        if rel == "interviews/2026-11-05_hippo_round1_machine_transcript.txt":
            if "transcript" not in q_lower and "round 1" not in q_lower and "hippo" not in q_lower:
                continue
        sections.append(f"=== {rel} ===\n{content}")

    if notes_data.get("rules") or notes_data.get("notes"):
        sections.append("=== Persistent Telegram Notes & Rule Additions ===\n" + json.dumps(notes_data, indent=2))

    return "\n\n".join(sections)


def call_gemini(gemini_key: str, payload: Dict[str, Any], timeout_sec: int = 75) -> str:
    models = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-2.5-flash"]
    bad_models = set()
    last_err = None
    for attempt in range(2):
        for model_name in models:
            if model_name in bad_models:
                continue
            req_payload = json.loads(json.dumps(payload))
            if attempt == 1 and "thinkingConfig" in req_payload.get("generationConfig", {}):
                req_payload["generationConfig"].pop("thinkingConfig", None)
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(req_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with _open_url(req, timeout=timeout_sec) as resp:
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


def ask_wabbits(
    gemini_key: str,
    token: str,
    user_text: str,
    chat_id: int,
    image_paths: List[str] = None,
    audio_items: List[Tuple[str, str]] = None,
) -> str:
    ctx = build_context(gemini_key, token, user_text)
    if chat_id not in WABBITS_MEMORY:
        WABBITS_MEMORY[chat_id] = []
    history = WABBITS_MEMORY[chat_id]

    system_prompt = (
        "You are Aaron Millard's personal Hunting Wabbits Assistant on Telegram.\n"
        "You have full access to his entire Hunting Wabbits repository (`rules/MasterRules.md`, `memory/ProjectMemory.md`, `memory/DecisionLog.md`, `profile/resume.md`, company profiles, job postings, interview prep questions, and feedback).\n\n"
        "CRITICAL RULES (FOLLOW AT ALL TIMES):\n"
        "1. RULE #1 (SHORT AS HUMANLY POSSIBLE): Every response must be as short, direct, and scannable as humanly possible. Use tight bullet points, zero fluff, no long intros, no recaps unless explicitly asked.\n"
        "2. IDEA-DUMP MODE RULE: When Aaron is purely dumping ideas, notes, or requirements without asking a question, reply ONLY `Okay.` (the bot automatically logs his note).\n"
        "3. INTERVIEW PREP VOICE: Default to Aaron's 'Casual & Direct' voice. When giving feedback on voice memos or practice answers, be candid, specific, and constructive—flag wandering, weak structure, filler, unclear ownership/impact, and give the #1 priority fix.\n"
        "4. ACCURATE GROUNDING: Never invent experience, tools, or company facts not in the project files. Distinguish verified facts from unknowns.\n\n"
        f"{ctx}"
    )

    parts: List[Dict[str, Any]] = []
    for img_path in (image_paths or []):
        if img_path and os.path.exists(img_path):
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})

    for aud_path, mime_type in (audio_items or []):
        if aud_path and os.path.exists(aud_path):
            with open(aud_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            parts.append({"inline_data": {"mime_type": mime_type, "data": b64}})

    default_prompt = (
        "Listen to this voice memo and respond following MasterRules.md."
        if audio_items
        else "Read the image(s) and respond following MasterRules.md."
    )
    parts.append({"text": user_text or default_prompt})

    trimmed_history: List[Dict[str, Any]] = []
    recent_slice = list(history[-12:])
    for idx, turn in enumerate(recent_slice):
        if idx < len(recent_slice) - 4:
            text_only_parts = [p for p in turn.get("parts", []) if "text" in p]
            if not text_only_parts:
                text_only_parts = [{"text": "[Earlier Media Upload]"}]
            trimmed_history.append({"role": turn["role"], "parts": text_only_parts})
        else:
            trimmed_history.append(turn)

    contents = trimmed_history + [{"role": "user", "parts": parts}]
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.4,
            "thinkingConfig": {"thinkingBudget": 1024},
        },
    }

    reply = call_gemini(gemini_key, payload, timeout_sec=75)
    history.append({"role": "user", "parts": parts})
    history.append({"role": "model", "parts": [{"text": reply}]})

    s_lower = (user_text or "").strip().lower()
    if reply.strip() in ("Okay.", "Okay") or any(
        s_lower.startswith(p) for p in ("note:", "log:", "remember:", "rule:", "add rule", "save note")
    ):
        if user_text and user_text.strip():
            cat = "rule" if "rule" in s_lower[:15] else "note"
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            notes_data = sync_notes_from_cloud(token)
            entry = {"timestamp": ts, "text": user_text.strip()}
            notes_data.setdefault("rules" if cat == "rule" else "notes", []).append(entry)
            threading.Thread(target=save_notes_to_cloud, args=(token, notes_data), daemon=True).start()

    return reply


def _flush_wabbits_batch(gemini_key: str, token: str, chat_id: int):
    with WABBITS_BATCH_LOCK:
        batch = WABBITS_BATCH.pop(chat_id, None)
    if not batch:
        return

    texts: List[str] = batch.get("texts", [])
    photos: List[str] = batch.get("photos", [])
    audios: List[Tuple[str, str]] = batch.get("audios", [])
    combined_text = "\n".join(t for t in texts if t).strip()

    try:
        if combined_text.strip().lower() in ("/start", "start"):
            send_message(
                token,
                chat_id,
                "Hunting Wabbits Bot online (24/7 Render cloud). Ask anything about your interviews, companies, prep questions, rules, or send a voice memo / idea dump.",
            )
            return
        if combined_text.strip().lower() in ("/clear", "clear memory", "reset chat"):
            WABBITS_MEMORY.pop(chat_id, None)
            send_message(token, chat_id, "Chat history cleared.")
            return

        reply = ask_wabbits(gemini_key, token, combined_text, chat_id, image_paths=photos, audio_items=audios)
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
        for ap, _ in audios:
            try:
                if os.path.exists(ap):
                    os.remove(ap)
            except Exception:
                pass


def _enqueue_wabbits(
    gemini_key: str,
    token: str,
    chat_id: int,
    text: str = "",
    photo_path: str = None,
    audio_item: Tuple[str, str] = None,
):
    with WABBITS_BATCH_LOCK:
        entry = WABBITS_BATCH.get(chat_id)
        if not entry:
            entry = {"texts": [], "photos": [], "audios": [], "timer": None}
            WABBITS_BATCH[chat_id] = entry
        if entry["timer"] is not None:
            entry["timer"].cancel()
        if text:
            entry["texts"].append(text.strip())
        if photo_path:
            entry["photos"].append(photo_path)
        if audio_item:
            entry["audios"].append(audio_item)
        timer = threading.Timer(WABBITS_BATCH_DELAY, _flush_wabbits_batch, args=(gemini_key, token, chat_id))
        timer.daemon = True
        entry["timer"] = timer
        timer.start()


def process_wabbits_webhook(gemini_key: str, body_bytes: bytes):
    token = get_wabbits_token(gemini_key)
    if not token:
        return
    try:
        upd = json.loads(body_bytes.decode("utf-8"))
        uid = upd.get("update_id")
        if uid is not None:
            if uid in WABBITS_SEEN_UPDATES:
                return
            WABBITS_SEEN_UPDATES.add(uid)
        if "message" in upd:
            msg = upd["message"]
            cid = msg["chat"]["id"]
            if "photo" in msg:
                photo_list = msg["photo"]
                best_photo = photo_list[-2] if len(photo_list) >= 2 else photo_list[-1]
                local_path = download_file(token, best_photo["file_id"], suffix=".jpg")
                _enqueue_wabbits(gemini_key, token, cid, text=msg.get("caption", ""), photo_path=local_path)
            elif "voice" in msg:
                voice = msg["voice"]
                mime = voice.get("mime_type", "audio/ogg")
                local_path = download_file(token, voice["file_id"], suffix=".ogg")
                _enqueue_wabbits(gemini_key, token, cid, text=msg.get("caption", ""), audio_item=(local_path, mime))
            elif "audio" in msg:
                aud = msg["audio"]
                mime = aud.get("mime_type", "audio/mp4")
                local_path = download_file(token, aud["file_id"], suffix=".m4a")
                _enqueue_wabbits(gemini_key, token, cid, text=msg.get("caption", ""), audio_item=(local_path, mime))
            elif "text" in msg:
                _enqueue_wabbits(gemini_key, token, cid, text=msg["text"])
    except Exception as e:
        print(f"[wabbits] Webhook error: {e}", flush=True)


def register_wabbits_webhook(gemini_key: str, external_url: str):
    token = get_wabbits_token(gemini_key)
    if not token or not external_url:
        return
    webhook_url = f"{external_url.rstrip('/')}/wabbits-webhook"
    try:
        tg_api(token, "setWebhook", {"url": webhook_url})
        sync_notes_from_cloud(token)
        print(f"[wabbits] Webhook registered at {webhook_url}", flush=True)
    except Exception as e:
        print(f"[wabbits] Webhook setup failed: {e}", flush=True)
