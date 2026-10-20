import os
import re
import subprocess
from typing import List, Dict, Any, Tuple
from meat_recipes import MEAT_RECIPES

# Comprehensive natural-language food database (supports both raw & cooked measurements!)
COMMON_FOOD_DB: List[Dict[str, Any]] = [
    # Eggs & Dairy
    {"keywords": ["egg white", "liquid egg whites"], "name": "H-E-B Liquid Egg Whites", "unit": "tbsp", "default_qty": 6, "cal": 8.3, "p": 1.8, "f": 0.0, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["whole egg", "eggs", "egg"], "name": "Whole Large Egg", "unit": "egg", "default_qty": 1, "cal": 70.0, "p": 6.0, "f": 5.0, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["fairlife shake", "fairlife 30g", "chocolate protein shake", "fairlife protein"], "name": "Fairlife 30g Chocolate Protein Shake", "unit": "shake", "default_qty": 1, "cal": 150.0, "p": 30.0, "f": 2.5, "c": 4.0, "fib": 1.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["premier protein", "premier shake"], "name": "Premier Protein Shake (30g)", "unit": "shake", "default_qty": 1, "cal": 160.0, "p": 30.0, "f": 3.0, "c": 5.0, "fib": 1.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["fairlife milk", "fat free milk", "milk"], "name": "Fairlife Fat-Free Milk (1 cup)", "unit": "cup", "default_qty": 1, "cal": 80.0, "p": 13.0, "f": 0.0, "c": 6.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["oikos", "yogurt", "strawberry yogurt", "greek yogurt"], "name": "Oikos Pro 20g Protein Strawberry Yogurt", "unit": "cup", "default_qty": 1, "cal": 140.0, "p": 20.0, "f": 3.0, "c": 8.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["cottage cheese"], "name": "Low-Fat Cottage Cheese (1/2 cup)", "unit": "serving", "default_qty": 1, "cal": 90.0, "p": 13.0, "f": 2.5, "c": 5.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["mozzarella"], "name": "Reduced-Fat Mozzarella Cheese (1/4 cup)", "unit": "serving", "default_qty": 1, "cal": 70.0, "p": 7.0, "f": 4.5, "c": 1.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["tillamook", "cheddar packet", "sharp cheddar"], "name": "Tillamook Sharp Cheddar Packet", "unit": "packet", "default_qty": 1, "cal": 90.0, "p": 5.0, "f": 7.0, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["babybel"], "name": "Babybel Cheese", "unit": "piece", "default_qty": 1, "cal": 70.0, "p": 5.0, "f": 5.0, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["laughing cow"], "name": "Laughing Cow Light Cheese Wedge", "unit": "wedge", "default_qty": 1, "cal": 25.0, "p": 2.0, "f": 1.5, "c": 1.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["whey", "protein powder", "scoop of protein"], "name": "Whey Protein Powder", "unit": "scoop", "default_qty": 1, "cal": 120.0, "p": 24.0, "f": 1.5, "c": 3.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["fit pb", "peanut powder", "pb2"], "name": "Fit PB Roasted Peanut Powder (2 tbsp)", "unit": "serving", "default_qty": 1, "cal": 60.0, "p": 7.0, "f": 1.5, "c": 5.0, "fib": 2.0, "is_gummy": False, "is_meat": False},

    # Meats (base values per 1 oz RAW; if measured COOKED, automatically multiplied by 1.33x since 4 oz raw -> ~3 oz cooked)
    {"keywords": ["chicken breast", "chicken"], "name": "Chicken Breast", "unit": "oz", "default_qty": 6, "cal": 30.0, "p": 6.5, "f": 0.4, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": True},
    {"keywords": ["ground beef", "93/7 beef", "taco beef", "smash patties", "beef"], "name": "93/7 Ground Beef", "unit": "oz", "default_qty": 6, "cal": 42.5, "p": 6.0, "f": 2.0, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": True},
    {"keywords": ["steak", "flat iron", "sirloin"], "name": "Sliced Steak / Flat Iron", "unit": "oz", "default_qty": 6, "cal": 40.0, "p": 6.0, "f": 1.7, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": True},
    {"keywords": ["ribeye"], "name": "Costco Ribeye Steak", "unit": "oz", "default_qty": 6, "cal": 70.0, "p": 5.5, "f": 5.2, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": True},
    {"keywords": ["shrimp"], "name": "Gulf Shrimp", "unit": "oz", "default_qty": 6, "cal": 23.0, "p": 5.3, "f": 0.2, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": True},
    {"keywords": ["pork tenderloin", "pork"], "name": "Pork Tenderloin", "unit": "oz", "default_qty": 6, "cal": 31.0, "p": 6.0, "f": 0.6, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": True},
    {"keywords": ["white fish", "tilapia", "cod", "fish"], "name": "White Fish Fillet", "unit": "oz", "default_qty": 6, "cal": 25.0, "p": 5.6, "f": 0.3, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": True},
    {"keywords": ["sliced turkey", "deli turkey", "turkey"], "name": "Sliced Deli Turkey", "unit": "oz", "default_qty": 4, "cal": 25.0, "p": 5.0, "f": 0.4, "c": 0.5, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["canned tuna", "tuna"], "name": "Canned Tuna", "unit": "can", "default_qty": 1, "cal": 110.0, "p": 25.0, "f": 1.0, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["canned chicken"], "name": "Canned Chicken", "unit": "can", "default_qty": 1, "cal": 120.0, "p": 26.0, "f": 2.0, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["bacon"], "name": "Bacon", "unit": "slice", "default_qty": 2, "cal": 40.0, "p": 3.0, "f": 3.0, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": False},

    # Grains, Bread, Oats, Pasta, Beans
    {"keywords": ["protein oatmeal", "instant oatmeal", "oatmeal packet"], "name": "H-E-B Protein Instant Oatmeal", "unit": "packet", "default_qty": 1, "cal": 170.0, "p": 10.0, "f": 2.5, "c": 27.0, "fib": 4.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["rolled oats", "oats", "oatmeal"], "name": "Rolled Oats (1/2 cup)", "unit": "serving", "default_qty": 1, "cal": 150.0, "p": 5.0, "f": 2.5, "c": 27.0, "fib": 4.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["sara lee", "delightful bread", "keto bread"], "name": "Sara Lee Delightful Bread", "unit": "slice", "default_qty": 2, "cal": 45.0, "p": 2.5, "f": 0.5, "c": 9.5, "fib": 3.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["sourdough"], "name": "Sourdough Bread", "unit": "slice", "default_qty": 1, "cal": 130.0, "p": 5.0, "f": 0.5, "c": 26.0, "fib": 1.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["bagel", "thomas bagel"], "name": "Thomas' Bagel", "unit": "bagel", "default_qty": 1, "cal": 270.0, "p": 10.0, "f": 1.5, "c": 53.0, "fib": 2.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["carb balance", "mission tortilla", "tortilla"], "name": "Mission Carb Balance Flour Tortilla", "unit": "tortilla", "default_qty": 1, "cal": 70.0, "p": 5.0, "f": 2.0, "c": 19.0, "fib": 15.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["wasa", "crispbread"], "name": "Wasa Sourdough Crispbread", "unit": "slice", "default_qty": 2, "cal": 45.0, "p": 1.5, "f": 0.25, "c": 10.0, "fib": 2.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["bibigo", "sticky rice"], "name": "Bibigo Sticky White Rice Bowl", "unit": "bowl", "default_qty": 1, "cal": 310.0, "p": 5.0, "f": 1.0, "c": 70.0, "fib": 1.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["ready rice", "ben's original", "jasmine rice", "white rice", "brown rice", "rice"], "name": "Cooked Rice (1 cup)", "unit": "cup", "default_qty": 1, "cal": 210.0, "p": 4.5, "f": 0.5, "c": 45.0, "fib": 1.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["banza", "chickpea mac"], "name": "Banza Chickpea Cheddar Mac & Cheese", "unit": "serving", "default_qty": 1, "cal": 260.0, "p": 16.0, "f": 4.5, "c": 41.0, "fib": 5.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["chickpea pasta", "chickpea elbows", "chickpea shells", "higher harvest"], "name": "Higher Harvest Chickpea Pasta (2 oz dry)", "unit": "serving", "default_qty": 1, "cal": 190.0, "p": 12.0, "f": 3.0, "c": 34.0, "fib": 8.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["barilla", "spaghetti", "pasta"], "name": "Barilla Protein+ Spaghetti (2 oz dry)", "unit": "serving", "default_qty": 1, "cal": 190.0, "p": 10.0, "f": 1.0, "c": 38.0, "fib": 5.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["black beans", "pinto beans", "kidney beans", "navy beans", "beans"], "name": "Beans (1/2 cup)", "unit": "serving", "default_qty": 1, "cal": 110.0, "p": 7.0, "f": 0.5, "c": 20.0, "fib": 6.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["edamame"], "name": "H-E-B Edamame (1 cup)", "unit": "cup", "default_qty": 1, "cal": 180.0, "p": 18.0, "f": 8.0, "c": 14.0, "fib": 8.0, "is_gummy": False, "is_meat": False},

    # Fruits, Veggies, Cereals, Snacks
    {"keywords": ["banana"], "name": "Medium Banana", "unit": "banana", "default_qty": 1, "cal": 105.0, "p": 1.3, "f": 0.4, "c": 27.0, "fib": 3.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["apple"], "name": "Medium Apple", "unit": "apple", "default_qty": 1, "cal": 95.0, "p": 0.5, "f": 0.3, "c": 25.0, "fib": 4.5, "is_gummy": False, "is_meat": False},
    {"keywords": ["orange"], "name": "Medium Orange", "unit": "orange", "default_qty": 1, "cal": 65.0, "p": 1.2, "f": 0.2, "c": 15.0, "fib": 3.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["avocado"], "name": "Avocado (1/2 medium)", "unit": "half", "default_qty": 1, "cal": 120.0, "p": 1.5, "f": 11.0, "c": 6.0, "fib": 5.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["blueberries", "blueberry"], "name": "Blueberries (1 cup)", "unit": "cup", "default_qty": 1, "cal": 80.0, "p": 1.0, "f": 0.5, "c": 19.0, "fib": 4.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["strawberries", "strawberry"], "name": "Strawberries (1 cup)", "unit": "cup", "default_qty": 1, "cal": 50.0, "p": 1.0, "f": 0.0, "c": 12.0, "fib": 3.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["kashi", "kashi go"], "name": "Kashi GO Cereal (1 cup)", "unit": "cup", "default_qty": 1, "cal": 190.0, "p": 10.0, "f": 2.5, "c": 38.0, "fib": 10.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["cheerios"], "name": "Honey Nut Cheerios Protein", "unit": "serving", "default_qty": 1, "cal": 160.0, "p": 7.0, "f": 2.5, "c": 29.0, "fib": 3.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["rice cake", "rice cakes"], "name": "Quaker Rice Cake", "unit": "cake", "default_qty": 2, "cal": 35.0, "p": 1.0, "f": 0.0, "c": 7.5, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["quest chips", "protein chips", "quest"], "name": "Quest Protein Chips (1 bag)", "unit": "bag", "default_qty": 1, "cal": 140.0, "p": 19.0, "f": 5.0, "c": 4.0, "fib": 1.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["good thins"], "name": "Good Thins Corn Snacks", "unit": "serving", "default_qty": 1, "cal": 130.0, "p": 2.0, "f": 3.5, "c": 23.0, "fib": 1.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["popcorn"], "name": "Popcorn (3 cups)", "unit": "serving", "default_qty": 1, "cal": 120.0, "p": 2.0, "f": 4.0, "c": 19.0, "fib": 3.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["halo top", "ice cream"], "name": "Halo Top Vanilla Bean (2/3 cup)", "unit": "serving", "default_qty": 1, "cal": 100.0, "p": 6.0, "f": 3.0, "c": 18.0, "fib": 2.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["peanut butter"], "name": "Peanut Butter (1 tbsp)", "unit": "tbsp", "default_qty": 1, "cal": 95.0, "p": 4.0, "f": 8.0, "c": 3.0, "fib": 1.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["olive oil", "avocado oil"], "name": "Cooking Oil (1 tsp)", "unit": "tsp", "default_qty": 1, "cal": 40.0, "p": 0.0, "f": 4.5, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["butter", "kerrygold"], "name": "Kerrygold Butter (1 tsp)", "unit": "tsp", "default_qty": 1, "cal": 34.0, "p": 0.0, "f": 3.8, "c": 0.0, "fib": 0.0, "is_gummy": False, "is_meat": False},
    {"keywords": ["fiber gummies", "fiber gummy", "gummies"], "name": "Fiber Gummies", "unit": "serving", "default_qty": 1, "cal": 30.0, "p": 0.0, "f": 0.0, "c": 10.0, "fib": 10.0, "is_gummy": True, "is_meat": False},
    {"keywords": ["burrito", "el monterey"], "name": "El Monterey Bean & Cheese Burrito", "unit": "burrito", "default_qty": 1, "cal": 300.0, "p": 10.0, "f": 9.0, "c": 44.0, "fib": 5.0, "is_gummy": False, "is_meat": False},
]

WORD_NUMS = {
    "a": 1.0,
    "an": 1.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "half": 0.5,
}


def detect_slot(segment: str, current_slot: str) -> str:
    s = segment.lower()
    if any(k in s for k in ["pre-workout", "pre workout", "preworkout", "before gym", "before lifting"]):
        return "Pre-workout"
    if any(k in s for k in ["breakfast", "morning"]):
        return "Breakfast"
    if any(k in s for k in ["lunch", "midday", "noon"]):
        return "Lunch"
    if any(k in s for k in ["dinner", "supper", "tonight", "evening"]):
        return "Dinner"
    if any(k in s for k in ["snack", "midnight", "late night", "dessert", "after dinner"]):
        return "Snacks"
    return current_slot


def extract_multiplier(phrase: str, unit: str, default_qty: float) -> Tuple[float, str]:
    p = phrase.lower()
    oz_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:oz|ounces?)", p)
    if oz_m and unit == "oz":
        val = float(oz_m.group(1))
        return val, f"{val:g} oz"

    frac_m = re.search(r"(\d+)\s*/\s*(\d+)", p)
    if frac_m:
        val = float(frac_m.group(1)) / float(frac_m.group(2))
        return val / default_qty if default_qty else val, f"{val:g} {unit}"

    num_m = re.search(r"\b(\d+(?:\.\d+)?)\b", p)
    if num_m:
        val = float(num_m.group(1))
        if val not in (93, 7, 30, 20, 70, 90, 170):
            return val, f"{val:g} {unit}"

    for w, n in WORD_NUMS.items():
        if re.search(rf"\b{w}\b", p):
            if w in ("a", "an") and unit == "oz":
                return default_qty, f"{default_qty:g} oz"
            return n, f"{n:g} {unit}"

    return default_qty, f"{default_qty:g} {unit}"


def parse_natural_language_day(text: str, default_meat_state: str = "Raw") -> List[Dict[str, Any]]:
    """
    Parse a natural-language paragraph (typed or voice-to-text) into structured meal slot rows.
    Respects 'raw' vs 'cooked' weights!
    """
    if not text.strip():
        return []

    normalized = re.sub(
        r"\b(for\s+(?:pre-?workout|breakfast|lunch|dinner|snacks?|midnight\s+snack))\b",
        r". \1",
        text,
        flags=re.IGNORECASE,
    )
    sentences = re.split(r"[.\n;]+", normalized)

    current_slot = "Breakfast"
    parsed_items: List[Dict[str, Any]] = []

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        current_slot = detect_slot(sent, current_slot)

        clauses = re.split(r"\b(?:and|plus|with)\b|,|\+", sent, flags=re.IGNORECASE)
        for clause in clauses:
            c_clean = clause.strip()
            if not c_clean:
                continue
            current_slot = detect_slot(c_clean, current_slot)

            # Check if phrase specifies "cooked" or "raw"
            is_cooked = "cooked" in c_clean.lower() or (default_meat_state == "Cooked" and "raw" not in c_clean.lower())
            state_label = "Cooked" if is_cooked else "Raw"

            # First check if it matches one of the 35 Meat Recipes by name
            matched_recipe = None
            for rec in MEAT_RECIPES:
                if rec["name"].lower() in c_clean.lower():
                    matched_recipe = rec
                    break

            if matched_recipe:
                est = matched_recipe["est_macros"]
                mult = 1.33 if is_cooked else 1.0
                parsed_items.append(
                    {
                        "Meal Slot": current_slot,
                        "Raw / Cooked": state_label,
                        "Food / Item": f"{matched_recipe['name']} ({est['portion']} - {state_label})",
                        "Calories": int(round(est["cal"] * mult)),
                        "Protein (g)": round(float(est["p"]) * mult, 1),
                        "Fat (g)": round(float(est["f"]) * mult, 1),
                        "Carbs (g)": round(float(est["c"]), 1),
                        "Fiber (g)": 0.0,
                        "Is Gummy Fiber": False,
                    }
                )
                continue

            # Otherwise match against COMMON_FOOD_DB
            matched_db = None
            for entry in COMMON_FOOD_DB:
                for kw in entry["keywords"]:
                    if re.search(rf"\b{re.escape(kw)}s?\b", c_clean.lower()):
                        matched_db = entry
                        break
                if matched_db:
                    break

            if matched_db:
                qty, qty_label = extract_multiplier(c_clean, matched_db["unit"], matched_db["default_qty"])
                # If it's meat weighed cooked, 1 oz cooked ≈ 1.33 oz raw
                cook_mult = 1.33 if (matched_db.get("is_meat") and is_cooked) else 1.0
                item_state = state_label if matched_db.get("is_meat") else "As Packaged"
                parsed_items.append(
                    {
                        "Meal Slot": current_slot,
                        "Raw / Cooked": item_state,
                        "Food / Item": f"{matched_db['name']} ({qty_label}{' ' + state_label.lower() if matched_db.get('is_meat') else ''})",
                        "Calories": int(round(matched_db["cal"] * qty * cook_mult)),
                        "Protein (g)": round(matched_db["p"] * qty * cook_mult, 1),
                        "Fat (g)": round(matched_db["f"] * qty * cook_mult, 1),
                        "Carbs (g)": round(matched_db["c"] * qty, 1),
                        "Fiber (g)": round(matched_db["fib"] * qty, 1),
                        "Is Gummy Fiber": bool(matched_db["is_gummy"]),
                    }
                )

    return parsed_items


def run_windows_ocr_on_image(image_path: str) -> str:
    """
    Use Windows 10/11 built-in native OCR (Windows.Media.Ocr) via PowerShell to extract text from a receipt image offline.
    """
    abs_path = os.path.abspath(image_path).replace("'", "''")
    ps_script = f"""
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Foundation.IAsyncOperation`1, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]

    function Await($WinRtTask, $ResultType) {{
        $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]
        $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
        $netTask = $asTask.Invoke($null, @($WinRtTask))
        $netTask.Wait(-1) | Out-Null
        $netTask.Result
    }}

    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync('{abs_path}')) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    $ocrResult = Await ($ocrEngine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    foreach ($line in $ocrResult.Lines) {{
        Write-Output $line.Text
    }}
    """
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def parse_receipt_text_into_items(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse OCR or pasted grocery receipt text into candidate items (either Raw Meat or Kitchen Inventory).
    """
    results: List[Dict[str, Any]] = []
    if not raw_text.strip():
        return results

    ignore_words = [
        "subtotal", "total", "tax", "visa", "mastercard", "debit", "credit",
        "change", "balance", "thank you", "receipt", "h-e-b", "costco", "savings",
        "coupon", "approval", "aid:", "terminal", "items sold",
    ]

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if len(line) < 3:
            continue
        low = line.lower()
        if any(w in low for w in ignore_words):
            continue

        cleaned = re.sub(r"\$?\d+\.\d{2}\s*[A-Z]*$", "", line).strip()
        cleaned = re.sub(r"^\d{4,12}\s+", "", cleaned).strip()
        if len(cleaned) < 2 or cleaned.isdigit():
            continue

        wt_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:lbs?|oz|packs?)", cleaned, flags=re.IGNORECASE)
        amount = wt_match.group(0) if wt_match else ""

        is_raw_meat = False
        cat = "Cereals, Granola & Snacks"
        if any(k in low for k in ["frozen", "nugget", "strip", "wing", "meatball"]):
            cat = "Frozen Meat & Seafood"
        elif any(k in low for k in ["chicken", "steak", "ribeye", "flat iron", "sirloin", "ground beef", "93/7", "shrimp", "pork", "tenderloin", "tilapia", "cod", "salmon", "fish"]):
            is_raw_meat = True
            cat = "Separate Raw Meat Section"
        elif any(k in low for k in ["egg", "milk", "fairlife", "premier", "yogurt", "oikos", "cheese", "cottage", "mozzarella", "butter", "whey"]):
            cat = "Dairy, Eggs & Protein Supplements"
        elif any(k in low for k in ["banana", "apple", "orange", "avocado", "carrot", "garlic", "cilantro", "berry", "blueberr", "strawberr", "edamame", "pepper", "onion"]):
            cat = "Produce (Fresh & Frozen)"
        elif any(k in low for k in ["bread", "sourdough", "bagel", "tortilla", "wasa", "sara lee"]):
            cat = "Bread, Tortillas & Bakery"
        elif any(k in low for k in ["rice", "oat", "pasta", "spaghetti", "banza", "chickpea", "mac"]):
            cat = "Grains, Rice, Oats & Pasta"
        elif any(k in low for k in ["bean", "broth", "sauce"]):
            cat = "Canned Beans, Broths & Sauces"

        results.append(
            {
                "Add": True,
                "Item Name": cleaned,
                "Destination": "🥩 Raw Meat Section" if is_raw_meat else f"📦 Kitchen ({cat})",
                "Category": cat,
                "Raw Meat Weight (if meat)": amount,
            }
        )

    return results
