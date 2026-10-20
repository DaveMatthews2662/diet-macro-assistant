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
    page_title="Macro, Recipe & Pantry Assistant",
    page_icon="🥩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# High-contrast styling: solid dark cards (#1e293b) with bright white text (#f8fafc)
# so text is ALWAYS crisp and readable even if a phone browser forces Light Mode!
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 1.5rem !important;
    }
    /* Make top navigation tabs huge, bold, and high-contrast */
    button[data-baseweb="tab"] {
        font-size: 1.02rem !important;
        font-weight: 700 !important;
        padding: 10px 16px !important;
    }
    .crono-card {
        background-color: #1e293b !important;
        color: #f8fafc !important;
        border: 1px solid #334155 !important;
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.25);
    }
    .crono-card-title {
        display: flex;
        justify-content: space-between;
        font-weight: 700;
        font-size: 0.96rem;
        margin-bottom: 8px;
        color: #ffffff !important;
    }
    .rings-row {
        display: flex;
        justify-content: space-around;
        align-items: center;
        gap: 8px;
        margin-bottom: 10px;
        flex-wrap: wrap;
    }
    .ring-item {
        text-align: center;
        flex: 1;
        min-width: 90px;
    }
    .ring-label {
        font-size: 0.80rem;
        color: #e2e8f0 !important;
        margin-top: 3px;
        font-weight: 600;
    }
    .target-row {
        margin-bottom: 8px;
    }
    .target-top {
        display: flex;
        justify-content: space-between;
        font-size: 0.85rem;
        margin-bottom: 3px;
        color: #ffffff !important;
    }
    .target-sub {
        color: #cbd5e1 !important;
        font-weight: 500;
    }
    .target-bar-bg {
        width: 100%;
        height: 11px;
        background-color: #0f172a !important;
        border-radius: 5px;
        overflow: hidden;
    }
    .target-bar-fill {
        height: 100%;
        border-radius: 5px;
    }
    .micro-section {
        background-color: #1e293b !important;
        color: #f8fafc !important;
        border: 1px solid #334155 !important;
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 10px;
    }
    .micro-hdr {
        font-weight: 700;
        font-size: 0.88rem;
        padding-bottom: 5px;
        margin-bottom: 6px;
        border-bottom: 1px solid #475569;
        color: #ffffff !important;
    }
    .micro-row {
        display: grid;
        grid-template-columns: 1.3fr 0.9fr 1.2fr 0.5fr;
        align-items: center;
        gap: 8px;
        font-size: 0.80rem;
        padding: 3px 0;
        color: #f1f5f9 !important;
    }
    .recipe-box {
        background-color: #1e293b !important;
        color: #ffffff !important;
        border: 2px solid #22c55e !important;
        border-radius: 12px;
        padding: 14px 18px;
        margin-top: 6px;
        margin-bottom: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def svg_ring(value_text: str, unit_text: str, pct: int, color: str = "#3b82f6", size: int = 82) -> str:
    pct_clamped = min(100, max(0, pct))
    r = 32
    c = 2 * 3.14159 * r
    offset = c - (pct_clamped / 100.0) * c
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 82 82">'
        f'<circle cx="41" cy="41" r="{r}" fill="none" stroke="#334155" stroke-width="8"/>'
        f'<circle cx="41" cy="41" r="{r}" fill="none" stroke="{color}" stroke-width="8" '
        f'stroke-dasharray="{c:.1f}" stroke-dashoffset="{offset:.1f}" stroke-linecap="round" transform="rotate(-90 41 41)"/>'
        f'<text x="41" y="39" text-anchor="middle" fill="#ffffff" font-size="13" font-weight="700">{value_text}</text>'
        f'<text x="41" y="53" text-anchor="middle" fill="#cbd5e1" font-size="9.5">{unit_text}</text>'
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
    rem_base = max(0, 1900 - t_cal)
    rem_ceil = max(0, 2100 - t_cal)
    cal_pct = int(round(t_cal / 1900 * 100))

    ring1 = svg_ring(str(t_cal), "kcal", cal_pct, "#3b82f6")
    ring2 = svg_ring("1900", "base (2100 max)", 100, "#94a3b8")
    ring3 = svg_ring(str(rem_ceil), "left to 2100", int(round(rem_ceil / 2100 * 100)), "#22c55e")

    rows_data = [
        ("🔥 Energy", f"{t_cal} / 1900 kcal ({rem_base} to base • {rem_ceil} to 2100 ceiling)", cal_pct, "#38bdf8"),
        ("🥩 Protein", f"{t_p:g} / 180.0 g", int(round(t_p / 180.0 * 100)), "#ef4444"),
        ("🍚 Carbs", f"{t_c:g} / 180.0 g (target 170–220g)", int(round(t_c / 180.0 * 100)), "#a855f7"),
        ("🥑 Fat", f"{t_f:g} / 55.0 g", int(round(t_f / 55.0 * 100)), "#eab308"),
        (
            "🌾 Fiber",
            f"{t_fib:g} / 32.0 g  ({t_fib_food:g}g Whole Food • {t_fib_gummy:g}g/10g Gummy)",
            int(round(t_fib / 32.0 * 100)),
            "#22c55e",
        ),
        (
            "💧 Water",
            f"{t_water_oz:g} / 128.0 fl oz  ({food_water_oz:g} oz from food • {drank_water_oz:g} oz drank)",
            int(round(t_water_oz / 128.0 * 100)),
            "#06b6d4",
        ),
    ]

    bars_html = []
    for name, label_val, pct, col in rows_data:
        w = min(100, max(0, pct))
        bars_html.append(
            f'<div class="target-row">'
            f'<div class="target-top"><span><b>{name}</b> &nbsp;<span class="target-sub">{label_val}</span></span><span><b>{pct}%</b></span></div>'
            f'<div class="target-bar-bg"><div class="target-bar-fill" style="width:{w}%; background:{col};"></div></div>'
            f'</div>'
        )

    html = (
        f'<div class="crono-card">'
        f'<div class="crono-card-title"><span>🎯 Daily Summary & Equal-Priority Targets</span><span>CONSUMED %</span></div>'
        f'<div class="rings-row">'
        f'<div class="ring-item">{ring1}<div class="ring-label">Consumed</div></div>'
        f'<div class="ring-item">{ring2}<div class="ring-label">Target / Ceiling</div></div>'
        f'<div class="ring-item">{ring3}<div class="ring-label">Remaining</div></div>'
        f'</div>'
        f'{"".join(bars_html)}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_detailed_nutrients_dropdown(t_cal: int, t_p: float, t_c: float, t_f: float, t_fib: float, t_water_oz: float):
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
        f'<div class="crono-card"><div class="crono-card-title"><span>🔬 Highlighted Nutrients</span></div>'
        f'<div class="rings-row">{h_rings}</div></div>',
        unsafe_allow_html=True,
    )

    def section_box(title: str, rows: list) -> str:
        r_html = []
        for r_lbl, r_val, r_pct in rows:
            w = min(100, max(0, r_pct)) if r_pct is not None else 0
            bar = (
                f'<div class="target-bar-bg" style="height:7px;"><div class="target-bar-fill" style="width:{w}%; background:#38bdf8;"></div></div>'
                if r_pct is not None
                else '<div style="border-bottom:1px dashed #475569; height:1px;"></div>'
            )
            pct_txt = f"{r_pct}%" if r_pct is not None else ""
            r_html.append(f'<div class="micro-row"><span>{r_lbl}</span><span style="text-align:right;">{r_val}</span>{bar}<span style="text-align:right;">{pct_txt}</span></div>')
        return f'<div class="micro-section"><div class="micro-hdr">{title}</div>{"".join(r_html)}</div>'

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            section_box(
                "General & Carbohydrates",
                [
                    ("Energy", f"{t_cal} kcal", int(round(t_cal / 1900 * 100))),
                    ("Water (Food + Drinks)", f"{water_g} g ({t_water_oz:g} oz)", int(round(t_water_oz / 128 * 100))),
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
                "Protein & Vitamins",
                [
                    ("Protein", f"{t_p:g} g", int(round(t_p / 180 * 100))),
                    ("Leucine", f"{round(t_p * 0.068, 1):g} g", int(round(t_p / 180 * 345))),
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


# Initialize session state cleanly
if "inventory" not in st.session_state:
    st.session_state.inventory = load_inventory()

if "raw_meats" not in st.session_state:
    st.session_state.raw_meats = load_raw_meats()

if "show_macros" not in st.session_state:
    st.session_state.show_macros = False

if "show_detailed_nutrients" not in st.session_state:
    st.session_state.show_detailed_nutrients = False

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


# Sidebar summary
with st.sidebar:
    st.title("🥩 Macro & Pantry HQ")
    st.markdown(
        """
        **🎯 Equal-Priority Targets**
        - **Calories:** `1,900` *(2,100 ceiling)*
        - **Protein:** `180g`
        - **Carbs:** `170g–220g`
        - **Fat:** `55g`
        - **Fiber:** `30g–35g` *(≤10g gummy)*
        - **Water:** `128 fl oz` *(1 gallon)*
        """
    )
    st.divider()
    st.markdown("### 🥩 Rotating Raw Meat in Fridge")
    if not st.session_state.raw_meats:
        st.caption("0 raw meats in fridge")
    else:
        for rm in st.session_state.raw_meats:
            st.markdown(f"- **{rm['name']}**: `{rm.get('amount', '')}`")
    st.divider()
    st.caption(f"📦 Kitchen Inventory: **{len(st.session_state.inventory)} items** (Unlimited)")


# Main Navigation Tabs (Big & Bold at the top)
tab_logger, tab_inv, tab_raw_meat, tab_recipes, tab_workout = st.tabs([
    "📊 Daily Log & Talk-to-Text",
    "📦 Kitchen Inventory (141 Items)",
    "🥩 Raw Meat & 🧾 Receipt Upload",
    "🍳 35 Raw Meat Simple Recipes",
    "🏋️ Workout Plan",
])

# ==============================================================================
# TAB 1: DAILY LOG, TARGETS, WATER & TALK-TO-TEXT (ALL VISIBLE)
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

    # Top bar: Switch between Today (Oct 19) & Yesterday (Oct 18) using a button so it NEVER loops!
    logs = []
    if os.path.exists("DailyLogs.json"):
        try:
            with open("DailyLogs.json", "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    top_c1, top_c2, top_c3 = st.columns([1.3, 0.7, 2.0])
    with top_c1:
        day_labels = [f"{x.get('date')} ({x.get('totals', {}).get('calories', 0)} kcal)" for x in logs] if logs else ["2026-10-19"]
        picked_day_idx = st.selectbox("Select Saved Day", range(len(day_labels)), format_func=lambda i: day_labels[i], label_visibility="collapsed")
    with top_c2:
        if st.button("📂 Load Day", use_container_width=True) and logs:
            st.session_state.draft_day_items = logs[picked_day_idx].get("entries", [])
            st.session_state.water_drank_oz = float(logs[picked_day_idx].get("water_drank_oz", 64.0))
            st.rerun()
    with top_c3:
        nut_btn_lbl = (
            "🙈 Hide Detailed Nutrient Breakdown"
            if st.session_state.show_detailed_nutrients
            else "🔬 Expand Detailed Nutrient Breakdown (Vitamins, Minerals & Lipids)"
        )
        if st.button(nut_btn_lbl, use_container_width=True):
            st.session_state.show_detailed_nutrients = not st.session_state.show_detailed_nutrients
            st.rerun()

    # 1. TARGETS & RINGS CARD
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
    if wc5.button("🔄 Reset Water (0 oz)", use_container_width=True):
        st.session_state.water_drank_oz = 0.0
        st.rerun()

    # 2. EXPANDABLE DETAILED NUTRIENT BREAKDOWN
    if st.session_state.show_detailed_nutrients:
        render_detailed_nutrients_dropdown(t_cal, t_p, t_c, t_f, t_fib, total_water_oz)

    # 3. WIDE-OPEN TALK-TO-TEXT & NATURAL LANGUAGE FOOD LOGGER (Never hidden!)
    st.markdown("#### 🎙️ Enter Food or Water (Talk-to-Text or Natural Language)")
    nl_col1, nl_col2 = st.columns([1.05, 1.95], gap="medium")
    with nl_col1:
        components.html(
            """
            <div style="background:#1e293b; border:1px solid #475569; border-radius:10px; padding:10px; font-family:sans-serif; color:#ffffff;">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:6px;">
                    <span style="font-weight:700; font-size:13px;">🎙️ Desktop Voice Mic</span>
                    <button id="micBtn" onclick="toggleSpeech()" style="background:#22c55e; color:#052e16; border:none; border-radius:6px; padding:5px 12px; font-weight:700; cursor:pointer; font-size:12px;">
                        🎙️ Start Speaking
                    </button>
                </div>
                <textarea id="speechOut" rows="2" placeholder="On Phone: tap the box on the right and press your phone keyboard's 🎙️ mic key! On PC: click 'Start Speaking' here..." style="width:100%; box-sizing:border-box; border-radius:6px; border:1px solid #64748b; background:#0f172a; color:#ffffff; padding:6px; font-size:12px;"></textarea>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:5px;">
                    <span id="micStatus" style="font-size:11px; color:#cbd5e1;">Ready</span>
                    <button onclick="copyTranscript()" style="background:#3b82f6; color:#ffffff; border:none; border-radius:5px; padding:4px 10px; font-size:11px; font-weight:600; cursor:pointer;">
                        📋 Copy Spoken Text
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
                    document.getElementById('micBtn').innerText = '🎙️ Start Speaking';
                    document.getElementById('micBtn').style.background = '#22c55e';
                };
            }
            function toggleSpeech() {
                if (!recognition) {
                    document.getElementById('micStatus').innerText = 'Use keyboard 🎙️ mic button on this browser';
                    return;
                }
                if (!listening) {
                    recognition.start();
                    listening = true;
                    document.getElementById('micBtn').innerText = '⏹️ Stop';
                    document.getElementById('micBtn').style.background = '#ef4444';
                    document.getElementById('micStatus').innerText = '🔴 Listening...';
                } else {
                    recognition.stop();
                }
            }
            function copyTranscript() {
                const el = document.getElementById('speechOut');
                el.select();
                document.execCommand('copy');
                document.getElementById('micStatus').innerText = '✅ Copied! Paste in box on right ->';
            }
            </script>
            """,
            height=145,
        )
    with nl_col2:
        nl_input = st.text_area(
            "🗣️ Type or Dictate Food / Water (e.g. 'just drank 32 oz of water' or 'avocado toast - sourdough - 40g'):",
            height=82,
            placeholder="avocado toast - sourdough - 40g\navocado toast - avocado - 50g\napple - apple - 182g\njust drank 32 oz of water",
        )
        b1, b2, b3 = st.columns([1.4, 1.3, 1.1])
        if b1.button("➕ Add to Today's Log", type="primary", use_container_width=True):
            low_in = nl_input.lower()
            added_any = False
            if ("water" in low_in or "ewater" in low_in) and "drank" in low_in:
                oz_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:fl\s*oz|oz|ounces?)", low_in)
                if oz_m:
                    st.session_state.water_drank_oz += float(oz_m.group(1))
                    added_any = True
            parsed = parse_natural_language_day(nl_input)
            if parsed:
                st.session_state.draft_day_items.extend(parsed)
                added_any = True
            if added_any:
                st.rerun()
            else:
                st.warning("Type at least one food or water amount (e.g. '3 eggs' or 'drank 32 oz water').")
        if b2.button("🔄 Replace Today's Table", use_container_width=True):
            parsed = parse_natural_language_day(nl_input)
            if parsed:
                st.session_state.draft_day_items = parsed
                st.rerun()
        if b3.button("🗑️ Clear Today's Table", use_container_width=True):
            st.session_state.draft_day_items = []
            st.rerun()

    # 4. FOOD ENTRIES TABLE
    st.markdown("#### 📋 Today's Food Entries (`Meal - Ingredient - Measured Amount`)")
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
        height=380,
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
        st.subheader("📦 Kitchen Inventory (141 Items — Assumed Unlimited)")
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
        with st.container(border=True):
            st.markdown("#### ➕ Add an Item to Kitchen Inventory")
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
        with st.container(border=True):
            st.markdown("#### 🗑️ Remove an Item You No Longer Have")
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

    if st.button("🔍 Scan Receipt", type="primary"):
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

    st.markdown("##### 👇 Tap any recipe button below to view the Super-Simple Recipe:")
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
                <h3 style="margin-top:0; margin-bottom:6px; color:#ffffff;">🍽️ {active_recipe['name']} ({active_recipe['meat_type']})</h3>
                <p style="margin-top:0; color:#e2e8f0;">
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
