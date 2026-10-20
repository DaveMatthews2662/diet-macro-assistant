import json
import os
from typing import List, Dict, Any

INVENTORY_MD_PATH = "FoodInventory.md"
INVENTORY_JSON_PATH = "InventoryData.json"
RAW_MEAT_JSON_PATH = "RawMeatStock.json"

CATEGORIES = [
    "Frozen Meat & Seafood",
    "Dairy & Refrigerated",
    "Produce",
    "Bakery & Bread",
    "Pantry & Canned",
    "Frozen",
    "Desserts, Candy & Snacks",
    "Oils & Condiments",
    "Baking & Grains",
    "Drinks",
    "Spices & Seasonings",
]

SIDEBAR_FILTER_OPTIONS = [
    "All",
    "Frozen Meat & Seafood",
    "Dairy & Refrigerated",
    "Produce",
    "Bakery & Bread",
    "Pantry & Canned",
    "Frozen",
    "Desserts, Candy & Snacks",
    "Oils & Condiments",
    "Baking & Grains",
    "Drinks",
    "Spices & Seasonings",
    "Good Protein Options",
    "Good Fat Options",
    "Good Carb Options",
    "Good Fiber Options",
]


def load_inventory() -> List[Dict[str, Any]]:
    """Load structured kitchen inventory from InventoryData.json."""
    if os.path.exists(INVENTORY_JSON_PATH):
        try:
            with open(INVENTORY_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            pass
    return []


def save_inventory(items: List[Dict[str, Any]]) -> None:
    """Save kitchen inventory to InventoryData.json AND sync back to FoodInventory.md."""
    with open(INVENTORY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)

    grouped: Dict[str, List[Dict[str, Any]]] = {cat: [] for cat in CATEGORIES}
    for item in items:
        cat = item.get("category", "Pantry & Canned")
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(item)

    lines: List[str] = []
    for cat, cat_items in grouped.items():
        if not cat_items:
            continue
        lines.append(f"# {cat}")
        for it in cat_items:
            name = it.get("name", "").strip()
            if name:
                lines.append(f"- {name}")
        lines.append("")

    with open(INVENTORY_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")

    try:
        from github_sync import sync_file_to_github
        sync_file_to_github(INVENTORY_JSON_PATH, "Sync InventoryData.json from dashboard")
        sync_file_to_github(INVENTORY_MD_PATH, "Sync FoodInventory.md from dashboard")
    except Exception:
        pass


def load_raw_meats() -> List[Dict[str, Any]]:
    """Load separate Raw Meat stock."""
    if os.path.exists(RAW_MEAT_JSON_PATH):
        try:
            with open(RAW_MEAT_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_raw_meats(raw_meats: List[Dict[str, Any]]) -> None:
    """Save separate Raw Meat stock to RawMeatStock.json."""
    with open(RAW_MEAT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(raw_meats, f, indent=2)

    try:
        from github_sync import sync_file_to_github
        sync_file_to_github(RAW_MEAT_JSON_PATH, "Sync RawMeatStock.json from dashboard")
    except Exception:
        pass
