import json
import os
from typing import List, Dict, Any

INVENTORY_MD_PATH = "FoodInventory.md"
INVENTORY_JSON_PATH = "InventoryData.json"
RAW_MEAT_JSON_PATH = "RawMeatStock.json"

CATEGORIES = [
    "Deli & Canned Meats",
    "Frozen Meat & Seafood",
    "Dairy, Eggs & Protein Supplements",
    "Produce (Fresh & Frozen)",
    "Bread, Tortillas & Bakery",
    "Grains, Rice, Oats & Pasta",
    "Canned Beans, Broths & Sauces",
    "Cereals, Granola & Snacks",
    "Sweets & Treats",
    "Condiments, Baking & Spices",
    "Drinks & Supplements",
]

# USDA / Cronometer / Brand-exact per-serving nutrition & smart tag hints
BASELINE_MACROS: Dict[str, Dict[str, Any]] = {
    "H-E-B Honey Turkey Breast Deli Meat (Sliced)": {"serving": "4 oz (112g)", "cal": 140, "p": 20, "f": 3.0, "c": 1, "fib": 0, "tags": "🥩 Lean Protein, 🌙 Midnight Snacks"},
    "Starkist / H-E-B Chunk Light Canned Tuna in Water": {"serving": "1 can drained", "cal": 110, "p": 25, "f": 1, "c": 0, "fib": 0, "tags": "🥩 Lean Protein"},
    "Canned White Meat Chicken Breast in Water": {"serving": "4 oz drained", "cal": 120, "p": 26, "f": 2, "c": 0, "fib": 0, "tags": "🥩 Lean Protein"},
    "H-E-B Thick Cut / Center Cut Bacon": {"serving": "2 slices pan-fried", "cal": 80, "p": 6, "f": 6, "c": 0, "fib": 0, "tags": ""},
    "H-E-B Italian Style Meatballs (Frozen, Raw)": {"serving": "3 oz (85g)", "cal": 210, "p": 14, "f": 15, "c": 4, "fib": 0, "tags": ""},
    "Foster Farms Take Out Crispy Chicken Wings (Frozen)": {"serving": "3 oz (84g)", "cal": 200, "p": 15, "f": 14, "c": 3, "fib": 0, "tags": ""},
    "Tyson White Meat Chicken Nuggets (Frozen)": {"serving": "5 nuggets (90g)", "cal": 230, "p": 13, "f": 13, "c": 14, "fib": 1, "tags": ""},
    "Tyson Crispy Chicken Breast Strips (Frozen)": {"serving": "3 oz (84g)", "cal": 210, "p": 14, "f": 11, "c": 13, "fib": 1, "tags": ""},
    "H-E-B Maple Flavor Breakfast Sausage Links/Patties (Frozen)": {"serving": "2 links / 1 patty", "cal": 180, "p": 9, "f": 15, "c": 2, "fib": 0, "tags": ""},
    "H-E-B Wild Caught Texas Gulf Shrimp (Large, Raw, Peeled, Frozen)": {"serving": "4 oz (112g)", "cal": 90, "p": 21, "f": 0.5, "c": 0, "fib": 0, "tags": "🥩 Lean Protein"},
    "Kirkland Signature (Costco) USDA Choice Ribeye Steaks (Frozen)": {"serving": "4 oz raw (112g)", "cal": 280, "p": 22, "f": 21, "c": 0, "fib": 0, "tags": ""},
    "Boneless Skinless Chicken Breast Fillets (Frozen)": {"serving": "4 oz raw (112g)", "cal": 120, "p": 26, "f": 1.5, "c": 0, "fib": 0, "tags": "🥩 Lean Protein"},
    "USDA Large Whole Eggs": {"serving": "1 large egg (50g)", "cal": 70, "p": 6, "f": 5, "c": 0, "fib": 0, "tags": "🥩 Lean Protein"},
    "H-E-B Cage-Free 100% Liquid Egg Whites": {"serving": "100g (~6 tbsp)", "cal": 50, "p": 11, "f": 0, "c": 0, "fib": 0, "tags": "🥩 Lean Protein"},
    "Fairlife Fat-Free Ultra-Filtered Lactose-Free Milk": {"serving": "1 cup (240ml)", "cal": 80, "p": 13, "f": 0, "c": 6, "fib": 0, "tags": "🥩 Lean Protein, 🌙 Midnight Snacks"},
    "Fairlife Nutrition Plan 30g Chocolate Protein Shakes": {"serving": "1 bottle (11.5 fl oz)", "cal": 150, "p": 30, "f": 2.5, "c": 4, "fib": 1, "tags": "🥩 Lean Protein, 🌙 Midnight Snacks"},
    "Premier Protein 30g Chocolate Protein Shakes": {"serving": "1 carton (11 fl oz)", "cal": 160, "p": 30, "f": 3, "c": 5, "fib": 1, "tags": "🥩 Lean Protein, 🌙 Midnight Snacks"},
    "Oikos Pro 20g Protein Cultured Ultra-Filtered Yogurt (Strawberry)": {"serving": "1 cup (150g)", "cal": 130, "p": 20, "f": 3, "c": 7, "fib": 0, "tags": "🥩 Lean Protein, 🌙 Midnight Snacks"},
    "Oikos Triple Zero Blended Greek Yogurt (100 Cal)": {"serving": "1 cup (150g)", "cal": 100, "p": 15, "f": 0, "c": 7, "fib": 0, "tags": "🥩 Lean Protein, 🌙 Midnight Snacks"},
    "H-E-B Low-Fat Small Curd Cottage Cheese": {"serving": "1/2 cup (113g)", "cal": 90, "p": 13, "f": 2.5, "c": 5, "fib": 0, "tags": "🥩 Lean Protein, 🌙 Midnight Snacks"},
    "H-E-B Reduced-Fat Shredded Mozzarella Cheese": {"serving": "1/4 cup (28g)", "cal": 70, "p": 7, "f": 4.5, "c": 1, "fib": 0, "tags": "🥩 Lean Protein"},
    "Tillamook Sharp Cheddar Individual Cheese Portions (21g Packets)": {"serving": "1 packet (21g)", "cal": 90, "p": 5, "f": 7, "c": 0, "fib": 0, "tags": "🌙 Midnight Snacks"},
    "Babybel Original Circular Wax Semisoft Cheeses": {"serving": "1 piece (21g)", "cal": 70, "p": 5, "f": 5, "c": 0, "fib": 0, "tags": "🌙 Midnight Snacks"},
    "The Laughing Cow Creamy Light Swiss Cheese Wedges": {"serving": "1 wedge (21g)", "cal": 25, "p": 2, "f": 1.5, "c": 1, "fib": 0, "tags": "🌙 Midnight Snacks"},
    "Whey Protein Isolate / Concentrate Powder": {"serving": "1 scoop (~31g)", "cal": 120, "p": 24, "f": 1.5, "c": 3, "fib": 0, "tags": "🥩 Lean Protein, 🌙 Midnight Snacks"},
    "Fit PB Organic Roasted Peanut Powder (60 kcal, 7g Protein)": {"serving": "2 tbsp (16g)", "cal": 60, "p": 7, "f": 1.5, "c": 5, "fib": 2, "tags": "🥩 Lean Protein, 🌙 Midnight Snacks"},
    "Fresh Bananas (Raw)": {"serving": "1 medium (118g)", "cal": 105, "p": 1.3, "f": 0.4, "c": 27, "fib": 3, "tags": "⚡ Pre-Workout Carbs, 🌾 High Whole-Food Fiber"},
    "H-E-B Red Apples (Fresh / Sliced)": {"serving": "1 medium (182g)", "cal": 95, "p": 0.5, "f": 0.3, "c": 25, "fib": 4.5, "tags": "🌾 High Whole-Food Fiber, ⚡ Pre-Workout Carbs, 🌙 Midnight Snacks"},
    "Fresh Navel Oranges (Raw)": {"serving": "1 medium (131g)", "cal": 65, "p": 1.2, "f": 0.2, "c": 15, "fib": 3, "tags": "🌾 High Whole-Food Fiber, ⚡ Pre-Workout Carbs"},
    "Hass Avocados (Fresh)": {"serving": "50g (~1/3 medium)", "cal": 83, "p": 1.0, "f": 7.5, "c": 4, "fib": 3.4, "tags": "🌾 High Whole-Food Fiber"},
    "Fresh Whole / Baby Carrots": {"serving": "1 cup (128g)", "cal": 50, "p": 1, "f": 0, "c": 12, "fib": 3.5, "tags": "🌾 High Whole-Food Fiber"},
    "H-E-B Premier Shelled Edamame (Frozen)": {"serving": "1 cup shelled (155g)", "cal": 180, "p": 18, "f": 8, "c": 14, "fib": 8, "tags": "🌾 High Whole-Food Fiber, 🥩 Lean Protein"},
    "H-E-B Whole Frozen Blueberries": {"serving": "1 cup (140g)", "cal": 80, "p": 1, "f": 0.5, "c": 19, "fib": 4, "tags": "🌾 High Whole-Food Fiber, ⚡ Pre-Workout Carbs, 🌙 Midnight Snacks"},
    "H-E-B Whole Frozen Strawberries": {"serving": "1 cup (140g)", "cal": 50, "p": 1, "f": 0, "c": 12, "fib": 3, "tags": "🌾 High Whole-Food Fiber, 🌙 Midnight Snacks"},
    "Thomas' Plain / Original Bagels": {"serving": "1 bagel (95g)", "cal": 270, "p": 10, "f": 1.5, "c": 53, "fib": 2, "tags": "⚡ Pre-Workout Carbs"},
    "Sara Lee Delightful 45-Calorie Keto-Friendly Bread": {"serving": "2 slices (45g)", "cal": 90, "p": 5, "f": 1, "c": 19, "fib": 6, "tags": "🌾 High Whole-Food Fiber, ⚡ Pre-Workout Carbs"},
    "H-E-B Higher Harvest Low-Carb Lifestyle Wheat Bread": {"serving": "2 slices (28g)", "cal": 60, "p": 6, "f": 1, "c": 12, "fib": 8, "tags": "🌾 High Whole-Food Fiber, ⚡ Pre-Workout Carbs"},
    "Easy Tiger Sourdough Bread": {"serving": "1 slice (40g)", "cal": 98, "p": 4, "f": 0, "c": 18.5, "fib": 1, "tags": "⚡ Pre-Workout Carbs"},
    "Mission Carb Balance Soft Taco Flour Tortillas (70 kcal)": {"serving": "1 tortilla (43g)", "cal": 70, "p": 5, "f": 2, "c": 19, "fib": 15, "tags": "🌾 High Whole-Food Fiber"},
    "Wasa Sourdough Swedish Style Crispbread Crackers": {"serving": "2 slices (28g)", "cal": 90, "p": 3, "f": 0.5, "c": 20, "fib": 4, "tags": "🌾 High Whole-Food Fiber, 🌙 Midnight Snacks"},
    "Old Fashioned Rolled Oats (Dry)": {"serving": "1/2 cup dry (40g)", "cal": 150, "p": 5, "f": 2.5, "c": 27, "fib": 4, "tags": "🌾 High Whole-Food Fiber, ⚡ Pre-Workout Carbs"},
    "H-E-B Protein Instant Oatmeal Packets (170 kcal, 10g Protein)": {"serving": "1 packet (43g)", "cal": 170, "p": 10, "f": 2.5, "c": 27, "fib": 4, "tags": "⚡ Pre-Workout Carbs, 🌾 High Whole-Food Fiber"},
    "Bibigo Cooked Sticky White Rice (Microwave Individual Bowls)": {"serving": "1 bowl (210g)", "cal": 310, "p": 5, "f": 1, "c": 70, "fib": 1, "tags": "⚡ Pre-Workout Carbs"},
    "Barilla Protein+ (10g Protein) Thin Spaghetti Pasta": {"serving": "2 oz dry (56g)", "cal": 190, "p": 10, "f": 1, "c": 38, "fib": 5, "tags": "🌾 High Whole-Food Fiber"},
    "Banza Chickpea Pasta Cheddar Mac & Cheese Shells (16g Protein)": {"serving": "2.5 oz dry", "cal": 260, "p": 16, "f": 4.5, "c": 41, "fib": 5, "tags": "🌾 High Whole-Food Fiber"},
    "Higher Harvest by H-E-B Gluten-Free Organic Chickpea Elbows (12g Protein)": {"serving": "2 oz dry (56g)", "cal": 190, "p": 12, "f": 3, "c": 34, "fib": 8, "tags": "🌾 High Whole-Food Fiber"},
    "Higher Harvest by H-E-B Gluten-Free Organic Chickpea Shells (12g Protein)": {"serving": "2 oz dry (56g)", "cal": 190, "p": 12, "f": 3, "c": 34, "fib": 8, "tags": "🌾 High Whole-Food Fiber"},
    "H-E-B Canned Black Beans (Drained / Cooked)": {"serving": "150g cooked", "cal": 171, "p": 11.5, "f": 0.7, "c": 25.5, "fib": 11, "tags": "🌾 High Whole-Food Fiber"},
    "H-E-B Canned Pinto Beans": {"serving": "1/2 cup (130g)", "cal": 110, "p": 7, "f": 0.5, "c": 20, "fib": 6, "tags": "🌾 High Whole-Food Fiber"},
    "Dark Red Kidney Beans (Canned)": {"serving": "1/2 cup (130g)", "cal": 110, "p": 7, "f": 0.5, "c": 20, "fib": 6, "tags": "🌾 High Whole-Food Fiber"},
    "Canned Navy Beans": {"serving": "1/2 cup (130g)", "cal": 110, "p": 7, "f": 0.5, "c": 20, "fib": 7, "tags": "🌾 High Whole-Food Fiber"},
    "Cento Canned Chickpeas (Garbanzo Beans)": {"serving": "1/2 cup (130g)", "cal": 120, "p": 6, "f": 2, "c": 20, "fib": 5, "tags": "🌾 High Whole-Food Fiber"},
    "Kashi GO Protein + Fiber Cereal: Mixed Berry Crunch (10g Protein, 10g Fiber)": {"serving": "1 cup (53g)", "cal": 190, "p": 10, "f": 2.5, "c": 38, "fib": 10, "tags": "🌾 High Whole-Food Fiber, ⚡ Pre-Workout Carbs, 🌙 Midnight Snacks"},
    "Kashi GO Protein + Fiber Cereal: Chocolate Crunch (10g Protein, 10g Fiber)": {"serving": "30g (~3/5 cup)", "cal": 117, "p": 6, "f": 4, "c": 12, "fib": 5.7, "tags": "🌾 High Whole-Food Fiber, ⚡ Pre-Workout Carbs, 🌙 Midnight Snacks"},
    "General Mills Cheerios Protein: Honey Nut": {"serving": "30g (~1 cup)", "cal": 114, "p": 5, "f": 1.2, "c": 16.8, "fib": 1.1, "tags": "⚡ Pre-Workout Carbs, 🌙 Midnight Snacks"},
    "Purely Elizabeth Ancient Grain Granola: Chocolate Sea Salt": {"serving": "30g (1/3 cup)", "cal": 130, "p": 3, "f": 6, "c": 17, "fib": 2, "tags": "⚡ Pre-Workout Carbs, 🌙 Midnight Snacks"},
    "Quaker Lightly Salted Rice Cakes": {"serving": "2 cakes (18g)", "cal": 70, "p": 2, "f": 0, "c": 15, "fib": 0, "tags": "⚡ Pre-Workout Carbs, 🌙 Midnight Snacks"},
    "Good Thins Gluten-Free Corn & Rice Snacks (130 kcal)": {"serving": "30g", "cal": 126, "p": 3.6, "f": 3.2, "c": 17.5, "fib": 1, "tags": "🌙 Midnight Snacks"},
    "Quest Tortilla Style Protein Chips": {"serving": "1 bag (32g)", "cal": 140, "p": 19, "f": 5, "c": 4, "fib": 1, "tags": "🥩 Lean Protein, 🌙 Midnight Snacks"},
    "Hill Country Fare Microwave Popcorn: Light Butter": {"serving": "3 cups popped", "cal": 120, "p": 2, "f": 4, "c": 19, "fib": 3, "tags": "🌾 High Whole-Food Fiber, 🌙 Midnight Snacks"},
    "Hill Country Fare Microwave Popcorn: Kettle Corn": {"serving": "3 cups popped", "cal": 130, "p": 2, "f": 4, "c": 21, "fib": 3, "tags": "🌾 High Whole-Food Fiber, 🌙 Midnight Snacks"},
    "Raw / Roasted Cashews": {"serving": "28g (1 oz)", "cal": 149, "p": 5.1, "f": 12.3, "c": 8.5, "fib": 0.9, "tags": "🌙 Midnight Snacks"},
    "Halo Top Light Ice Cream: Vanilla Bean": {"serving": "2/3 cup (85g)", "cal": 100, "p": 6, "f": 3, "c": 18, "fib": 2, "tags": "🌙 Midnight Snacks"},
    "Jell-O Sugar-Free Ready-to-Eat Strawberry Gelatin Cups": {"serving": "1 cup", "cal": 10, "p": 1, "f": 0, "c": 0, "fib": 0, "tags": "🌙 Midnight Snacks"},
    "H-E-B Vitamin Fiber Gummies (Peach, Strawberry & Berry — Max 10g Fiber/Day)": {"serving": "2 gummies", "cal": 10, "p": 0, "f": 0, "c": 0, "fib": 4, "tags": ""},
}


def parse_food_inventory_md() -> List[Dict[str, Any]]:
    """Parse FoodInventory.md into a clean list of kitchen inventory items (no in-stock or weight fields)."""
    if not os.path.exists(INVENTORY_MD_PATH):
        return []

    items: List[Dict[str, Any]] = []
    current_category = "Misc"

    with open(INVENTORY_MD_PATH, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("# "):
                current_category = line[2:].strip()
            elif line.startswith("- "):
                entry = line[2:].strip()
                base = BASELINE_MACROS.get(entry, {})
                items.append({
                    "name": entry,
                    "category": current_category,
                    "tags": base.get("tags", ""),
                    "serving_size": base.get("serving", "1 serving"),
                    "calories": float(base.get("cal", 0)),
                    "protein_g": float(base.get("p", 0)),
                    "fat_g": float(base.get("f", 0)),
                    "carbs_g": float(base.get("c", 0)),
                    "fiber_g": float(base.get("fib", 0)),
                })
    return items


def load_inventory() -> List[Dict[str, Any]]:
    """Load structured kitchen inventory from InventoryData.json, seeding from FoodInventory.md if needed."""
    if os.path.exists(INVENTORY_JSON_PATH):
        try:
            with open(INVENTORY_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            pass

    items = parse_food_inventory_md()
    save_inventory(items)
    return items


def save_inventory(items: List[Dict[str, Any]]) -> None:
    """Save kitchen inventory to InventoryData.json AND sync back to FoodInventory.md."""
    with open(INVENTORY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for cat in CATEGORIES:
        grouped[cat] = []

    for item in items:
        cat = item.get("category", "Misc")
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
