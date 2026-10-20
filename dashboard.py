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
    initial_sidebar_state="collapsed",
)

# Cronometer-inspired sleek CSS (responsive for both desktop and 390px mobile phone screens)
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.1rem !important;
        padding-bottom: 1.2rem !important;
        max-width: 1180px;
    }
    .crono-card {
        background: rgba(255, 255, 255, 0.035);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }
    .crono-card-title {
        display: flex;
        justify-content: space-between;
        font-weight: 700;
        font-size: 0.95rem;
        margin-bottom: 10px;
        color: #f8fafc;
    }
    .rings-row {
        display: flex;
        justify-content: space-around;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
        flex-wrap: wrap;
    }
    .ring-item {
        text-align: center;
        flex: 1;
        min-width: 90px;
    }
    .ring-label {
        font-size: 0.78rem;
        color: #cbd5e1;
        margin-top: 4px;
        font-weight: 600;
    }
    .target-row {
        margin-bottom: 8px;
    }
    .target-top {
        display: flex;
        justify-content: space-between;
        font-size: 0.82rem;
        margin-bottom: 3px;
        color: #e2e8f0;
    }
    .target-bar-bg {
        width: 100%;
        height: 10px;
        background: rgba(255, 255, 255, 0.12);
        border-radius: 4px;
        overflow: hidden;
    }
    .target-bar-fill {
        height: 100%;
        border-radius: 4px;
    }
    .micro-section {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 10px;
    }
    .micro-hdr {
        font-weight: 700;
        font-size: 0.86rem;
        padding-bottom: 6px;
        margin-bottom: 6px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        color: #f8fafc;
    }
    .micro-row {
        display: grid;
        grid-template-columns: 1.4fr 0.9fr 1.2fr 0.45fr;
        align-items: center;
        gap: 8px;
        font-size: 0.78rem;
        padding: 3px 0;
    }
    .meal-pill {
        background: rgba(255, 255, 255, 0.03);
        border-left: 3px solid #3b82f6;
        padding: 4px 10px;
        margin-bottom: 4px;
        font-size: 0.80rem;
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
    .phone-frame {
        max-width: 390px;
        margin: 0 auto;
        border: 3px solid #475569;
        border-radius: 24px;
        padding: 12px;
        background: #0f172a;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def svg_ring(value_text: str, unit_text: str, pct: int, color: str = "#3b82f6", size: int = 84) -> str:
    pct_clamped = min(100, max(0, pct))
    r = 33
    c = 2 * 3.14159 * r
    offset = c - (pct_clamped / 100.0) * c
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 84 84">'
        f'<circle cx="42" cy="42" r="{r}" fill="none" stroke="rgba(255,255,255,0.12)" stroke-width="8"/>'
        f'<circle cx="42" cy="42" r="{r}" fill="none" stroke="{color}" stroke-width="8" '
        f'stroke-dasharray="{c:.1f}" stroke-dashoffset="{offset:.1f}" stroke-linecap="round" transform="rotate(-90 42 42)"/>'
        f'<text x="42" y="40" text-anchor="middle" fill="#f8fafc" font-size="13" font-weight="700">{value_text}</text>'
        f'<text x="42" y="54" text-anchor="middle" fill="#94a3b8" font-size="10">{unit_text}</text>'
        f'</svg>'
    )


def render_cronometer_targets_card(
    t_cal: int,
    t_p: float,
    t_c: float,
    t_f: float,
    t_fib: float,
    t_fib_food: float,
    t_fib_gummy: float,
    t_water_oz: float,
    food_water_oz: float,
    drank_water_oz: float,
):
    """Render the exact Cronometer-inspired Energy Summary Rings + Targets card (with Fiber & Water included!)."""
    rem_base = max(0, 1900 - t_cal)
    rem_ceil = max(0, 2100 - t_cal)
    cal_pct = int(round(t_cal / 1900 * 100))

    ring1 = svg_ring(str(t_cal), "kcal", cal_pct, "#3b82f6")
    ring2 = svg_ring("1900", "base (2100 max)", 100, "#64748b")
    ring3 = svg_ring(str(rem_ceil), "to ceiling", int(round(rem_ceil / 2100 * 100)), "#22c55e")

    rows_data = [
        ("Energy", f"{t_cal} / 1900 kcal ({rem_base} to base • {rem_ceil} to 2100 ceiling)", cal_pct, "#94a3b8"),
        ("Protein", f"{t_p:g} / 180.0 g", int(round(t_p / 180.0 * 100)), "#ef4444"),
        ("Carbs", f"{t_c:g} / 180.0 g (range 170–220g)", int(round(t_c / 180.0 * 100)), "#3b82f6"),
        ("Fat", f"{t_f:g} / 55.0 g", int(round(t_f / 55.0 * 100)), "#eab308"),
        (
            "Fiber (Food + Gummy)",
            f"{t_fib:g} / 32.0 g  ({t_fib_food:g}g Whole Food • {t_fib_gummy:g}g/10g Gummy)",
            int(round(t_fib / 32.0 * 100)),
            "#22c55e",
        ),
        (
            "Water (Food + Drinks)",
            f"{t_water_oz:g} / 126.0 fl oz  ({food_water_oz:g} oz from food/drinks • {drank_water_oz:g} oz plain water)",
            int(round(t_water_oz / 126.0 * 100)),
            "#06b6d4",
        ),
    ]

    bars_html = []
    for name, label_val, pct, col in rows_data:
        w = min(100, max(0, pct))
        bars_html.append(
            f'<div class="target-row">'
            f'<div class="target-top"><span><b>{name}</b> &nbsp;<span style="color:#94a3b8;">{label_val}</span></span><span><b>{pct}%</b></span></div>'
            f'<div class="target-bar-bg"><div class="target-bar-fill" style="width:{w}%; background:{col};"></div></div>'
            f'</div>'
        )

    html = (
        f'<div class="crono-card">'
        f'<div class="crono-card-title"><span>Energy Summary</span><span style="color:#94a3b8; font-size:0.8rem;">TARGET</span></div>'
        f'<div class="rings-row">'
        f'<div class="ring-item">{ring1}<div class="ring-label">Consumed</div></div>'
        f'<div class="ring-item">{ring2}<div class="ring-label">Budget / Ceiling</div></div>'
        f'<div class="ring-item">{ring3}<div class="ring-label">Remaining</div></div>'
        f'</div>'
        f'<div class="crono-card-title" style="margin-top:6px;"><span>Targets</span><span style="color:#94a3b8; font-size:0.8rem;">CONSUMED</span></div>'
        f'{"".join(bars_html)}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_detailed_nutrients_dropdown(t_cal: int, t_p: float, t_c: float, t_f: float, t_fib: float, t_water_oz: float):
    """Render the collapsible Cronometer Pages 3-6 Nutrient Breakdown (Highlighted Nutrients, General, Carbs, Lipids, Vitamins, Minerals)."""
    # Scale micronutrients proportionally to calories/macros logged
    scale = max(0.2, t_cal / 2044.0) if t_cal > 0 else 0.0
    net_carbs = round(max(0.0, t_c - t_fib), 1)
    water_g = round(t_water_oz * 29.57, 1)

    highlights = [
        ("Fiber", int(round(t_fib / 32.0 * 100)), "#22c55e"),
        ("Iron", int(round(220 * scale)), "#3b82f6"),
        ("Calcium", int(round(76 * scale)), "#06b6d4"),
        ("Vit.A", int(round(45 * scale)), "#eab308"),
        ("Vit.C", int(round(85 * scale)), "#f97316"),
        ("Vit.B12", int(round(420 * scale)), "#a855f7"),
        ("Folate", int(round(90 * scale)), "#10b981"),
        ("Potassium", int(round(93 * scale)), "#ec4899"),
    ]
    h_rings = "".join(
        f'<div class="ring-item" style="min-width:72px;">{svg_ring(f"{pct}%", "", pct, col, 68)}<div class="ring-label">{lbl}</div></div>'
        for lbl, pct, col in highlights
    )
    st.markdown(
        f'<div class="crono-card"><div class="crono-card-title"><span>Highlighted Nutrients</span></div>'
        f'<div class="rings-row">{h_rings}</div></div>',
        unsafe_allow_html=True,
    )

    def section_box(title: str, rows: list) -> str:
        r_html = []
        for r_lbl, r_val, r_pct in rows:
            w = min(100, max(0, r_pct)) if r_pct is not None else 0
            bar = (
                f'<div class="target-bar-bg" style="height:7px;"><div class="target-bar-fill" style="width:{w}%; background:#94a3b8;"></div></div>'
                if r_pct is not None
                else '<div style="border-bottom:1px dashed rgba(255,255,255,0.15); height:1px;"></div>'
            )
            pct_txt = f"{r_pct}%" if r_pct is not None else ""
            r_html.append(f'<div class="micro-row"><span>{r_lbl}</span><span style="text-align:right;">{r_val}</span>{bar}<span style="text-align:right;">{pct_txt}</span></div>')
        return f'<div class="micro-section"><div class="micro-hdr">{title}</div>{"".join(r_html)}</div>'

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            section_box(
                "General",
                [
                    ("Energy", f"{t_cal} kcal", int(round(t_cal / 1900 * 100))),
                    ("Water (Food + Drinks)", f"{water_g} g ({t_water_oz:g} oz)", int(round(t_water_oz / 126 * 100))),
                    ("Caffeine", "0.0 mg", None),
                ],
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            section_box(
                "Carbohydrates",
                [
                    ("Total Carbs", f"{t_c:g} g", int(round(t_c / 180 * 100))),
                    ("Net Carbs", f"{net_carbs:g} g", int(round(net_carbs / 150 * 100))),
                    ("Fiber", f"{t_fib:g} g", int(round(t_fib / 32 * 100))),
                    ("Starch", f"{round(t_c * 0.42, 1):g} g", None),
                    ("Sugars", f"{round(t_c * 0.16, 1):g} g", None),
                ],
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            section_box(
                "Lipids",
                [
                    ("Fat", f"{t_f:g} g", int(round(t_f / 55 * 100))),
                    ("Monounsaturated", f"{round(t_f * 0.43, 1):g} g", None),
                    ("Polyunsaturated", f"{round(t_f * 0.15, 1):g} g", None),
                    ("Omega-3", f"{round(1.0 * scale, 1):g} g", int(round(61 * scale))),
                    ("Omega-6", f"{round(6.3 * scale, 1):g} g", int(round(37 * scale))),
                    ("Saturated", f"{round(t_f * 0.27, 1):g} g", None),
                    ("Cholesterol", f"{round(560 * scale):d} mg", None),
                ],
            ),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            section_box(
                "Protein & Amino Acids",
                [
                    ("Protein", f"{t_p:g} g", int(round(t_p / 180 * 100))),
                    ("Leucine", f"{round(t_p * 0.068, 1):g} g", int(round(t_p / 180 * 345))),
                    ("Isoleucine", f"{round(t_p * 0.038, 1):g} g", int(round(t_p / 180 * 420))),
                    ("Valine", f"{round(t_p * 0.041, 1):g} g", int(round(t_p / 180 * 365))),
                    ("Lysine", f"{round(t_p * 0.069, 1):g} g", int(round(t_p / 180 * 385))),
                ],
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            section_box(
                "Vitamins",
                [
                    ("B1 (Thiamine)", f"{round(0.8 * scale, 1):g} mg", int(round(70 * scale))),
                    ("B2 (Riboflavin)", f"{round(1.2 * scale, 1):g} mg", int(round(93 * scale))),
                    ("B3 (Niacin)", f"{round(18.3 * scale, 1):g} mg", int(round(114 * scale))),
                    ("B6 (Pyridoxine)", f"{round(1.8 * scale, 1):g} mg", int(round(138 * scale))),
                    ("B12 (Cobalamin)", f"{round(10.1 * scale, 1):g} µg", int(round(421 * scale))),
                    ("Folate", f"{round(361 * scale):d} µg", int(round(90 * scale))),
                ],
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            section_box(
                "Minerals",
                [
                    ("Calcium", f"{round(765 * scale):d} mg", int(round(77 * scale))),
                    ("Iron", f"{round(17.7 * scale, 1):g} mg", int(round(221 * scale))),
                    ("Magnesium", f"{round(298 * scale):d} mg", int(round(71 * scale))),
                    ("Potassium", f"{round(3193 * scale):d} mg", int(round(94 * scale))),
                    ("Sodium", f"{round(2639 * scale):d} mg", int(round(176 * scale))),
                    ("Zinc", f"{round(17.3 * scale, 1):g} mg", int(round(157 * scale))),
                ],
            ),
            unsafe_allow_html=True,
        )


# Initialize session state
if "inventory" not in st.session_state:
    st.session_state.inventory = load_inventory()

if "raw_meats" not in st.session_state:
    st.session_state.raw_meats = load_raw_meats()

if "show_macros" not in st.session_state:
    st.session_state.show_macros = False

if "show_detailed_nutrients" not in st.session_state:
    st.session_state.show_detailed_nutrients = False

if "mobile_preview" not in st.session_state:
    st.session_state.mobile_preview = False

if "selected_recipe_name" not in st.session_state:
    st.session_state.selected_recipe_name = MEAT_RECIPES[0]["name"]

if "draft_day_items" not in st.session_state:
    initial_draft = []
    initial_water = 64.0
    if os.path.exists("DailyLogs.json"):
        try:
            with open("DailyLogs.json", "r", encoding="utf-8") as f:
                saved_logs = json.load(f)
            if saved_logs and isinstance(saved_logs, list):
                latest = saved_logs[0]
                initial_draft = latest.get("entries", [])
                initial_water = float(latest.get("water_drank_oz", 64.0))
        except Exception:
            initial_draft = []
    st.session_state.draft_day_items = initial_draft
    st.session_state.water_drank_oz = initial_water

if "water_drank_oz" not in st.session_state:
    st.session_state.water_drank_oz = 64.0

if "receipt_candidates" not in st.session_state:
    st.session_state.receipt_candidates = []


# Main navigation tabs
tab_logger, tab_inv, tab_raw_meat, tab_recipes, tab_workout = st.tabs([
    "📊 Daily Log & Targets",
    "📦 Kitchen Inventory",
    "🥩 Raw Meat & 🧾 Receipt",
    "🍳 35 Raw Meat Recipes",
    "🏋️ Workout Plan",
])

# ==============================================================================
# TAB 1: CRONOMETER-STYLE DAILY LOG, WATER TRACKER & EXPANDABLE NUTRIENTS
# ==============================================================================
with tab_logger:
    cols_order = ["Meal", "Ingredient", "Measured Amount", "Calories", "Protein", "Fat", "Carbs", "Fiber", "Water (oz)", "Gummy Fiber"]
    if st.session_state.draft_day_items:
        draft_df = pd.DataFrame(st.session_state.draft_day_items)
        for c in cols_order:
            if c not in draft_df.columns:
                draft_df[c] = False if c == "Gummy Fiber" else (0.0 if c in ("Calories", "Protein", "Fat", "Carbs", "Fiber", "Water (oz)") else "")
        draft_df = draft_df[cols_order]
    else:
        draft_df = pd.DataFrame(columns=cols_order)

    # Calculate live totals
    t_cal = int(draft_df["Calories"].fillna(0).sum()) if len(draft_df) else 0
    t_p = round(float(draft_df["Protein"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    t_f = round(float(draft_df["Fat"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    t_c = round(float(draft_df["Carbs"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    t_fib = round(float(draft_df["Fiber"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    food_water_oz = round(float(draft_df["Water (oz)"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    drank_water_oz = round(float(st.session_state.water_drank_oz), 1)
    total_water_oz = round(food_water_oz + drank_water_oz, 1)

    if len(draft_df):
        gummy_mask = draft_df["Gummy Fiber"].fillna(False).astype(bool)
        t_fib_gummy = round(float(draft_df.loc[gummy_mask, "Fiber"].fillna(0).sum()), 1)
    else:
        t_fib_gummy = 0.0
    t_fib_food = round(max(0.0, t_fib - t_fib_gummy), 1)

    # Optional Phone Preview Toggle so user can see how it looks on a 390px phone screen
    top_bar1, top_bar2, top_bar3 = st.columns([1.4, 1.4, 1.2])
    with top_bar1:
        logs = []
        if os.path.exists("DailyLogs.json"):
            try:
                with open("DailyLogs.json", "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        if logs:
            day_opts = [f"📅 {x.get('date')} ({x.get('totals', {}).get('calories', 0)} kcal)" for x in logs]
            chosen_day = st.selectbox("Switch Logged Day", options=["📅 Viewing Active Day..."] + day_opts, label_visibility="collapsed")
            if chosen_day != "📅 Viewing Active Day...":
                idx = day_opts.index(chosen_day)
                st.session_state.draft_day_items = logs[idx].get("entries", [])
                st.session_state.water_drank_oz = float(logs[idx].get("water_drank_oz", 64.0))
                st.rerun()
    with top_bar2:
        nut_btn_lbl = (
            "🙈 Hide Detailed Nutrient Breakdown"
            if st.session_state.show_detailed_nutrients
            else "🔬 Expand Detailed Nutrient Breakdown (Vitamins, Minerals & Lipids)"
        )
        if st.button(nut_btn_lbl, use_container_width=True):
            st.session_state.show_detailed_nutrients = not st.session_state.show_detailed_nutrients
            st.rerun()
    with top_bar3:
        mob_lbl = "🖥️ Back to Full Width" if st.session_state.mobile_preview else "📱 Preview Phone Screen (390px)"
        if st.button(mob_lbl, use_container_width=True):
            st.session_state.mobile_preview = not st.session_state.mobile_preview
            st.rerun()

    if st.session_state.mobile_preview:
        st.caption("📱 **Phone Preview Mode (390px iPhone Width):** This is how the top card stacks and fits on your phone screen.")
        _, phone_col, _ = st.columns([1, 1.15, 1])
        target_container = phone_col
    else:
        target_container = st.container()

    with target_container:
        # 1. CRONOMETER ENERGY SUMMARY RINGS + TARGETS CARD (WITH FIBER & WATER!)
        render_cronometer_targets_card(
            t_cal, t_p, t_c, t_f, t_fib, t_fib_food, t_fib_gummy, total_water_oz, food_water_oz, drank_water_oz
        )

        # Quick Water Buttons Bar
        wc1, wc2, wc3, wc4, wc5 = st.columns(5)
        if wc1.button("💧 +8 oz Water", use_container_width=True):
            st.session_state.water_drank_oz += 8.0
            st.rerun()
        if wc2.button("💧 +16 oz Water", use_container_width=True):
            st.session_state.water_drank_oz += 16.0
            st.rerun()
        if wc3.button("💧 +24 oz Water", use_container_width=True):
            st.session_state.water_drank_oz += 24.0
            st.rerun()
        if wc4.button("💧 +32 oz Water", use_container_width=True):
            st.session_state.water_drank_oz += 32.0
            st.rerun()
        if wc5.button("🔄 Reset Water", use_container_width=True):
            st.session_state.water_drank_oz = 0.0
            st.rerun()

    # 2. EXPANDABLE DETAILED NUTRIENT BREAKDOWN (Pages 3-6 of Cronometer)
    if st.session_state.show_detailed_nutrients:
        render_detailed_nutrients_dropdown(t_cal, t_p, t_c, t_f, t_fib, total_water_oz)

    # 3. QUICK ADD VIA VOICE OR TEXT
    with st.expander("🎙️ Quick Add Food or Water via Voice / Text (e.g. 'just drank 32 oz of water' or 'avocado toast - sourdough - 40g')", expanded=False):
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
                "Type or dictate items:",
                height=80,
                placeholder="just drank 32 oz of water\navocado toast - sourdough - 40g\navocado toast - avocado - 50g",
            )
            b1, b2, b3 = st.columns([1.3, 1.3, 1])
            if b1.button("➕ Append to Today", type="primary", use_container_width=True):
                # Check if plain water phrase
                low_in = nl_input.lower()
                if ("water" in low_in or "ewater" in low_in) and "drank" in low_in:
                    oz_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:fl\s*oz|oz|ounces?)", low_in)
                    if oz_m:
                        st.session_state.water_drank_oz += float(oz_m.group(1))
                        st.rerun()
                parsed = parse_natural_language_day(nl_input)
                if parsed:
                    st.session_state.draft_day_items.extend(parsed)
                    st.rerun()
            if b2.button("🔄 Replace Table", use_container_width=True):
                parsed = parse_natural_language_day(nl_input)
                if parsed:
                    st.session_state.draft_day_items = parsed
                    st.rerun()
            if b3.button("🗑️ Clear Table", use_container_width=True):
                st.session_state.draft_day_items = []
                st.rerun()

    # 4. FOOD ENTRIES TABLE
    edited_draft = st.data_editor(
        draft_df,
        column_config={
            "Meal": st.column_config.TextColumn("Meal", width="medium"),
            "Ingredient": st.column_config.TextColumn("Ingredient", width="large"),
            "Measured Amount": st.column_config.TextColumn("Measured Amount", width="small"),
            "Calories": st.column_config.NumberColumn("Calories", min_value=0, max_value=3000, default=0, width="small"),
            "Protein": st.column_config.NumberColumn("Protein (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
            "Fat": st.column_config.NumberColumn("Fat (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
            "Carbs": st.column_config.NumberColumn("Carbs (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
            "Fiber": st.column_config.NumberColumn("Fiber (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
            "Water (oz)": st.column_config.NumberColumn("Water (oz)", format="%.1f", min_value=0.0, default=0.0, width="small"),
            "Gummy Fiber": st.column_config.CheckboxColumn("Gummy Fiber", width="small", default=False),
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        height=360,
        key="draft_day_editor",
    )

    sc1, sc2 = st.columns([1, 3])
    with sc1:
        log_date_str = st.text_input("Date", value=datetime.now().strftime("%Y-%m-%d"), label_visibility="collapsed")
    with sc2:
        if st.button("💾 Save Today's Log to DailyLogs.json", type="primary", use_container_width=True):
            entries_list = edited_draft.to_dict(orient="records")
            st.session_state.draft_day_items = entries_list
            t_cal_s = int(edited_draft["Calories"].fillna(0).sum()) if len(edited_draft) else 0
            t_p_s = round(float(edited_draft["Protein"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
            t_f_s = round(float(edited_draft["Fat"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
            t_c_s = round(float(edited_draft["Carbs"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
            t_fib_s = round(float(edited_draft["Fiber"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
            fw_s = round(float(edited_draft["Water (oz)"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
            tw_s = round(fw_s + float(st.session_state.water_drank_oz), 1)
            g_mask = edited_draft["Gummy Fiber"].fillna(False).astype(bool) if len(edited_draft) else pd.Series([], dtype=bool)
            t_gummy_s = round(float(edited_draft.loc[g_mask, "Fiber"].fillna(0).sum()), 1) if len(edited_draft) else 0.0
            t_food_s = round(max(0.0, t_fib_s - t_gummy_s), 1)

            new_entry = {
                "date": log_date_str,
                "timestamp": datetime.now().isoformat(),
                "water_drank_oz": float(st.session_state.water_drank_oz),
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
                    "water_food_oz": fw_s,
                    "water_total_oz": tw_s,
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
