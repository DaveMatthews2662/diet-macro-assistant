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
    page_title="Cronometer-Style Macro & Pantry HQ",
    page_icon="🥩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Tight Cronometer-inspired CSS
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1.5rem !important;
    }
    .crono-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 8px;
        margin-bottom: 10px;
    }
    .crono-box {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px;
        padding: 7px 11px;
    }
    .crono-top {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        font-size: 0.82rem;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .crono-pct {
        font-weight: 700;
        font-size: 0.84rem;
    }
    .crono-bar-bg {
        width: 100%;
        height: 8px;
        background: rgba(255, 255, 255, 0.12);
        border-radius: 999px;
        overflow: hidden;
    }
    .crono-bar-fill {
        height: 100%;
        border-radius: 999px;
    }
    .crono-sub {
        font-size: 0.72rem;
        color: #94a3b8;
        margin-top: 3px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .meal-pill {
        background: rgba(255, 255, 255, 0.03);
        border-left: 3px solid #3b82f6;
        padding: 4px 10px;
        margin-bottom: 4px;
        font-size: 0.82rem;
        display: flex;
        justify-content: space-between;
        border-radius: 0 6px 6px 0;
    }
    .recipe-box {
        background: rgba(34, 197, 94, 0.08);
        border: 2px solid rgba(74, 222, 128, 0.45);
        border-radius: 12px;
        padding: 14px 18px;
        margin-top: 6px;
        margin-bottom: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_compact_tracker_grid(t_cal: int, t_p: float, t_f: float, t_c: float, t_fib: float, t_fib_food: float, t_fib_gummy: float):
    """Render all 6 daily targets in one super-tight Cronometer-style horizontal grid."""
    items = [
        ("🔥 Energy", f"{t_cal} / 1,900 kcal", int(round(t_cal / 1900 * 100)), "#3b82f6", f"{max(0, 2100 - t_cal)} kcal under 2,100 ceiling"),
        ("🥩 Protein", f"{t_p:g} / 180g", int(round(t_p / 180 * 100)), "#22c55e", f"{max(0.0, round(180 - t_p, 1)):g}g left"),
        ("🍚 Net/Total Carbs", f"{t_c:g} / 170g", int(round(t_c / 170 * 100)), "#a855f7", "Target range: 170g–220g"),
        ("🥑 Fats", f"{t_f:g} / 55g", int(round(t_f / 55 * 100)), "#eab308", f"{max(0.0, round(55 - t_f, 1)):g}g left"),
        ("🌾 Total Fiber", f"{t_fib:g} / 32g", int(round(t_fib / 32 * 100)), "#10b981", "Target range: 30g–35g"),
        ("🥦 Food vs Gummy Fiber", f"{t_fib_food:g}g / 22g+", int(round(t_fib_food / 22 * 100)), "#14b8a6", f"Gummies: {t_fib_gummy:g}g / 10g max"),
    ]
    cards_html = []
    for title, val_str, pct, color, sub in items:
        w = min(100, max(0, pct))
        fill_col = "#f59e0b" if pct > 108 else color
        cards_html.append(
            f'<div class="crono-box">'
            f'<div class="crono-top"><span>{title}</span><span class="crono-pct">{val_str} ({pct}%)</span></div>'
            f'<div class="crono-bar-bg"><div class="crono-bar-fill" style="width:{w}%; background:{fill_col};"></div></div>'
            f'<div class="crono-sub">{sub}</div>'
            f'</div>'
        )
    st.markdown(f'<div class="crono-grid">{"".join(cards_html)}</div>', unsafe_allow_html=True)


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
                if "entries" in latest:
                    initial_draft = latest["entries"]
        except Exception:
            initial_draft = []
    st.session_state.draft_day_items = initial_draft

if "receipt_candidates" not in st.session_state:
    st.session_state.receipt_candidates = []


# Sidebar summary (no sync/reload button)
with st.sidebar:
    st.title("🥩 Macro & Pantry HQ")
    st.caption("31 y/o • 183 lbs • Equal-Priority Macros")

    st.markdown(
        """
        **🎯 Daily Targets**
        - **Calories:** `1,900` *(2,100 ceiling)*
        - **Protein:** `180g`
        - **Fats:** `55g`
        - **Carbs:** `170g–220g`
        - **Fiber:** `30g–35g` *(≤10g gummy)*
        """
    )
    st.divider()
    st.markdown("**🥩 Rotating Raw Meat Stock:**")
    if not st.session_state.raw_meats:
        st.caption("0 raw meats in fridge")
    else:
        for rm in st.session_state.raw_meats:
            st.markdown(f"- **{rm['name']}**: `{rm.get('amount', '')}`")


# Main navigation tabs
tab_logger, tab_inv, tab_raw_meat, tab_recipes, tab_workout = st.tabs([
    "📊 Daily Log & Target Trackers",
    "📦 Kitchen Inventory",
    "🥩 Raw Meat & 🧾 Receipt Upload",
    "🍳 35 Raw Meat Simple Recipes",
    "🏋️ Workout Plan",
])

# ==============================================================================
# TAB 1: DAILY LOG & COMPACT CRONOMETER-STYLE TARGET TRACKERS
# ==============================================================================
with tab_logger:
    # Build current DataFrame first so we can render the compact tracker bar right at the top!
    cols_order = ["Meal", "Ingredient", "Measured Amount", "Calories", "Protein", "Fat", "Carbs", "Fiber", "Gummy Fiber"]
    if st.session_state.draft_day_items:
        draft_df = pd.DataFrame(st.session_state.draft_day_items)
        for c in cols_order:
            if c not in draft_df.columns:
                draft_df[c] = False if c == "Gummy Fiber" else (0 if c in ("Calories", "Protein", "Fat", "Carbs", "Fiber") else "")
        draft_df = draft_df[cols_order]
    else:
        draft_df = pd.DataFrame(columns=cols_order)

    # Calculate live totals for top compact banner
    t_cal = int(draft_df["Calories"].fillna(0).sum()) if len(draft_df) else 0
    t_p = round(float(draft_df["Protein"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    t_f = round(float(draft_df["Fat"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    t_c = round(float(draft_df["Carbs"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    t_fib = round(float(draft_df["Fiber"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    if len(draft_df):
        gummy_mask = draft_df["Gummy Fiber"].fillna(False).astype(bool)
        t_fib_gummy = round(float(draft_df.loc[gummy_mask, "Fiber"].fillna(0).sum()), 1)
    else:
        t_fib_gummy = 0.0
    t_fib_food = round(max(0.0, t_fib - t_fib_gummy), 1)

    # 1. TIGHT CRONOMETER-STYLE TARGET BANNER AT THE VERY TOP
    render_compact_tracker_grid(t_cal, t_p, t_f, t_c, t_fib, t_fib_food, t_fib_gummy)

    # 2. COMPACT VOICE / NATURAL LANGUAGE INPUT (COLLAPSIBLE OR SIDE-BY-SIDE)
    with st.expander("🎙️ Quick Add via Voice or Text (e.g. 'avocado toast - sourdough - 40g' or natural language)", expanded=False):
        nl_col1, nl_col2 = st.columns([1, 2], gap="medium")
        with nl_col1:
            components.html(
                """
                <div style="background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.15); border-radius:8px; padding:8px; font-family:sans-serif; color:#f8fafc;">
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:6px;">
                        <span style="font-weight:600; font-size:12px;">🎙️ Voice Mic</span>
                        <button id="micBtn" onclick="toggleSpeech()" style="background:#22c55e; color:#052e16; border:none; border-radius:6px; padding:4px 10px; font-weight:700; cursor:pointer; font-size:12px;">
                            🎙️ Speak
                        </button>
                    </div>
                    <textarea id="speechOut" rows="2" placeholder="Speak out loud..." style="width:100%; box-sizing:border-box; border-radius:6px; border:1px solid #475569; background:#0f172a; color:#f8fafc; padding:6px; font-size:12px;"></textarea>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                        <span id="micStatus" style="font-size:11px; color:#94a3b8;">Ready</span>
                        <button onclick="copyTranscript()" style="background:#334155; color:#f8fafc; border:none; border-radius:5px; padding:3px 8px; font-size:11px; cursor:pointer;">
                            📋 Copy
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
                        document.getElementById('micBtn').innerText = '🎙️ Speak';
                        document.getElementById('micBtn').style.background = '#22c55e';
                    };
                }
                function toggleSpeech() {
                    if (!recognition) return;
                    if (!listening) {
                        recognition.start();
                        listening = true;
                        document.getElementById('micBtn').innerText = '⏹️ Stop';
                        document.getElementById('micBtn').style.background = '#ef4444';
                    } else {
                        recognition.stop();
                    }
                }
                function copyTranscript() {
                    const el = document.getElementById('speechOut');
                    el.select();
                    document.execCommand('copy');
                    document.getElementById('micStatus').innerText = '✅ Copied!';
                }
                </script>
                """,
                height=135,
            )
        with nl_col2:
            nl_input = st.text_area(
                "Type or dictate items (cups for liquids, grams for everything else):",
                height=80,
                placeholder="avocado toast - sourdough - 40g\navocado toast - avocado - 50g\napple - apple - 182g",
            )
            b1, b2, b3 = st.columns([1.3, 1.3, 1])
            if b1.button("➕ Append to Today", type="primary", use_container_width=True):
                parsed = parse_natural_language_day(nl_input)
                if parsed:
                    st.session_state.draft_day_items.extend(parsed)
                    st.rerun()
            if b2.button("🔄 Replace Today's Table", use_container_width=True):
                parsed = parse_natural_language_day(nl_input)
                if parsed:
                    st.session_state.draft_day_items = parsed
                    st.rerun()
            if b3.button("🗑️ Clear Table", use_container_width=True):
                st.session_state.draft_day_items = []
                st.rerun()

    # 3. CRONOMETER-STYLE MEAL SUBTOTAL PILLS + COMPACT FOOD ENTRY TABLE
    if len(draft_df) > 0:
        meal_groups = draft_df.groupby("Meal", sort=False)
        pills_html = []
        for m_name, grp in meal_groups:
            if not str(m_name).strip():
                continue
            mc = int(grp["Calories"].fillna(0).sum())
            mp = round(float(grp["Protein"].fillna(0).sum()), 1)
            mf = round(float(grp["Fat"].fillna(0).sum()), 1)
            mcarb = round(float(grp["Carbs"].fillna(0).sum()), 1)
            mfib = round(float(grp["Fiber"].fillna(0).sum()), 1)
            pills_html.append(
                f'<div class="meal-pill">'
                f'<span><b>{m_name}</b></span>'
                f'<span style="color:#cbd5e1;">{mc} kcal &bull; {mp:g}g P &bull; {mf:g}g F &bull; {mcarb:g}g C &bull; {mfib:g}g Fib</span>'
                f'</div>'
            )
        with st.expander("🍽️ Meal Subtotals (Cronometer Group View)", expanded=False):
            st.markdown("".join(pills_html), unsafe_allow_html=True)

    edited_draft = st.data_editor(
        draft_df,
        column_config={
            "Meal": st.column_config.TextColumn("Meal", width="medium", help="e.g. Avocado Toast, Apple, Protein Shake"),
            "Ingredient": st.column_config.TextColumn("Ingredient", width="large", help="e.g. Easy Tiger Sourdough Bread"),
            "Measured Amount": st.column_config.TextColumn("Measured Amount", width="small", help="Cups for liquids, grams (g) for everything else"),
            "Calories": st.column_config.NumberColumn("Calories", min_value=0, max_value=3000, default=0, width="small"),
            "Protein": st.column_config.NumberColumn("Protein (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
            "Fat": st.column_config.NumberColumn("Fat (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
            "Carbs": st.column_config.NumberColumn("Carbs (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
            "Fiber": st.column_config.NumberColumn("Fiber (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
            "Gummy Fiber": st.column_config.CheckboxColumn("Gummy Fiber", width="small", default=False),
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        height=390,
        key="draft_day_editor",
    )

    sc1, sc2, sc3 = st.columns([1, 1.5, 2])
    with sc1:
        log_date_str = st.text_input("Date", value=datetime.now().strftime("%Y-%m-%d"), label_visibility="collapsed")
    with sc2:
        if st.button("💾 Save Log to DailyLogs.json", type="primary", use_container_width=True):
            entries_list = edited_draft.to_dict(orient="records")
            st.session_state.draft_day_items = entries_list
            t_cal_s = int(edited_draft["Calories"].fillna(0).sum()) if len(edited_draft) else 0
            t_p_s = round(float(edited_draft["Protein"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
            t_f_s = round(float(edited_draft["Fat"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
            t_c_s = round(float(edited_draft["Carbs"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
            t_fib_s = round(float(edited_draft["Fiber"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
            g_mask = edited_draft["Gummy Fiber"].fillna(False).astype(bool) if len(edited_draft) else pd.Series([], dtype=bool)
            t_gummy_s = round(float(edited_draft.loc[g_mask, "Fiber"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
            t_food_s = round(max(0.0, t_fib_s - t_gummy_s), 1)

            new_entry = {
                "date": log_date_str,
                "timestamp": datetime.now().isoformat(),
                "totals": {
                    "calories": t_cal_s,
                    "midnight_buffer_remaining": max(0, 2100 - t_cal_s),
                    "daily_ceiling": 2100,
                    "protein_g": t_p_s,
                    "fat_g": t_f_s,
                    "carbs_g": t_c_s,
                    "fiber_total_g": t_fib_s,
                    "fiber_whole_food_g": t_food_s,
                    "fiber_gummy_g": t_gummy_s,
                },
                "entries": entries_list,
            }
            existing_logs = []
            if os.path.exists("DailyLogs.json"):
                try:
                    with open("DailyLogs.json", "r", encoding="utf-8") as f:
                        existing_logs = json.load(f)
                except Exception:
                    existing_logs = []
            existing_logs = [x for x in existing_logs if x.get("date") != log_date_str]
            existing_logs.insert(0, new_entry)
            with open("DailyLogs.json", "w", encoding="utf-8") as f:
                json.dump(existing_logs, f, indent=2)
            try:
                from github_sync import sync_file_to_github
                sync_file_to_github("DailyLogs.json", f"Save {log_date_str} log")
            except Exception:
                pass
            st.success(f"Saved **{log_date_str}**!")
            st.rerun()

    with sc3:
        # Quick switcher to load any past logged day into the view
        logs = []
        if os.path.exists("DailyLogs.json"):
            try:
                with open("DailyLogs.json", "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        if logs:
            day_opts = [f"📂 Load Logged Day: {x.get('date')} ({x.get('totals', {}).get('calories', 0)} kcal)" for x in logs]
            chosen_day = st.selectbox("Switch Day", options=["Switch / View Saved Day..."] + day_opts, label_visibility="collapsed")
            if chosen_day != "Switch / View Saved Day...":
                idx = day_opts.index(chosen_day)
                st.session_state.draft_day_items = logs[idx].get("entries", [])
                st.rerun()

# ==============================================================================
# TAB 2: KITCHEN INVENTORY (UNLIMITED)
# ==============================================================================
with tab_inv:
    header_col1, header_col2 = st.columns([1.8, 1.2])
    with header_col1:
        st.subheader("📦 Kitchen Inventory (Unlimited Supply)")
    with header_col2:
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
        height=460,
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
            new_item_name = st.text_input("Food Name", placeholder="e.g., Honey, Hot Sauce")
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
                    st.rerun()

# ==============================================================================
# TAB 3: SEPARATE RAW MEAT SECTION & RECEIPT UPLOADER
# ==============================================================================
with tab_raw_meat:
    st.subheader("🥩 Rotating Raw Meat Stock (Separate from Kitchen Inventory)")
    rm_left, rm_right = st.columns([1.2, 1.8], gap="large")
    with rm_left:
        with st.container(border=True):
            st.markdown("#### ➕ Add Raw Meat")
            rm_name = st.text_input("Raw Meat Type / Cut", placeholder="e.g., 93/7 Lean Ground Beef, Flat Iron Steak")
            rm_amount = st.text_input("Amount", placeholder="e.g., 2 lbs")
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
            st.markdown("#### 🧊 Current Raw Meat in Fridge")
            if not st.session_state.raw_meats:
                st.info("**0 Raw Meats in fridge right now.**")
            else:
                for idx, rm in enumerate(st.session_state.raw_meats):
                    rc1, rc2, rc3 = st.columns([2, 1.2, 0.8])
                    rc1.markdown(f"**🥩 {rm['name']}**")
                    rc2.markdown(f"`{rm.get('amount', '')}`")
                    if rc3.button("🗑️ Gone", key=f"del_rm_{idx}"):
                        st.session_state.raw_meats.pop(idx)
                        save_raw_meats(st.session_state.raw_meats)
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
        height=300,
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
                st.markdown(f"#### 📊 Macros ({est['portion']} / ~128g cooked)")
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
