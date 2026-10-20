import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime
from nl_logger_and_receipt import parse_natural_language_day
from inventory_manager import load_raw_meats, save_raw_meats, load_inventory, save_inventory

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
        return f"🥩 Added **{meat_str}** to your Raw Meat list! You now have {len(raw_meats)} raw meat item(s)."

    # Otherwise parse as daily food log
    day_type = "Rest Day" if "rest day" in low else ("Workout Day" if "workout" in low else "Logged via Telegram")
    items = parse_natural_language_day(text)
    if not items:
        return (
            "🤖 I received your message! To log food, just text what you ate (e.g., *'3 eggs, 2 slices Sara Lee bread, "
            "6 oz cooked chicken breast, Bibigo rice'*).\n\n"
            "Or text *'Raw meat: 2 lbs Steak'* to add raw meat."
        )

    today_str = datetime.now().strftime("%Y-%m-%d")
    logs = []
    if os.path.exists("DailyLogs.json"):
        try:
            with open("DailyLogs.json", "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    # Find or create today's log
    today_log = next((x for x in logs if x.get("date") == today_str), None)
    if not today_log:
        today_log = {
            "date": today_str,
            "timestamp": datetime.now().isoformat(),
            "training_split": day_type,
            "totals": {},
            "slots": {"Pre-workout": [], "Breakfast": [], "Lunch": [], "Dinner": [], "Snacks": []},
        }
        logs.insert(0, today_log)

    if day_type != "Logged via Telegram":
        today_log["training_split"] = day_type

    for it in items:
        slot = it.get("Meal Slot", "Breakfast")
        if slot not in today_log["slots"]:
            today_log["slots"][slot] = []
        today_log["slots"][slot].append(
            {
                "item": it["Food / Item"],
                "measured_state": it.get("Raw / Cooked", "As Packaged"),
                "calories": it["Calories"],
                "protein_g": it["Protein (g)"],
                "fat_g": it["Fat (g)"],
                "carbs_g": it["Carbs (g)"],
                "fiber_g": it["Fiber (g)"],
                "is_gummy": it["Is Gummy Fiber"],
            }
        )

    # Recompute totals
    all_logged = [item for slot_list in today_log["slots"].values() for item in slot_list]
    t_cal = sum(int(x.get("calories", 0)) for x in all_logged)
    t_p = round(sum(float(x.get("protein_g", 0)) for x in all_logged), 1)
    t_f = round(sum(float(x.get("fat_g", 0)) for x in all_logged), 1)
    t_c = round(sum(float(x.get("carbs_g", 0)) for x in all_logged), 1)
    t_fib = round(sum(float(x.get("fiber_g", 0)) for x in all_logged), 1)
    t_gummy = round(sum(float(x.get("fiber_g", 0)) for x in all_logged if x.get("is_gummy")), 1)
    t_food_fib = round(max(0.0, t_fib - t_gummy), 1)

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
    }

    with open("DailyLogs.json", "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)

    added_names = ", ".join(x["Food / Item"] for x in items)
    return (
        f"✅ *Added to Today ({today_log['training_split']}):*\n{added_names}\n\n"
        f"📊 *Today's Running Totals & %:*\n"
        f"• 🔥 Calories: *{t_cal} / 1,900 kcal* ({int(round(t_cal/1900*100))}%)\n"
        f"• 🥩 Protein: *{t_p:g}g / 180g* ({int(round(t_p/180*100))}%)\n"
        f"• 🥑 Fat: *{t_f:g}g / 55g* ({int(round(t_f/55*100))}%)\n"
        f"• 🍚 Carbs: *{t_c:g}g / 170g* ({int(round(t_c/170*100))}%)\n"
        f"• 🌾 Fiber: *{t_fib:g}g / 32g* ({int(round(t_fib/32*100))}%) — _{t_food_fib:g}g food / {t_gummy:g}g gummy_"
    )


def run_polling():
    token = get_token()
    if not token:
        print("No Telegram bot token found in .telegram_token or TELEGRAM_BOT_TOKEN.")
        return

    print("Telegram bot polling started...")
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
        except Exception as e:
            time.sleep(3)


if __name__ == "__main__":
    run_polling()
