import json
import os
import re
from datetime import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from inventory_manager import (
    CATEGORIES,
    SIDEBAR_FILTER_OPTIONS,
    load_inventory,
    save_inventory,
    load_raw_meats,
    save_raw_meats,
)
from meat_recipes import MEAT_RECIPES
from nl_logger_and_receipt import (
    MEAL_GROUPS,
    UNIT_OPTIONS,
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

# High-contrast styling:
# - padding-top: 3.8rem so top tabs are NEVER cut off by Streamlit's top bar
# - solid dark cards (#1e293b) with bright white text (#ffffff)
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 3.8rem !important;
        padding-bottom: 2.0rem !important;
    }
    /* Make top navigation tabs prominent, readable, and never cut off */
    div[data-baseweb="tab-list"] {
        gap: 8px !important;
        background-color: #0f172a !important;
        padding: 8px 10px !important;
        border-radius: 10px !important;
        border: 1px solid #334155 !important;
        margin-bottom: 14px !important;
    }
    button[data-baseweb="tab"] {
        font-size: 0.98rem !important;
        font-weight: 700 !important;
        padding: 10px 16px !important;
        color: #e2e8f0 !important;
        background-color: #1e293b !important;
        border-radius: 8px !important;
        border: 1px solid #475569 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #22c55e !important;
        color: #052e16 !important;
        border-color: #22c55e !important;
    }
    .crono-card {
        background-color: #1e293b !important;
        color: #f8fafc !important;
        border: 1px solid #334155 !important;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.25);
    }
    .crono-card-title {
        display: flex;
        justify-content: space-between;
        font-weight: 700;
        font-size: 1.0rem;
        margin-bottom: 12px;
        color: #ffffff !important;
    }
    .rings-row {
        display: flex;
        justify-content: space-around;
        align-items: center;
        gap: 14px;
        margin-bottom: 16px;
        flex-wrap: wrap;
    }
    .ring-item {
        text-align: center;
        flex: 1;
        min-width: 135px;
    }
    .ring-label {
        font-size: 0.92rem;
        color: #ffffff !important;
        margin-top: 6px;
        font-weight: 700;
    }
    .target-row {
        margin-bottom: 8px;
    }
    .target-top {
        display: flex;
        justify-content: space-between;
        font-size: 0.88rem;
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
    .meal-group-hdr {
        background-color: #1e293b !important;
        color: #ffffff !important;
        border: 1px solid #475569 !important;
        border-left: 4px solid #22c55e !important;
        border-radius: 8px;
        padding: 7px 14px;
        margin-top: 10px;
        margin-bottom: 4px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.92rem;
        font-weight: 700;
    }
    .meal-group-sub {
        font-size: 0.80rem;
        color: #cbd5e1 !important;
        font-weight: 600;
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
    .sidebar-inv-box {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        border-radius: 8px;
        padding: 10px 12px;
        max-height: 420px;
        overflow-y: auto;
        font-size: 0.83rem;
        color: #f8fafc !important;
    }
    .sidebar-inv-item {
        padding: 4px 0;
        border-bottom: 1px solid #334155;
        color: #f8fafc !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def svg_ring(value_text: str, unit_text: str, pct: int, color: str = "#3b82f6", size: int = 136) -> str:
    """Large, high-contrast SVG ring where inner text never touches the circle stroke."""
    pct_clamped = min(100, max(0, pct))
    r = 52
    c = 2 * 3.14159 * r
    offset = c - (pct_clamped / 100.0) * c
    val_font = 22 if size >= 120 else 14
    unit_font = 11.5 if size >= 120 else 9.5
    cx = size // 2
    cy = size // 2
    if size < 100:
        r = 30
        c = 2 * 3.14159 * r
        offset = c - (pct_clamped / 100.0) * c
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#334155" stroke-width="10"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="10" '
        f'stroke-dasharray="{c:.1f}" stroke-dashoffset="{offset:.1f}" stroke-linecap="round" transform="rotate(-90 {cx} {cy})"/>'
        f'<text x="{cx}" y="{cy - 3}" text-anchor="middle" fill="#ffffff" font-size="{val_font}" font-weight="800">{value_text}</text>'
        f'<text x="{cx}" y="{cy + 16}" text-anchor="middle" fill="#e2e8f0" font-size="{unit_font}" font-weight="600">{unit_text}</text>'
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

    ring1 = svg_ring(str(t_cal), "kcal", cal_pct, "#3b82f6", 136)
    ring2 = svg_ring("1900", "2100 max", 100, "#94a3b8", 136)
    ring3 = svg_ring(str(rem_ceil), "kcal left", int(round(rem_ceil / 2100 * 100)), "#22c55e", 136)

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
        f'<div class="ring-item">{ring2}<div class="ring-label">Target (2,100 Ceiling)</div></div>'
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
        f'<div class="ring-item" style="min-width:80px;">{svg_ring(f"{pct}%", "", pct, col, 78)}<div class="ring-label" style="font-size:0.80rem;">{lbl}</div></div>'
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


def normalize_entry_row(row: dict) -> dict:
    """Ensure every food entry has Group, Meal, Ingredient, Amount, Unit, Calories, Protein, Fat, Carbs, Fiber, Water (oz)."""
    grp = row.get("Group") or "Snacks"
    if grp not in MEAL_GROUPS:
        grp = "Gummy fibers" if "gumm" in str(row.get("Ingredient", "")).lower() else "Snacks"

    amt = row.get("Amount")
    unit = row.get("Unit")
    if amt is None or unit is None:
        m_str = str(row.get("Measured Amount", "1 serving")).strip()
        m_match = re.match(r"^(\d+(?:\.\d+)?)\s*([a-zA-Z\s]+)", m_str)
        if m_match:
            amt = float(m_match.group(1))
            u_raw = m_match.group(2).strip().lower()
            if u_raw.startswith("cup"):
                unit = "cups"
            elif u_raw == "g" or u_raw.startswith("gram"):
                unit = "g"
            elif "oz" in u_raw:
                unit = "oz"
            elif "gumm" in u_raw:
                unit = "gummies"
            else:
                unit = "1 unit"
        else:
            amt = 1.0
            unit = "1 unit"

    if unit not in UNIT_OPTIONS:
        unit = "1 unit"

    return {
        "Group": grp,
        "Meal": str(row.get("Meal", "")),
        "Ingredient": str(row.get("Ingredient", "")),
        "Amount": float(amt),
        "Unit": unit,
        "Calories": int(float(row.get("Calories", 0) or 0)),
        "Protein": round(float(row.get("Protein", 0.0) or 0.0), 1),
        "Fat": round(float(row.get("Fat", 0.0) or 0.0), 1),
        "Carbs": round(float(row.get("Carbs", 0.0) or 0.0), 1),
        "Fiber": round(float(row.get("Fiber", 0.0) or 0.0), 1),
        "Water (oz)": round(float(row.get("Water (oz)", 0.0) or 0.0), 1),
    }


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
                initial_draft = [normalize_entry_row(x) for x in latest.get("entries", [])]
                initial_water = float(latest.get("water_drank_oz", 64.0))
        except Exception:
            initial_draft = []
    st.session_state.draft_day_items = initial_draft
    st.session_state.water_drank_oz = initial_water
else:
    st.session_state.draft_day_items = [normalize_entry_row(x) for x in st.session_state.draft_day_items]

if "water_drank_oz" not in st.session_state:
    st.session_state.water_drank_oz = 64.0

if "receipt_candidates" not in st.session_state:
    st.session_state.receipt_candidates = []


# ==============================================================================
# LEFT SIDEBAR: TARGETS, RAW MEAT & FULL INVENTORY LIST WITH 16-OPTION DROPDOWN
# ==============================================================================
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
    st.markdown(f"### 📦 Kitchen Inventory ({len(st.session_state.inventory)} Items)")
    sidebar_cat_pick = st.selectbox(
        "Filter Inventory",
        options=SIDEBAR_FILTER_OPTIONS,
        index=0,
    )
    sidebar_search = st.text_input("Quick Search", placeholder="Filter items...", label_visibility="collapsed")

    sidebar_items = st.session_state.inventory
    if sidebar_cat_pick != "All":
        if sidebar_cat_pick.startswith("Good "):
            sidebar_items = [x for x in sidebar_items if sidebar_cat_pick in x.get("tags", "")]
        else:
            sidebar_items = [x for x in sidebar_items if x.get("category") == sidebar_cat_pick]

    if sidebar_search.strip():
        sq = sidebar_search.strip().lower()
        sidebar_items = [x for x in sidebar_items if sq in x.get("name", "").lower() or sq in x.get("category", "").lower()]

    st.caption(f"Showing **{len(sidebar_items)}** items ({sidebar_cat_pick}):")
    inv_rows_html = []
    for it in sidebar_items:
        p_val = float(it.get("protein_g", 0))
        fib_val = float(it.get("fiber_g", 0))
        cal_val = int(float(it.get("calories", 0)))
        badge = f" <span style='color:#94a3b8; font-size:0.75rem;'>({cal_val} kcal | {p_val:g}P | {fib_val:g}Fib)</span>" if cal_val > 0 else ""
        inv_rows_html.append(f"<div class='sidebar-inv-item'>• {it['name']}{badge}</div>")

    st.markdown(
        f"<div class='sidebar-inv-box'>{''.join(inv_rows_html) if inv_rows_html else 'No matching items'}</div>",
        unsafe_allow_html=True,
    )


# ==============================================================================
# TOP NAVIGATION TABS (NEVER CUT OFF)
# ==============================================================================
tab_logger, tab_inv, tab_raw_meat, tab_recipes, tab_workout = st.tabs([
    "📊 Daily Log & Talk-to-Text",
    "📦 Kitchen Inventory (141 Items)",
    "🥩 Raw Meat & 🧾 Receipt Upload",
    "🍳 35 Raw Meat Simple Recipes",
    "🏋️ Workout Plan",
])

# ==============================================================================
# TAB 1: DAILY LOG, TARGETS, WATER, TALK-TO-TEXT & 7 MEAL GROUPS
# ==============================================================================
with tab_logger:
    cols_order = ["Group", "Meal", "Ingredient", "Amount", "Unit", "Calories", "Protein", "Fat", "Carbs", "Fiber", "Water (oz)"]
    if st.session_state.draft_day_items:
        draft_df = pd.DataFrame([normalize_entry_row(x) for x in st.session_state.draft_day_items])[cols_order]
    else:
        draft_df = pd.DataFrame(columns=cols_order)

    # Calculate live totals across all groups
    t_cal = int(draft_df["Calories"].fillna(0).sum()) if len(draft_df) else 0
    t_p = round(float(draft_df["Protein"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    t_f = round(float(draft_df["Fat"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    t_c = round(float(draft_df["Carbs"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    t_fib = round(float(draft_df["Fiber"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    food_water_oz = round(float(draft_df["Water (oz)"].fillna(0).sum()), 1) if len(draft_df) else 0.0
    drank_water_oz = round(float(st.session_state.water_drank_oz), 1)
    total_water_oz = round(food_water_oz + drank_water_oz, 1)

    if len(draft_df):
        gummy_mask = (draft_df["Group"] == "Gummy fibers") | draft_df["Ingredient"].str.contains("gumm", case=False, na=False)
        t_fib_gummy = round(float(draft_df.loc[gummy_mask, "Fiber"].fillna(0).sum()), 1)
    else:
        t_fib_gummy = 0.0
    t_fib_food = round(max(0.0, t_fib - t_fib_gummy), 1)

    # Top bar: Switch between Today (Oct 19) & Yesterday (Oct 18)
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
            st.session_state.draft_day_items = [normalize_entry_row(x) for x in logs[picked_day_idx].get("entries", [])]
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

    # 1. TARGETS & RINGS CARD (With Bigger, Crystal-Clear Rings)
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

    # 3. WIDE-OPEN TALK-TO-TEXT & NATURAL LANGUAGE FOOD LOGGER
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
        grp_col, txt_col = st.columns([0.9, 2.1])
        with grp_col:
            target_group_pick = st.selectbox("Add into Group", options=MEAL_GROUPS, index=4)
        with txt_col:
            nl_input = st.text_area(
                "🗣️ Type or Dictate Food / Water:",
                height=72,
                placeholder="1 gatorade zero\navocado toast - sourdough - 40g\njust drank 32 oz of water",
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
            parsed = parse_natural_language_day(nl_input, default_group=target_group_pick)
            if parsed:
                st.session_state.draft_day_items.extend(parsed)
                added_any = True
            if added_any:
                st.rerun()
            else:
                st.warning("Type at least one food or water amount (e.g. '1 gatorade' or 'drank 32 oz water').")
        if b2.button("🔄 Replace Today's Table", use_container_width=True):
            parsed = parse_natural_language_day(nl_input, default_group=target_group_pick)
            if parsed:
                st.session_state.draft_day_items = parsed
                st.rerun()
        if b3.button("🗑️ Clear Today's Table", use_container_width=True):
            st.session_state.draft_day_items = []
            st.rerun()

    # 4. TODAY'S FOOD ENTRIES BROKEN UP INTO THE 7 GROUPS (WITH TINY SEPARATION & UNIT DROPDOWN)
    st.markdown("#### 📋 Today's Food Entries (Grouped by Meal Slot)")
    group_icons = {
        "Pre Workout": "⚡",
        "Breakfast": "🍳",
        "Lunch": "🥪",
        "Dinner": "🍽️",
        "Snacks": "🥨",
        "Midnight Snacks": "🌙",
        "Gummy fibers": "🍬",
    }

    group_cols = ["Meal", "Ingredient", "Amount", "Unit", "Calories", "Protein", "Fat", "Carbs", "Fiber", "Water (oz)"]
    updated_all_entries = []

    for grp_name in MEAL_GROUPS:
        grp_df = draft_df[draft_df["Group"] == grp_name][group_cols].copy() if len(draft_df) else pd.DataFrame(columns=group_cols)
        g_cal = int(grp_df["Calories"].fillna(0).sum()) if len(grp_df) else 0
        g_p = round(float(grp_df["Protein"].fillna(0).sum()), 1) if len(grp_df) else 0.0
        g_f = round(float(grp_df["Fat"].fillna(0).sum()), 1) if len(grp_df) else 0.0
        g_c = round(float(grp_df["Carbs"].fillna(0).sum()), 1) if len(grp_df) else 0.0
        g_fib = round(float(grp_df["Fiber"].fillna(0).sum()), 1) if len(grp_df) else 0.0
        g_wat = round(float(grp_df["Water (oz)"].fillna(0).sum()), 1) if len(grp_df) else 0.0

        icon = group_icons.get(grp_name, "🍽️")
        sub_label = (
            f"{g_cal} kcal &nbsp;•&nbsp; {g_p:g}g P &nbsp;•&nbsp; {g_f:g}g F &nbsp;•&nbsp; {g_c:g}g C &nbsp;•&nbsp; {g_fib:g}g Fib &nbsp;•&nbsp; {g_wat:g} oz Water"
            if len(grp_df)
            else "0 items — click '+' row below to add"
        )
        st.markdown(
            f'<div class="meal-group-hdr"><span>{icon} {grp_name}</span><span class="meal-group-sub">{sub_label}</span></div>',
            unsafe_allow_html=True,
        )

        edited_grp = st.data_editor(
            grp_df,
            column_config={
                "Meal": st.column_config.TextColumn("Meal", width="medium", default=grp_name),
                "Ingredient": st.column_config.TextColumn("Ingredient", width="large", default=""),
                "Amount": st.column_config.NumberColumn("Amount", format="%.1f", min_value=0.0, default=1.0, width="small"),
                "Unit": st.column_config.SelectboxColumn("Unit", options=UNIT_OPTIONS, default="g", width="small", required=True),
                "Calories": st.column_config.NumberColumn("Calories", min_value=0, max_value=3000, default=0, width="small"),
                "Protein": st.column_config.NumberColumn("Protein (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
                "Fat": st.column_config.NumberColumn("Fat (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
                "Carbs": st.column_config.NumberColumn("Carbs (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
                "Fiber": st.column_config.NumberColumn("Fiber (g)", format="%.1f", min_value=0.0, default=0.0, width="small"),
                "Water (oz)": st.column_config.NumberColumn("Water (oz)", format="%.1f", min_value=0.0, default=0.0, width="small"),
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"editor_{grp_name}",
        )

        for _, r in edited_grp.iterrows():
            if str(r.get("Ingredient", "")).strip() or str(r.get("Meal", "")).strip():
                row_dict = r.to_dict()
                row_dict["Group"] = grp_name
                updated_all_entries.append(normalize_entry_row(row_dict))

        # Tiny visual separation between each group
        st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)

    sc1, sc2 = st.columns([1, 3])
    with sc1:
        log_date_str = st.text_input("Date", value=datetime.now().strftime("%Y-%m-%d"), label_visibility="collapsed")
    with sc2:
        if st.button("💾 Save Today's Log to DailyLogs.json", type="primary", use_container_width=True):
            st.session_state.draft_day_items = updated_all_entries
            save_df = pd.DataFrame(updated_all_entries) if updated_all_entries else pd.DataFrame(columns=cols_order)
            t_cal_s = int(save_df["Calories"].fillna(0).sum()) if len(save_df) else 0
            t_p_s = round(float(save_df["Protein"].fillna(0).sum()), 1) if len(save_df) else 0.0
            t_f_s = round(float(save_df["Fat"].fillna(0).sum()), 1) if len(save_df) else 0.0
            t_c_s = round(float(save_df["Carbs"].fillna(0).sum()), 1) if len(save_df) else 0.0
            t_fib_s = round(float(save_df["Fiber"].fillna(0).sum()), 1) if len(save_df) else 0.0
            fw_s = round(float(save_df["Water (oz)"].fillna(0).sum()), 1) if len(save_df) else 0.0
            tw_s = round(fw_s + float(st.session_state.water_drank_oz), 1)
            if len(save_df):
                g_mask = (save_df["Group"] == "Gummy fibers") | save_df["Ingredient"].str.contains("gumm", case=False, na=False)
                t_gummy_s = round(float(save_df.loc[g_mask, "Fiber"].fillna(0).sum()), 1)
            else:
                t_gummy_s = 0.0
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
                "entries": updated_all_entries,
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
        st.subheader(f"📦 Kitchen Inventory ({len(st.session_state.inventory)} Items — Assumed Unlimited)")
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

    f_col1, f_col2 = st.columns([1.5, 1.5])
    with f_col1:
        inv_filter_pick = st.selectbox("📂 Filter by Category or Macro Option", SIDEBAR_FILTER_OPTIONS, key="main_inv_filter")
    with f_col2:
        search_query = st.text_input("🔍 Search Kitchen", placeholder="e.g., oats, beans, kashi, yogurt...")

    df_all = pd.DataFrame(st.session_state.inventory)
    df_all["_orig_idx"] = df_all.index

    mask = pd.Series([True] * len(df_all))
    if inv_filter_pick != "All":
        if inv_filter_pick.startswith("Good "):
            mask &= df_all["tags"].fillna("").str.contains(re.escape(inv_filter_pick), case=False, na=False)
        else:
            mask &= df_all["category"] == inv_filter_pick

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
        "tags": st.column_config.TextColumn("Macro Options", width="medium"),
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
            st.markdown("#### ➕ Log Fresh Raw Meat")
            meat_type = st.selectbox(
                "Raw Meat Type",
                [
                    "93/7 Lean Ground Beef",
                    "Chicken Breast (Boneless Skinless)",
                    "Chicken Thighs (Boneless Skinless)",
                    "Fresh Gulf Shrimp (Peeled)",
                    "Sliced Steak (Flat Iron / Sirloin / Top Round)",
                    "Ribeye Steak (Fresh)",
                    "Pork Tenderloin",
                    "White Fish Fillets (Tilapia / Cod / Mahi)",
                ],
            )
            custom_meat = st.text_input("Or custom cut:", placeholder="e.g., Flank Steak")
            meat_amount = st.text_input("Amount / Weight Bought", placeholder="e.g., 2 lbs")
            if st.button("🥩 Add to Raw Meat Fridge", type="primary", use_container_width=True):
                chosen_meat = custom_meat.strip() if custom_meat.strip() else meat_type
                st.session_state.raw_meats.append(
                    {
                        "name": chosen_meat,
                        "amount": meat_amount.strip() if meat_amount.strip() else "In Fridge",
                        "notes": "Fresh Raw Meat",
                    }
                )
                save_raw_meats(st.session_state.raw_meats)
                st.rerun()

    with rm_right:
        with st.container(border=True):
            st.markdown("#### 🧊 Current Raw Meat in Fridge (`RawMeatStock.json`)")
            if not st.session_state.raw_meats:
                st.warning("Currently `0` (Empty).")
            else:
                rm_df = pd.DataFrame(st.session_state.raw_meats)
                edited_rm = st.data_editor(
                    rm_df,
                    column_config={
                        "name": st.column_config.TextColumn("Raw Meat Cut", width="large", required=True),
                        "amount": st.column_config.TextColumn("Amount / Weight", width="medium"),
                        "notes": st.column_config.TextColumn("Notes", width="medium"),
                    },
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    key="raw_meat_editor",
                )
                b_rm1, b_rm2 = st.columns(2)
                if b_rm1.button("💾 Save Raw Meat Updates", type="primary", use_container_width=True):
                    st.session_state.raw_meats = edited_rm.to_dict(orient="records")
                    save_raw_meats(st.session_state.raw_meats)
                    st.rerun()
                if b_rm2.button("🧹 Clear All Raw Meat (Reset to 0)", use_container_width=True):
                    st.session_state.raw_meats = []
                    save_raw_meats([])
                    st.rerun()

    st.divider()
    st.subheader("🧾 Upload Grocery Receipt (Image, Screenshot, or Text)")
    rc1, rc2 = st.columns(2, gap="large")
    with rc1:
        uploaded_receipt = st.file_uploader("📸 Upload Receipt Image (PNG / JPG)", type=["png", "jpg", "jpeg"])
        if uploaded_receipt is not None:
            if st.button("🔍 Scan Receipt Image with Windows OCR", type="primary", use_container_width=True):
                temp_path = os.path.join(".", f"_temp_receipt_{uploaded_receipt.name}")
                with open(temp_path, "wb") as f:
                    f.write(uploaded_receipt.getbuffer())
                ocr_text = run_windows_ocr_on_image(temp_path)
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
                if ocr_text:
                    st.session_state.receipt_candidates = parse_receipt_text_into_items(ocr_text)
                    st.rerun()

    with rc2:
        pasted_receipt = st.text_area(
            "📋 Or Paste H-E-B / Costco Order Text:",
            height=100,
            placeholder="93/7 Lean Ground Beef 2.0 lbs\nFairlife Fat-Free Milk\nOikos Pro 20g Strawberry Yogurt",
        )
        if st.button("⚙️ Parse Pasted Receipt Text", use_container_width=True):
            st.session_state.receipt_candidates = parse_receipt_text_into_items(pasted_receipt)
            st.rerun()

    if st.session_state.receipt_candidates:
        cand_df = pd.DataFrame(st.session_state.receipt_candidates)
        edited_cand = st.data_editor(cand_df, num_rows="dynamic", use_container_width=True, hide_index=True)
        if st.button("✅ Add Checked Items to Inventory / Raw Meat Stock", type="primary"):
            for _, r in edited_cand.iterrows():
                if not r.get("Add"):
                    continue
                nm = str(r.get("Item Name", "")).strip()
                dest = str(r.get("Destination", ""))
                wt = str(r.get("Raw Meat Weight (if meat)", "")).strip()
                if not nm:
                    continue
                if "Raw Meat" in dest:
                    st.session_state.raw_meats.append({"name": nm, "amount": wt if wt else "In Fridge", "notes": "From Receipt"})
                else:
                    cat_m = re.search(r"\((.*?)\)", dest)
                    chosen_cat = cat_m.group(1) if cat_m else str(r.get("Category", CATEGORIES[0]))
                    if not any(x["name"].lower() == nm.lower() for x in st.session_state.inventory):
                        st.session_state.inventory.append(
                            {
                                "name": nm,
                                "category": chosen_cat,
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
# TAB 4: 35 RAW MEAT SIMPLE RECIPES
# ==============================================================================
with tab_recipes:
    st.subheader("🍳 35 Raw Meat Meal Options (Click Any Meal for the Super-Simple Recipe)")
    rf1, rf2, rf3 = st.columns([1.4, 1.4, 1.2])
    with rf1:
        meat_groups = ["All 35 Meals"] + sorted(list({r["meat"] for r in MEAT_RECIPES}))
        picked_meat_group = st.selectbox("🥩 Filter by Raw Meat Type", meat_groups)
    with rf2:
        stock_filter = st.selectbox(
            "🥫 Kitchen Ingredient Status",
            ["All Meals", "✅ 100% In Kitchen Now (26 Meals)", "🛒 Needs 1–2 Quick Add-Ons (9 Meals)"],
        )
    with rf3:
        method_filter = st.selectbox("🔥 Cooking Method", ["All Methods", "Air Fryer", "Skillet", "Sheet Pan", "Oven", "Pot"])

    filtered_recipes = []
    for r in MEAT_RECIPES:
        if picked_meat_group != "All 35 Meals" and r["meat"] != picked_meat_group:
            continue
        if stock_filter.startswith("✅") and r["missing_from_kitchen"]:
            continue
        if stock_filter.startswith("🛒") and not r["missing_from_kitchen"]:
            continue
        if method_filter != "All Methods" and method_filter.lower() not in r["cook_method"].lower():
            continue
        filtered_recipes.append(r)

    recipe_rows = []
    for r in filtered_recipes:
        missing_list = r["missing_from_kitchen"]
        status_badge = "✅ 100% In Kitchen" if not missing_list else f"🛒 Needs: {', '.join(missing_list)}"
        recipe_rows.append(
            {
                "ID": r["id"],
                "Meal Style": r["name"],
                "Raw Meat": r["meat"],
                "Cook Method": r["cook_method"],
                "Time": r["prep_time"],
                "Kitchen Status": status_badge,
                "Calories": r["macros_per_serving"]["cal"],
                "Protein (g)": r["macros_per_serving"]["p"],
                "Fat (g)": r["macros_per_serving"]["f"],
                "Carbs (g)": r["macros_per_serving"]["c"],
            }
        )

    rec_df = pd.DataFrame(recipe_rows)
    selection_event = st.dataframe(
        rec_df,
        use_container_width=True,
        hide_index=True,
        height=300,
        on_select="rerun",
        selection_mode="single-row",
    )

    if selection_event and selection_event.selection and selection_event.selection.get("rows"):
        sel_idx = selection_event.selection["rows"][0]
        if 0 <= sel_idx < len(filtered_recipes):
            st.session_state.selected_recipe_name = filtered_recipes[sel_idx]["name"]

    recipe_names_list = [r["name"] for r in filtered_recipes] if filtered_recipes else [r["name"] for r in MEAT_RECIPES]
    current_idx = recipe_names_list.index(st.session_state.selected_recipe_name) if st.session_state.selected_recipe_name in recipe_names_list else 0
    chosen_recipe_name = st.selectbox("📖 Open Recipe Card:", options=recipe_names_list, index=current_idx)
    st.session_state.selected_recipe_name = chosen_recipe_name
    active_recipe = next((r for r in MEAT_RECIPES if r["name"] == chosen_recipe_name), MEAT_RECIPES[0])

    m_info = active_recipe["macros_per_serving"]
    missing_items = active_recipe["missing_from_kitchen"]
    missing_html = (
        "<span style='color:#4ade80; font-weight:700;'>✅ Every single pantry/spice ingredient is already in your Kitchen Inventory!</span>"
        if not missing_items
        else f"<span style='color:#facc15; font-weight:700;'>🛒 Needs from store: {', '.join(missing_items)}</span>"
    )

    st.markdown(
        f"""
        <div class="recipe-box">
            <h3 style="margin-top:0; margin-bottom:6px; color:#ffffff;">🍳 #{active_recipe['id']}: {active_recipe['name']}</h3>
            <p style="margin:0 0 8px 0; font-size:0.95rem; color:#e2e8f0;">
                <b>🥩 Meat:</b> <code>{active_recipe['meat']}</code> &nbsp;|&nbsp;
                <b>🔥 Method:</b> <code>{active_recipe['cook_method']}</code> &nbsp;|&nbsp;
                <b>⏱️ Time:</b> <code>{active_recipe['prep_time']}</code>
            </p>
            <p style="margin:0 0 8px 0; font-size:0.95rem; color:#ffffff;">
                <b>📊 Macros (per 6 oz raw / ~4.5 oz cooked meat serving):</b>
                <code>{m_info['cal']} kcal</code> • <code>{m_info['p']}g Protein</code> • <code>{m_info['f']}g Fat</code> • <code>{m_info['c']}g Carbs</code> • <code>{m_info['fib']}g Fiber</code>
            </p>
            <p style="margin:0; font-size:0.92rem;">{missing_html}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    rc_left, rc_right = st.columns([1.1, 1.9], gap="large")
    with rc_left:
        st.markdown("#### 🧂 What You Grab")
        for ing in active_recipe["kitchen_ingredients"]:
            st.markdown(f"- ✅ **{ing}**")
        for m_ing in active_recipe["missing_from_kitchen"]:
            st.markdown(f"- 🛒 **{m_ing}** *(not in inventory yet)*")
    with rc_right:
        st.markdown("#### 👨‍🍳 Dead-Simple Steps (Zero Fluff)")
        for step_num, step_text in enumerate(active_recipe["steps"], start=1):
            st.markdown(f"**Step {step_num}.** {step_text}")

# ==============================================================================
# TAB 5: WORKOUT PLAN REFERENCE
# ==============================================================================
with tab_workout:
    st.subheader("🏋️ Workout Plan Reference (`WorkoutPlan.md`)")
    if os.path.exists("WorkoutPlan.md"):
        with open("WorkoutPlan.md", "r", encoding="utf-8") as f:
            st.markdown(f.read())
