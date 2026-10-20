import json
import os
import re
from datetime import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from inventory_manager import (
    CATEGORIES,
    load_inventory,
    save_inventory,
    load_raw_meats,
    save_raw_meats,
)
from meat_recipes import MEAT_RECIPES
from nl_logger_and_receipt import (
    parse_natural_language_day,
    parse_receipt_text_into_items,
    run_windows_ocr_on_image,
)

st.set_page_config(
    page_title="Diet, Macro & Pantry Assistant",
    page_icon="🥩",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .pct-card {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    .pct-header {
        display: flex;
        justify-content: space-between;
        font-weight: 600;
        font-size: 0.95rem;
        margin-bottom: 6px;
    }
    .pct-bar-bg {
        width: 100%;
        height: 12px;
        background: rgba(255, 255, 255, 0.12);
        border-radius: 999px;
        overflow: hidden;
    }
    .pct-bar-fill {
        height: 100%;
        border-radius: 999px;
        transition: width 0.3s ease;
    }
    .recipe-box {
        background: rgba(34, 197, 94, 0.08);
        border: 2px solid rgba(74, 222, 128, 0.45);
        border-radius: 14px;
        padding: 18px 22px;
        margin-top: 8px;
        margin-bottom: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_pct_bar(label: str, current: float, target: float, unit: str = "g", color: str = "#22c55e", subtitle: str = ""):
    pct = int(round((current / target) * 100)) if target > 0 else 0
    bar_width = min(100, max(0, pct))
    over_color = "#f59e0b" if pct > 105 else color
    sub_html = f"<div style='font-size:0.78rem; color:#94a3b8; margin-top:4px;'>{subtitle}</div>" if subtitle else ""
    st.markdown(
        f"""
        <div class="pct-card">
            <div class="pct-header">
                <span>{label}</span>
                <span>{current:g}{unit} / {target:g}{unit} &nbsp;({pct}%)</span>
            </div>
            <div class="pct-bar-bg">
                <div class="pct-bar-fill" style="width:{bar_width}%; background:{over_color};"></div>
            </div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# Initialize session state
if "inventory" not in st.session_state:
    st.session_state.inventory = load_inventory()

if "raw_meats" not in st.session_state:
    st.session_state.raw_meats = load_raw_meats()

if "show_macros" not in st.session_state:
    st.session_state.show_macros = False

if "selected_recipe_name" not in st.session_state:
    st.session_state.selected_recipe_name = MEAT_RECIPES[0]["name"]

if "draft_day_items" not in st.session_state:
    initial_draft = []
    if os.path.exists("DailyLogs.json"):
        try:
            with open("DailyLogs.json", "r", encoding="utf-8") as f:
                saved_logs = json.load(f)
            if saved_logs and isinstance(saved_logs, list):
                latest = saved_logs[0]
                for slot_name, slot_items in latest.get("slots", {}).items():
                    for it in slot_items:
                        initial_draft.append(
                            {
                                "Meal Slot": slot_name,
                                "Raw / Cooked": it.get("measured_state", "As Packaged"),
                                "Food / Item": it.get("item", ""),
                                "Calories": int(it.get("calories", 0)),
                                "Protein (g)": float(it.get("protein_g", 0.0)),
                                "Fat (g)": float(it.get("fat_g", 0.0)),
                                "Carbs (g)": float(it.get("carbs_g", 0.0)),
                                "Fiber (g)": float(it.get("fiber_g", 0.0)),
                                "Is Gummy Fiber": bool(it.get("is_gummy", False)),
                            }
                        )
        except Exception:
            initial_draft = []
    st.session_state.draft_day_items = initial_draft

if "receipt_candidates" not in st.session_state:
    st.session_state.receipt_candidates = []


# Sidebar summary
with st.sidebar:
    st.title("🥩 Macro & Pantry HQ")
    st.caption("31 y/o • 183 lbs • Raw Meat Priority")

    st.markdown("### 🎯 Equal-Priority Targets")
    st.markdown(
        """
        - **Base Calories:** `1,900 kcal`
        - **Midnight Buffer:** `+200 kcal` *(2,100 ceiling)*
        - **Protein:** `180g`
        - **Fats:** `55g`
        - **Carbs:** `170g – 220g`
        - **Fiber:** `30g – 35g`
          - *Whole Foods:* `20g – 25g+`
          - *Gummies Cap:* `Max 10g`
        """
    )
    st.divider()

    st.metric("Raw Meats Currently in Fridge", f"{len(st.session_state.raw_meats)}")
    st.metric("Kitchen Inventory Items", f"{len(st.session_state.inventory)} (Unlimited)")

    if st.button("🔄 Sync / Reload Files", use_container_width=True):
        if os.path.exists("InventoryData.json"):
            os.remove("InventoryData.json")
        st.session_state.inventory = load_inventory()
        st.session_state.raw_meats = load_raw_meats()
        st.rerun()


# Main navigation tabs
tab_logger, tab_inv, tab_raw_meat, tab_recipes, tab_workout = st.tabs([
    "🎙️ Today's Log & Target % Trackers",
    "📦 Kitchen Inventory (Unlimited)",
    "🥩 Raw Meat Stock & 🧾 Receipt Upload",
    "🍳 35 Raw Meat Simple Recipes",
    "🏋️ Workout Plan",
])

# ==============================================================================
# TAB 1: TODAY'S LOG & DAILY TARGET % TRACKERS
# ==============================================================================
with tab_logger:
    st.subheader("🎙️ Log What You Ate Today (Voice-to-Text or Natural Language)")

    top_c1, top_c2, top_c3 = st.columns([1.2, 1.3, 1.5])
    with top_c1:
        day_type = st.radio(
            "🏋️ Is Today a Workout or Rest Day?",
            options=["🏋️ Workout Day", "🧘 Rest Day"],
            horizontal=True,
        )
    with top_c2:
        if day_type == "🏋️ Workout Day":
            split_choice = st.selectbox(
                "Which Workout Split?",
                ["Workout Day (Push)", "Workout Day (Pull)", "Workout Day (Legs)", "Workout Day (General)"],
            )
        else:
            split_choice = "Rest Day"
            st.info("🧘 **Rest Day** selected (1,900 kcal base + 200 kcal midnight buffer).")
    with top_c3:
        default_meat_state = st.radio(
            "⚖️ How did you weigh meat (unless specified in text)?",
            options=["Raw", "Cooked"],
            horizontal=True,
            help="You can also type '6 oz cooked chicken' or '6 oz raw steak' directly in the text box!",
        )

    nl_col1, nl_col2 = st.columns([1.1, 1.9], gap="large")
    with nl_col1:
        components.html(
            """
            <div style="background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.15); border-radius:10px; padding:12px; font-family:sans-serif; color:#f8fafc;">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
                    <span style="font-weight:600; font-size:14px;">🎙️ Voice-to-Text Mic</span>
                    <button id="micBtn" onclick="toggleSpeech()" style="background:#22c55e; color:#052e16; border:none; border-radius:8px; padding:7px 14px; font-weight:700; cursor:pointer; font-size:13px;">
                        🎙️ Tap to Speak
                    </button>
                </div>
                <textarea id="speechOut" rows="3" placeholder="Click 'Tap to Speak' and talk out loud (or use your phone keyboard's 🎙️ mic button in the box on the right)..." style="width:100%; box-sizing:border-box; border-radius:6px; border:1px solid #475569; background:#0f172a; color:#f8fafc; padding:8px; font-size:13px;"></textarea>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:6px;">
                    <span id="micStatus" style="font-size:12px; color:#94a3b8;">Ready to listen</span>
                    <button onclick="copyTranscript()" style="background:#334155; color:#f8fafc; border:none; border-radius:6px; padding:5px 10px; font-size:12px; cursor:pointer;">
                        📋 Copy Text
                    </button>
                </div>
            </div>
            <script>
            let recognition = null;
            let listening = false;
            if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
                const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
                recognition = new SpeechRec();
                recognition.continuous = true;
                recognition.interimResults = true;
                recognition.lang = 'en-US';
                recognition.onresult = function(event) {
                    let finalText = '';
                    for (let i = 0; i < event.results.length; ++i) {
                        finalText += event.results[i][0].transcript;
                    }
                    document.getElementById('speechOut').value = finalText;
                };
                recognition.onend = function() {
                    listening = false;
                    document.getElementById('micBtn').innerText = '🎙️ Tap to Speak';
                    document.getElementById('micBtn').style.background = '#22c55e';
                    document.getElementById('micStatus').innerText = 'Stopped — click Copy Text';
                };
            } else {
                document.getElementById('micStatus').innerText = 'Use your keyboard 🎙️ mic button on this browser.';
            }
            function toggleSpeech() {
                if (!recognition) return;
                if (!listening) {
                    recognition.start();
                    listening = true;
                    document.getElementById('micBtn').innerText = '⏹️ Stop';
                    document.getElementById('micBtn').style.background = '#ef4444';
                    document.getElementById('micStatus').innerText = '🔴 Listening... speak your meals now!';
                } else {
                    recognition.stop();
                }
            }
            function copyTranscript() {
                const el = document.getElementById('speechOut');
                el.select();
                document.execCommand('copy');
                document.getElementById('micStatus').innerText = '✅ Copied! Paste into the box on the right.';
            }
            </script>
            """,
            height=190,
        )

    with nl_col2:
        nl_input = st.text_area(
            "🗣️ What did you eat today?",
            height=125,
            placeholder=(
                "Example: For breakfast I had 3 eggs and 2 slices of Sara Lee bread. "
                "For lunch I had 6 oz cooked chicken breast with a Bibigo sticky rice bowl and black beans. "
                "For snack I had a Fairlife chocolate shake and fiber gummies."
            ),
        )
        btn_c1, btn_c2, btn_c3 = st.columns([1.5, 1.2, 1])
        with btn_c1:
            if st.button("⚡ Lay Out My Day & Calculate", type="primary", use_container_width=True):
                parsed = parse_natural_language_day(nl_input, default_meat_state=default_meat_state)
                if parsed:
                    st.session_state.draft_day_items = parsed
                    st.rerun()
                else:
                    st.warning("Type or speak at least one food item.")
        with btn_c2:
            if st.button("➕ Add to Current Table", use_container_width=True):
                parsed = parse_natural_language_day(nl_input, default_meat_state=default_meat_state)
                if parsed:
                    st.session_state.draft_day_items.extend(parsed)
                    st.rerun()
        with btn_c3:
            if st.button("🗑️ Clear Today's Entries", use_container_width=True):
                st.session_state.draft_day_items = []
                st.rerun()

    # Editable Table for Today (starts empty so user can input today's real food)
    if st.session_state.draft_day_items:
        draft_df = pd.DataFrame(st.session_state.draft_day_items)
    else:
        draft_df = pd.DataFrame(
            columns=["Meal Slot", "Raw / Cooked", "Food / Item", "Calories", "Protein (g)", "Fat (g)", "Carbs (g)", "Fiber (g)", "Is Gummy Fiber"]
        )

    st.markdown("#### 📋 Today's Food Entries (Editable)")
    edited_draft = st.data_editor(
        draft_df,
        column_config={
            "Meal Slot": st.column_config.SelectboxColumn(
                "Meal Slot",
                options=["Pre-workout", "Breakfast", "Lunch", "Dinner", "Snacks"],
                width="small",
                default="Breakfast",
            ),
            "Raw / Cooked": st.column_config.SelectboxColumn(
                "Measured State",
                options=["Raw", "Cooked", "As Packaged"],
                width="small",
                default="As Packaged",
            ),
            "Food / Item": st.column_config.TextColumn("Food / Simple Recipe", width="large"),
            "Calories": st.column_config.NumberColumn("Calories", min_value=0, max_value=3000, default=0),
            "Protein (g)": st.column_config.NumberColumn("Protein (g)", format="%.1f", min_value=0.0, default=0.0),
            "Fat (g)": st.column_config.NumberColumn("Fat (g)", format="%.1f", min_value=0.0, default=0.0),
            "Carbs (g)": st.column_config.NumberColumn("Carbs (g)", format="%.1f", min_value=0.0, default=0.0),
            "Fiber (g)": st.column_config.NumberColumn("Fiber (g)", format="%.1f", min_value=0.0, default=0.0),
            "Is Gummy Fiber": st.column_config.CheckboxColumn("Gummy Fiber?", width="small", default=False),
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="draft_day_editor",
    )

    # Calculate live totals & %s
    t_cal = int(edited_draft["Calories"].fillna(0).sum()) if len(edited_draft) else 0
    t_p = round(float(edited_draft["Protein (g)"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
    t_f = round(float(edited_draft["Fat (g)"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
    t_c = round(float(edited_draft["Carbs (g)"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
    t_fib = round(float(edited_draft["Fiber (g)"].fillna(0).sum()), 1) if len(edited_draft) else 0.0

    if len(edited_draft):
        gummy_mask = edited_draft["Is Gummy Fiber"].fillna(False).astype(bool)
        t_fib_gummy = round(float(edited_draft.loc[gummy_mask, "Fiber (g)"].fillna(0).sum()), 1)
    else:
        t_fib_gummy = 0.0
    t_fib_food = round(max(0.0, t_fib - t_fib_gummy), 1)

    st.markdown("#### 🎯 Today's Target Trackers (% & Progress Bars)")
    bar_col1, bar_col2 = st.columns(2, gap="large")
    with bar_col1:
        render_pct_bar(
            "🔥 Base Calories (1,900 kcal)",
            t_cal,
            1900,
            unit=" kcal",
            color="#3b82f6",
            subtitle=f"{max(0, 1900 - t_cal)} kcal left to 1,900 base • {max(0, 2100 - t_cal)} kcal left to 2,100 ceiling ({int(round(t_cal/2100*100))}% of ceiling)",
        )
        render_pct_bar(
            "🥩 Protein (Equal Priority: 180g)",
            t_p,
            180,
            unit="g",
            color="#22c55e",
            subtitle=f"{max(0.0, round(180 - t_p, 1)):g}g protein remaining today",
        )
        render_pct_bar(
            "🥑 Fats (Equal Priority: 55g)",
            t_f,
            55,
            unit="g",
            color="#eab308",
            subtitle=f"{max(0.0, round(55 - t_f, 1)):g}g fat remaining today",
        )
    with bar_col2:
        carb_target = 195 if day_type == "🏋️ Workout Day" else 170
        render_pct_bar(
            f"🍚 Carbohydrates (Target: {carb_target}g / Range 170–220g)",
            t_c,
            carb_target,
            unit="g",
            color="#a855f7",
            subtitle=f"{max(0.0, round(carb_target - t_c, 1)):g}g carbs remaining today",
        )
        render_pct_bar(
            "🌾 Total Fiber (Target: 32g / Range 30–35g)",
            t_fib,
            32,
            unit="g",
            color="#10b981",
            subtitle=f"Whole-Food Fiber: {t_fib_food:g}g / 22g ({int(round(t_fib_food/22*100))}%) • Gummies: {t_fib_gummy:g}g / 10g max ({int(round(t_fib_gummy/10*100))}%)",
        )
        render_pct_bar(
            "🥦 Whole-Food Fiber Minimum (22g Target / 20–25g)",
            t_fib_food,
            22,
            unit="g",
            color="#14b8a6",
            subtitle=f"{max(0.0, round(22 - t_fib_food, 1)):g}g whole-food fiber remaining",
        )

    save_c1, save_c2 = st.columns([1, 2.5])
    with save_c1:
        log_date_str = st.text_input("Log Date", value=datetime.now().strftime("%Y-%m-%d"))
    with save_c2:
        st.write("")
        if st.button("💾 Save Today's Log to DailyLogs.json", type="primary", use_container_width=True):
            slots_dict = {"Pre-workout": [], "Breakfast": [], "Lunch": [], "Dinner": [], "Snacks": []}
            for _, r_row in edited_draft.iterrows():
                s_name = r_row.get("Meal Slot") or "Breakfast"
                if s_name not in slots_dict:
                    slots_dict[s_name] = []
                slots_dict[s_name].append(
                    {
                        "item": str(r_row.get("Food / Item", "")),
                        "measured_state": str(r_row.get("Raw / Cooked", "As Packaged")),
                        "calories": int(r_row.get("Calories", 0) or 0),
                        "protein_g": float(r_row.get("Protein (g)", 0.0) or 0.0),
                        "fat_g": float(r_row.get("Fat (g)", 0.0) or 0.0),
                        "carbs_g": float(r_row.get("Carbs (g)", 0.0) or 0.0),
                        "fiber_g": float(r_row.get("Fiber (g)", 0.0) or 0.0),
                        "is_gummy": bool(r_row.get("Is Gummy Fiber", False)),
                    }
                )
            new_entry = {
                "date": log_date_str,
                "timestamp": datetime.now().isoformat(),
                "training_split": split_choice,
                "totals": {
                    "calories": t_cal,
                    "midnight_buffer_remaining": max(0, 2100 - t_cal),
                    "daily_ceiling": 2100,
                    "protein_g": t_p,
                    "fat_g": t_f,
                    "carbs_g": t_c,
                    "fiber_total_g": t_fib,
                    "fiber_whole_food_g": t_fib_food,
                    "fiber_gummy_g": t_fib_gummy,
                },
                "slots": slots_dict,
            }
            existing_logs = []
            if os.path.exists("DailyLogs.json"):
                try:
                    with open("DailyLogs.json", "r", encoding="utf-8") as f:
                        existing_logs = json.load(f)
                except Exception:
                    existing_logs = []
            # Replace if same date exists, otherwise insert at top
            existing_logs = [x for x in existing_logs if x.get("date") != log_date_str]
            existing_logs.insert(0, new_entry)
            with open("DailyLogs.json", "w", encoding="utf-8") as f:
                json.dump(existing_logs, f, indent=2)
            try:
                from github_sync import sync_file_to_github
                sync_file_to_github("DailyLogs.json", f"Log {log_date_str} from phone/dashboard")
            except Exception:
                pass
            st.success(f"Saved **{log_date_str} ({split_choice})** to `DailyLogs.json`!")
            st.rerun()

    st.divider()
    st.subheader("📚 Past Logged Days (`DailyLogs.json` & Cronometer History)")
    logs = []
    if os.path.exists("DailyLogs.json"):
        try:
            with open("DailyLogs.json", "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    if not logs:
        st.caption("No past days logged yet. Send your Cronometer screenshots or today's food in chat (or log above)!")
    else:
        log_dates = [
            f"{entry.get('date', 'Unknown')} — {entry.get('training_split', 'Day')} ({entry.get('totals', {}).get('calories', 0)} kcal)"
            for entry in logs
        ]
        selected_idx = st.selectbox("Select Logged Day", range(len(log_dates)), format_func=lambda i: log_dates[i])
        active_log = logs[selected_idx]
        totals = active_log.get("totals", {})

        hc1, hc2 = st.columns(2, gap="large")
        with hc1:
            render_pct_bar("🔥 Calories", totals.get("calories", 0), 1900, " kcal", "#3b82f6")
            render_pct_bar("🥩 Protein", totals.get("protein_g", 0), 180, "g", "#22c55e")
            render_pct_bar("🥑 Fats", totals.get("fat_g", 0), 55, "g", "#eab308")
        with hc2:
            render_pct_bar("🍚 Carbs", totals.get("carbs_g", 0), 180, "g", "#a855f7")
            render_pct_bar("🌾 Total Fiber", totals.get("fiber_total_g", 0), 32, "g", "#10b981")
            render_pct_bar("🥦 Whole-Food Fiber", totals.get("fiber_whole_food_g", 0), 22, "g", "#14b8a6")

        hist_rows = []
        for s_name in ["Pre-workout", "Breakfast", "Lunch", "Dinner", "Snacks"]:
            for s_it in active_log.get("slots", {}).get(s_name, []):
                hist_rows.append(
                    {
                        "Meal Slot": s_name,
                        "Measured State": s_it.get("measured_state", "As Packaged"),
                        "Food / Item": s_it.get("item", ""),
                        "Calories": s_it.get("calories", 0),
                        "Protein (g)": s_it.get("protein_g", 0),
                        "Fat (g)": s_it.get("fat_g", 0),
                        "Carbs (g)": s_it.get("carbs_g", 0),
                        "Fiber (g)": s_it.get("fiber_g", 0),
                    }
                )
        if hist_rows:
            st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)

# ==============================================================================
# TAB 2: KITCHEN INVENTORY (UNLIMITED — NO IN-STOCK OR WEIGHT FIELDS)
# ==============================================================================
with tab_inv:
    header_col1, header_col2 = st.columns([1.8, 1.2])
    with header_col1:
        st.subheader("📦 Kitchen Inventory (Assumed Always in Stock / Unlimited)")
        st.caption("Clean list of foods in your kitchen. No in-stock checkboxes or weight fields.")
    with header_col2:
        st.write("")
        toggle_label = (
            "🙈 Hide Macro Counts (Simple View)"
            if st.session_state.show_macros
            else "📊 Expand Macro Counts for Whole Inventory Table"
        )
        if st.button(
            toggle_label,
            type="primary" if not st.session_state.show_macros else "secondary",
            use_container_width=True,
        ):
            st.session_state.show_macros = not st.session_state.show_macros
            st.rerun()

    f_col1, f_col2, f_col3 = st.columns([2.2, 1.3, 1.3])
    with f_col1:
        smart_filter = st.radio(
            "⚡ Smart Filter",
            options=[
                "All Items",
                "🥩 Lean Protein",
                "🌾 High Whole-Food Fiber",
                "⚡ Pre-Workout Carbs",
                "🌙 Midnight Snacks",
            ],
            horizontal=True,
        )
    with f_col2:
        cat_filter = st.selectbox("📂 Category", ["All Categories"] + CATEGORIES)
    with f_col3:
        search_query = st.text_input("🔍 Search Kitchen", placeholder="e.g., oats, beans, kashi, yogurt...")

    df_all = pd.DataFrame(st.session_state.inventory)
    df_all["_orig_idx"] = df_all.index

    mask = pd.Series([True] * len(df_all))
    if smart_filter != "All Items":
        mask &= df_all["tags"].fillna("").str.contains(re.escape(smart_filter), case=False, na=False)

    if cat_filter != "All Categories":
        mask &= df_all["category"] == cat_filter

    if search_query.strip():
        q = search_query.strip()
        mask &= (
            df_all["name"].str.contains(re.escape(q), case=False, na=False)
            | df_all["category"].str.contains(re.escape(q), case=False, na=False)
            | df_all["tags"].fillna("").str.contains(re.escape(q), case=False, na=False)
        )

    df_filtered = df_all[mask].copy()

    # Clean columns: ONLY Food Item, Category, Smart Tags (plus macro columns when expanded)
    base_cols = ["name", "category", "tags"]
    macro_cols = ["serving_size", "calories", "protein_g", "fat_g", "carbs_g", "fiber_g"]
    display_cols = base_cols + macro_cols if st.session_state.show_macros else base_cols

    column_config = {
        "name": st.column_config.TextColumn("Food Item", width="large", required=True),
        "category": st.column_config.SelectboxColumn("Category", options=CATEGORIES, width="medium"),
        "tags": st.column_config.TextColumn("Smart Tags", width="medium"),
        "serving_size": st.column_config.TextColumn("Serving Size", width="small"),
        "calories": st.column_config.NumberColumn("Calories", format="%d kcal", min_value=0, max_value=3000),
        "protein_g": st.column_config.NumberColumn("Protein (g)", format="%.1fg", min_value=0.0, max_value=200.0),
        "fat_g": st.column_config.NumberColumn("Fat (g)", format="%.1fg", min_value=0.0, max_value=200.0),
        "carbs_g": st.column_config.NumberColumn("Carbs (g)", format="%.1fg", min_value=0.0, max_value=300.0),
        "fiber_g": st.column_config.NumberColumn("Fiber (g)", format="%.1fg", min_value=0.0, max_value=100.0),
    }

    edited_df = st.data_editor(
        df_filtered[display_cols],
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=480,
        key="inventory_editor",
    )

    if st.button("💾 Save Any Table Edits", type="primary"):
        for idx_in_filtered, row in edited_df.iterrows():
            orig_idx = int(df_filtered.loc[idx_in_filtered, "_orig_idx"])
            for col in display_cols:
                st.session_state.inventory[orig_idx][col] = row[col]
        save_inventory(st.session_state.inventory)
        st.success("Saved changes to `FoodInventory.md`!")
        st.rerun()

    add_col, del_col = st.columns(2, gap="large")
    with add_col:
        with st.expander("➕ Add an Item to Kitchen Inventory", expanded=False):
            new_item_name = st.text_input("Food Name", placeholder="e.g., Honey, Hot Sauce, Greek Yogurt")
            new_item_cat = st.selectbox("Category", CATEGORIES, key="new_cat")
            if st.button("➕ Add Item", use_container_width=True):
                if new_item_name.strip():
                    st.session_state.inventory.append(
                        {
                            "name": new_item_name.strip(),
                            "category": new_item_cat,
                            "tags": "",
                            "serving_size": "1 serving",
                            "calories": 0.0,
                            "protein_g": 0.0,
                            "fat_g": 0.0,
                            "carbs_g": 0.0,
                            "fiber_g": 0.0,
                        }
                    )
                    save_inventory(st.session_state.inventory)
                    st.success(f"Added **{new_item_name.strip()}**!")
                    st.rerun()

    with del_col:
        with st.expander("🗑️ Remove an Item You No Longer Have", expanded=False):
            all_names = [x["name"] for x in st.session_state.inventory]
            to_delete = st.selectbox("Select item to remove", options=["Select an item..."] + all_names)
            if st.button("🗑️ Remove Item", use_container_width=True):
                if to_delete != "Select an item...":
                    st.session_state.inventory = [
                        x for x in st.session_state.inventory if x["name"] != to_delete
                    ]
                    save_inventory(st.session_state.inventory)
                    st.success(f"Removed **{to_delete}**.")
                    st.rerun()

# ==============================================================================
# TAB 3: SEPARATE RAW MEAT SECTION & RECEIPT UPLOADER
# ==============================================================================
with tab_raw_meat:
    st.subheader("🥩 Raw Meat Currently in Your Fridge (Separate from Kitchen Inventory)")
    st.caption("Right now this is **0** until you buy raw steak, chicken, shrimp, ground beef, pork, or fish and add it here.")

    rm_left, rm_right = st.columns([1.2, 1.8], gap="large")
    with rm_left:
        with st.container(border=True):
            st.markdown("#### ➕ Add Raw Meat When You Buy It")
            rm_name = st.text_input("Raw Meat Type / Cut", placeholder="e.g., Raw Chicken Breast, Flat Iron Steak, 93/7 Ground Beef")
            rm_amount = st.text_input("Amount (Optional)", placeholder="e.g., 2.5 lbs, 2 steaks, 1 pack")
            if st.button("🥩 Add to Raw Meat List", type="primary", use_container_width=True):
                if rm_name.strip():
                    st.session_state.raw_meats.append(
                        {
                            "name": rm_name.strip(),
                            "amount": rm_amount.strip() or "In Fridge",
                            "added_on": datetime.now().strftime("%Y-%m-%d"),
                        }
                    )
                    save_raw_meats(st.session_state.raw_meats)
                    st.rerun()

    with rm_right:
        with st.container(border=True):
            st.markdown("#### 🧊 Current Raw Meat List")
            if not st.session_state.raw_meats:
                st.info("**0 Raw Meats in fridge right now.** (When you buy raw meat, add it on the left!)")
            else:
                for idx, rm in enumerate(st.session_state.raw_meats):
                    rc1, rc2, rc3 = st.columns([2, 1.2, 0.8])
                    rc1.markdown(f"**🥩 {rm['name']}**")
                    rc2.markdown(f"`{rm.get('amount', '')}`")
                    if rc3.button("🗑️ Gone", key=f"del_rm_{idx}"):
                        st.session_state.raw_meats.pop(idx)
                        save_raw_meats(st.session_state.raw_meats)
                        st.rerun()
                if st.button("🧹 Clear All Raw Meat (Reset to 0)"):
                    st.session_state.raw_meats = []
                    save_raw_meats([])
                    st.rerun()

    st.divider()
    st.subheader("🧾 Upload a Grocery Receipt (Photo or Text)")
    rc_up1, rc_up2 = st.columns(2)
    with rc_up1:
        uploaded_receipt = st.file_uploader("📸 Upload Receipt Image (PNG / JPG)", type=["png", "jpg", "jpeg", "webp"])
    with rc_up2:
        pasted_receipt_text = st.text_area("📋 Or Paste Receipt Text", height=100)

    if st.button("🔍 Scan Receipt"):
        extracted_text = pasted_receipt_text.strip()
        if uploaded_receipt is not None:
            temp_path = "temp_receipt_upload.png"
            with open(temp_path, "wb") as f:
                f.write(uploaded_receipt.getvalue())
            ocr_out = run_windows_ocr_on_image(temp_path)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if ocr_out:
                extracted_text = (extracted_text + "\n" + ocr_out).strip()
        if extracted_text:
            st.session_state.receipt_candidates = parse_receipt_text_into_items(extracted_text)

    if st.session_state.receipt_candidates:
        cand_df = pd.DataFrame(st.session_state.receipt_candidates)
        edited_cand = st.data_editor(cand_df, use_container_width=True, hide_index=True)
        if st.button("✅ Add Checked Items", type="primary"):
            for _, row in edited_cand.iterrows():
                if not row.get("Add"):
                    continue
                r_name = str(row["Item Name"]).strip()
                if "Raw Meat" in str(row.get("Destination", "")):
                    st.session_state.raw_meats.append(
                        {
                            "name": r_name,
                            "amount": str(row.get("Raw Meat Weight (if meat)", "")).strip() or "In Fridge",
                            "added_on": datetime.now().strftime("%Y-%m-%d"),
                        }
                    )
                else:
                    if not any(x["name"].lower() == r_name.lower() for x in st.session_state.inventory):
                        st.session_state.inventory.append(
                            {
                                "name": r_name,
                                "category": str(row.get("Category", "Cereals, Granola & Snacks")),
                                "tags": "",
                                "serving_size": "1 serving",
                                "calories": 0.0,
                                "protein_g": 0.0,
                                "fat_g": 0.0,
                                "carbs_g": 0.0,
                                "fiber_g": 0.0,
                            }
                        )
            save_raw_meats(st.session_state.raw_meats)
            save_inventory(st.session_state.inventory)
            st.session_state.receipt_candidates = []
            st.success("Updated your Raw Meat / Kitchen lists!")
            st.rerun()

# ==============================================================================
# TAB 4: 35 RAW MEAT MEAL OPTIONS & CLICKABLE SUPER-SIMPLE RECIPES
# ==============================================================================
with tab_recipes:
    st.subheader("🍳 35 Raw Meat Meal Options (Click Any Meal for the Super-Simple Recipe)")
    r_col1, r_col2, r_col3 = st.columns([1.8, 1.3, 1.2])
    with r_col1:
        meat_type_filter = st.radio(
            "🥩 Filter by Raw Meat Type",
            options=["All (35)", "Chicken", "Shrimp", "Sliced Steak", "Ground Beef", "Pork Tenderloin", "White Fish"],
            horizontal=True,
        )
    with r_col2:
        status_filter = st.selectbox(
            "🏠 Kitchen Ingredient Status",
            options=["All Recipes", "✅ Ready to Make (In Kitchen)", "🛒 Needs Store Item"],
        )
    with r_col3:
        method_filter = st.selectbox(
            "🔥 Cooking Method",
            options=["All Methods", "Cast Iron", "Pan", "Air Fry", "Oven", "Broil"],
        )

    filtered_recipes = []
    for r in MEAT_RECIPES:
        if meat_type_filter != "All (35)" and r["meat_type"] != meat_type_filter:
            continue
        if status_filter == "✅ Ready to Make (In Kitchen)" and not r["status"].startswith("Ready to Make"):
            continue
        if status_filter == "🛒 Needs Store Item" and not r["status"].startswith("Needs Store Item"):
            continue
        if method_filter != "All Methods" and method_filter.lower() not in r["recommended_method"].lower():
            continue
        filtered_recipes.append(r)

    df_recipes = pd.DataFrame(
        [
            {
                "Meat Type": r["meat_type"],
                "Recipe / Style Name": r["name"],
                "Ingredients & Seasonings": r["ingredients"],
                "Quick Cooking Method": r["quick_method"],
                "Status": r["status"],
                "Calories": r["calories_tier"],
                "Recommended Cooking Method": r["recommended_method"],
                "Difficulty": r["difficulty"],
                "Prep + Cook Time": r["time"],
            }
            for r in filtered_recipes
        ]
    )

    selection_event = st.dataframe(
        df_recipes,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        height=320,
    )

    if selection_event and selection_event.selection and selection_event.selection.rows:
        sel_row_idx = selection_event.selection.rows[0]
        if 0 <= sel_row_idx < len(filtered_recipes):
            st.session_state.selected_recipe_name = filtered_recipes[sel_row_idx]["name"]

    with st.expander("📱 Quick-Tap Recipe Buttons", expanded=True):
        btn_cols = st.columns(4)
        for idx, r in enumerate(filtered_recipes):
            is_selected = r["name"] == st.session_state.selected_recipe_name
            badge = "✅" if r["status"].startswith("Ready") else "🛒"
            with btn_cols[idx % 4]:
                if st.button(
                    f"{badge} {r['name']}",
                    key=f"rec_btn_{idx}_{r['name']}",
                    type="primary" if is_selected else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.selected_recipe_name = r["name"]
                    st.rerun()

    active_recipe = next(
        (r for r in MEAT_RECIPES if r["name"] == st.session_state.selected_recipe_name),
        filtered_recipes[0] if filtered_recipes else MEAT_RECIPES[0],
    )

    if active_recipe:
        est = active_recipe["est_macros"]
        status_icon = "✅ Ready to Make with Kitchen Seasonings" if active_recipe["status"].startswith("Ready") else f"🛒 {active_recipe['status']}"
        st.markdown(
            f"""
            <div class="recipe-box">
                <h3 style="margin-top:0; margin-bottom:6px;">🍽️ {active_recipe['name']} ({active_recipe['meat_type']})</h3>
                <p style="margin-top:0; color:#cbd5e1;">
                    <b>⏱️ Time:</b> {active_recipe['time']} &nbsp;|&nbsp;
                    <b>🔥 Best Method:</b> {active_recipe['recommended_method']} &nbsp;|&nbsp;
                    <b>⚡ Difficulty:</b> {active_recipe['difficulty']} &nbsp;|&nbsp;
                    <b>🏷️Calories Tier:</b> {active_recipe['calories_tier']} &nbsp;|&nbsp;
                    <b>{status_icon}</b>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        rc1, rc2, rc3 = st.columns([1.2, 1.8, 1])
        with rc1:
            with st.container(border=True):
                st.markdown("#### 🛒 What to Grab (1 Serving)")
                for item_line in active_recipe["what_to_grab"]:
                    st.markdown(f"- {item_line}")
        with rc2:
            with st.container(border=True):
                st.markdown("#### 👨‍🍳 Super Duper Simple Steps")
                for step_line in active_recipe["simple_steps"]:
                    st.markdown(f"**{step_line}**")
        with rc3:
            with st.container(border=True):
                st.markdown(f"#### 📊 Macros ({est['portion']} / ~4.5 oz cooked)")
                st.metric("Calories", f"~{est['cal']} kcal")
                st.markdown(f"- **Protein:** `{est['p']}g`\n- **Fat:** `{est['f']}g`\n- **Carbs:** `{est['c']}g`")

# ==============================================================================
# TAB 5: WORKOUT PLAN
# ==============================================================================
with tab_workout:
    st.subheader("🏋️ 4-Day Rolling Split (Heavy 3 × 6 • 8-Week Cycle)")
    w_col1, w_col2 = st.columns(2)
    with w_col1:
        with st.container(border=True):
            st.markdown("### 🔥 Day 1: Push (~75 mins)")
            st.markdown(
                """
                - **Warm-Up (1–3 blocks):** Abs, Stairmaster 10m @ Lvl 4, or Incline Treadmill.
                - **Chest:** DB Press (`55s`) → DB Incline Press (`45s`) → DB Flys (`30s–35s`) → Burnout Push-Up Drop (`Decline → Flat → Incline`)
                - **Triceps:** Dips (`25–30 lbs`) → DB Behind-Head Extensions (`25 lbs`) or Skullcrushers (`60 lbs`) → Machine Pushdowns (`175 lbs`)
                - **Shoulders:** DB Shoulder Press (`35s`) → DB Lateral Raises (`25s`) → Machine Lateral Burnout (`50–65 lbs`)
                """
            )
        with st.container(border=True):
            st.markdown("### 🦵 Day 3: Legs (~40–45 mins)")
            st.markdown(
                """
                - **Main Sequence:** Leg Curls (`120–125 lbs`) → Hack Squat (`35s/side`) → Hip Abduction (`130 lbs`) → Walking Lunges (`10s–15s`) → Leg Extensions (`130–160 lbs`) → Calf Machine (`160 lbs`)
                - **Optional Finishers:** Hip Adduction (`130 lbs`), Calf Raises (`80 lbs`), Glute Push (`100 lbs`)
                - **Cool-Down:** Sciatic nerve glides and stretching.
                """
            )
    with w_col2:
        with st.container(border=True):
            st.markdown("### 🧲 Day 2: Pull (~75 mins)")
            st.markdown(
                """
                - **Warm-Up (1–3 blocks):** Abs + Stairmaster 10m @ Lvl 4 or Incline Treadmill.
                - **Back:** Assisted Pull-Ups (`65 lbs`) → Seated Close-Grip V-Bar Row (`120 lbs`) → Rear Delt Machine (`100 lbs`)
                - **Biceps:** DB Curls (`30s`) → Hammer Curls (`30s`) → Cable / T-Grip Curls (`60 lbs`)
                """
            )
        with st.container(border=True):
            st.markdown("### 🧘 Day 4: Rest / Active Recovery")
            st.markdown(
                """
                - **Recovery:** Full day off lifting; optional 15–30 min Zone 2 cardio or mobility work.
                """
            )
