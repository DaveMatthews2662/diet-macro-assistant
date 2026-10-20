import json
import os
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime
from nl_logger_and_receipt import parse_natural_language_day
from inventory_manager import load_raw_meats, save_raw_meats

TOKEN_FILE = ".telegram_token"


def get_token() -> str:
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def send_telegram_message(token: str, chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    urllib.request.urlopen(req, timeout=10)


def handle_message(text: str) -> str:
    low = text.strip().lower()

    # Check if adding raw meat
    if low.startswith("add raw meat:") or low.startswith("raw meat:"):
        meat_str = text.split(":", 1)[1].strip()
        raw_meats = load_raw_meats()
        raw_meats.append({"name": meat_str, "amount": "In Fridge", "added_on": datetime.now().strftime("%Y-%m-%d")})
        save_raw_meats(raw_meats)
        return f"🥩 Added *{meat_str}* to your Raw Meat list!"

    today_str = datetime.now().strftime("%Y-%m-%d")
    logs = []
    if os.path.exists("DailyLogs.json"):
        try:
            with open("DailyLogs.json", "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    today_log = next((x for x in logs if x.get("date") == today_str), None)
    if not today_log:
        today_log = {
            "date": today_str,
            "timestamp": datetime.now().isoformat(),
            "water_drank_oz": 0.0,
            "totals": {},
            "entries": [],
        }
        logs.insert(0, today_log)

    # Check if user texted about drinking water e.g. "just drank 32 oz of water" / "ewater"
    if any(w in low for w in ["water", "ewater", "drank"]):
        oz_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:fl\s*oz|oz|ounces?)", low)
        if oz_m and not any(f in low for f in ["chicken", "steak", "beef", "shrimp", "turkey"]):
            added_oz = float(oz_m.group(1))
            today_log["water_drank_oz"] = round(float(today_log.get("water_drank_oz", 0.0)) + added_oz, 1)
            food_w = round(sum(float(x.get("Water (oz)", 0.0)) for x in today_log.get("entries", [])), 1)
            total_w = round(today_log["water_drank_oz"] + food_w, 1)
            today_log.setdefault("totals", {})["water_total_oz"] = total_w
            with open("DailyLogs.json", "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2)
            pct_w = int(round(total_w / 128.0 * 100))
            return (
                f"💧 *Logged +{added_oz:g} fl oz of water!*\n"
                f"• Plain Water Drank: *{today_log['water_drank_oz']:g} fl oz*\n"
                f"• Water from Food/Drinks: *{food_w:g} fl oz*\n"
                f"• *Total Water Today:* *{total_w:g} / 128 fl oz ({pct_w}%)*"
            )

    items = parse_natural_language_day(text)
    if not items:
        return (
            "🤖 Text me what you ate or drank!\n"
            "• Example: *'just drank 32 oz of water'*\n"
            "• Example: *'avocado toast - sourdough - 40g'*\n"
            "• Example: *'Raw meat: 2 lbs 93/7 ground beef'*"
        )

    today_log.setdefault("entries", []).extend(items)
    all_entries = today_log["entries"]

    t_cal = sum(int(x.get("Calories", 0)) for x in all_entries)
    t_p = round(sum(float(x.get("Protein", 0)) for x in all_entries), 1)
    t_f = round(sum(float(x.get("Fat", 0)) for x in all_entries), 1)
    t_c = round(sum(float(x.get("Carbs", 0)) for x in all_entries), 1)
    t_fib = round(sum(float(x.get("Fiber", 0)) for x in all_entries), 1)
    t_gummy = round(sum(float(x.get("Fiber", 0)) for x in all_entries if x.get("Gummy Fiber")), 1)
    t_food_fib = round(max(0.0, t_fib - t_gummy), 1)
    food_w = round(sum(float(x.get("Water (oz)", 0.0)) for x in all_entries), 1)
    drank_w = float(today_log.get("water_drank_oz", 0.0))
    total_w = round(food_w + drank_w, 1)

    today_log["totals"] = {
        "calories": t_cal,
        "midnight_buffer_remaining": max(0, 2100 - t_cal),
        "daily_ceiling": 2100,
        "protein_g": t_p,
        "fat_g": t_f,
        "carbs_g": t_c,
        "fiber_total_g": t_fib,
        "fiber_whole_food_g": t_food_fib,
        "fiber_gummy_g": t_gummy,
        "water_food_oz": food_w,
        "water_total_oz": total_w,
    }

    with open("DailyLogs.json", "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)

    return (
        f"✅ *Logged {len(items)} item(s)!*\n\n"
        f"• 🔥 Energy: *{t_cal} / 1,900 kcal* ({int(round(t_cal/1900*100))}%)\n"
        f"• 🥩 Protein: *{t_p:g} / 180g* ({int(round(t_p/180*100))}%)\n"
        f"• 🍚 Carbs: *{t_c:g} / 180g* ({int(round(t_c/180*100))}%)\n"
        f"• 🥑 Fat: *{t_f:g} / 55g* ({int(round(t_f/55*100))}%)\n"
        f"• 🌾 Fiber: *{t_fib:g} / 32g* ({int(round(t_fib/32*100))}%) — _{t_food_fib:g}g food / {t_gummy:g}g gummy_\n"
        f"• 💧 Water: *{total_w:g} / 128 fl oz* ({int(round(total_w/128*100))}%)"
    )


def run_polling():
    token = get_token()
    if not token:
        print("No Telegram bot token found.")
        return

    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=25&offset={offset}"
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message", {})
                    chat_id = msg.get("chat", {}).get("id")
                    text = msg.get("text", "")
                    if chat_id and text:
                        reply = handle_message(text)
                        send_telegram_message(token, chat_id, reply)
        except Exception:
            time.sleep(3)


if __name__ == "__main__":
    run_polling()
