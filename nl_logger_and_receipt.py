import os
import re
import subprocess
from typing import List, Dict, Any, Tuple

MEAL_GROUPS = [
    "Pre Workout",
    "Breakfast",
    "Lunch",
    "Dinner",
    "Snacks",
    "Midnight Snacks",
    "Gummy fibers",
]

UNIT_OPTIONS = [
    "g",
    "oz",
    "fl oz",
    "cups",
    "1 unit",
    "bottle",
    "can",
    "scoop",
    "packet",
    "slice",
    "piece",
    "tbsp",
    "tsp",
    "serving",
    "gummies",
]

# Comprehensive natural-language food database (includes automatic water_oz per unit!)
COMMON_FOOD_DB: List[Dict[str, Any]] = [
    # Water & Zero-Cal Drinks (measured in 1 unit or oz)
    {"keywords": ["water", "ewater", "h2o"], "group": "Snacks", "meal": "Water", "ingredient": "Plain Drinking Water", "unit": "oz", "default_qty": 16.0, "cal": 0.0, "p": 0.0, "f": 0.0, "c": 0.0, "fib": 0.0, "water_oz": 1.0},
    {"keywords": ["gatorade", "g zero"], "group": "Pre Workout", "meal": "Gatorade Zero", "ingredient": "G Zero Gatorade, All Flavors", "unit": "1 unit", "default_qty": 1.0, "cal": 3.0, "p": 0.0, "f": 0.0, "c": 1.0, "fib": 0.0, "water_oz": 20.0},
    {"keywords": ["root beer", "diet soda", "zero soda"], "group": "Snacks", "meal": "Zero Cal Soda", "ingredient": "A&W Root Beer Zero Sugar", "unit": "1 unit", "default_qty": 1.0, "cal": 0.0, "p": 0.0, "f": 0.0, "c": 0.0, "fib": 0.0, "water_oz": 16.9},

    # Liquids & Shakes
    {"keywords": ["fairlife milk", "fat free milk", "milk"], "group": "Breakfast", "meal": "Milk", "ingredient": "Fairlife Fat-Free Ultra-Filtered Milk", "unit": "cups", "default_qty": 1.0, "cal": 80.0, "p": 13.0, "f": 0.0, "c": 6.0, "fib": 0.0, "water_oz": 7.5},
    {"keywords": ["fairlife shake", "fairlife 30g", "chocolate protein shake"], "group": "Snacks", "meal": "Protein Shake", "ingredient": "Fairlife 30g Chocolate Protein Shake", "unit": "1 unit", "default_qty": 1.0, "cal": 150.0, "p": 30.0, "f": 2.5, "c": 4.0, "fib": 1.0, "water_oz": 9.0},
    {"keywords": ["premier protein", "premier shake"], "group": "Snacks", "meal": "Protein Shake", "ingredient": "Premier Protein Shake, Chocolate", "unit": "1 unit", "default_qty": 1.0, "cal": 161.0, "p": 31.4, "f": 2.5, "c": 0.0, "fib": 1.0, "water_oz": 8.5},
    {"keywords": ["egg white", "liquid egg whites"], "group": "Breakfast", "meal": "Eggs", "ingredient": "H-E-B Cage-Free Liquid Egg Whites", "unit": "g", "default_qty": 100.0, "cal": 0.50, "p": 0.11, "f": 0.0, "c": 0.0, "fib": 0.0, "water_oz": 0.03},
    {"keywords": ["beef broth", "broth"], "group": "Dinner", "meal": "Beef Broth", "ingredient": "H-E-B Beef Broth", "unit": "cups", "default_qty": 1.0, "cal": 15.0, "p": 3.0, "f": 0.0, "c": 1.0, "fib": 0.0, "water_oz": 7.8},

    # Solid Foods (measured in grams - cal/macros/water_oz per 1g)
    {"keywords": ["whole egg", "eggs", "egg"], "group": "Breakfast", "meal": "Eggs", "ingredient": "USDA Large Whole Eggs", "unit": "g", "default_qty": 150.0, "cal": 1.4, "p": 0.12, "f": 0.10, "c": 0.0, "fib": 0.0, "water_oz": 0.025},
    {"keywords": ["oikos", "yogurt", "strawberry yogurt", "greek yogurt"], "group": "Breakfast", "meal": "Yogurt", "ingredient": "Oikos Pro 20g Protein Strawberry Yogurt", "unit": "g", "default_qty": 150.0, "cal": 0.87, "p": 0.133, "f": 0.02, "c": 0.047, "fib": 0.0, "water_oz": 0.027},
    {"keywords": ["cottage cheese"], "group": "Snacks", "meal": "Cottage Cheese", "ingredient": "H-E-B Low-Fat Cottage Cheese", "unit": "g", "default_qty": 113.0, "cal": 0.80, "p": 0.115, "f": 0.022, "c": 0.044, "fib": 0.0, "water_oz": 0.027},
    {"keywords": ["mozzarella"], "group": "Lunch", "meal": "Cheese", "ingredient": "H-E-B Reduced-Fat Shredded Mozzarella", "unit": "g", "default_qty": 28.0, "cal": 2.5, "p": 0.25, "f": 0.16, "c": 0.035, "fib": 0.0, "water_oz": 0.016},
    {"keywords": ["tillamook", "cheddar packet", "sharp cheddar"], "group": "Snacks", "meal": "Cheese", "ingredient": "Tillamook Sharp Cheddar Packet", "unit": "g", "default_qty": 21.0, "cal": 4.28, "p": 0.238, "f": 0.333, "c": 0.0, "fib": 0.0, "water_oz": 0.012},
    {"keywords": ["babybel"], "group": "Snacks", "meal": "Cheese", "ingredient": "Babybel Original Cheese Round", "unit": "g", "default_qty": 21.0, "cal": 3.33, "p": 0.238, "f": 0.238, "c": 0.0, "fib": 0.0, "water_oz": 0.015},
    {"keywords": ["laughing cow"], "group": "Midnight Snacks", "meal": "Cheese", "ingredient": "The Laughing Cow Light Wedge", "unit": "g", "default_qty": 21.0, "cal": 1.32, "p": 0.095, "f": 0.071, "c": 0.047, "fib": 0.0, "water_oz": 0.020},
    {"keywords": ["whey", "protein powder"], "group": "Pre Workout", "meal": "Protein Shake", "ingredient": "Whey Protein Powder", "unit": "g", "default_qty": 31.0, "cal": 3.87, "p": 0.774, "f": 0.048, "c": 0.097, "fib": 0.0, "water_oz": 0.0},
    {"keywords": ["fit pb", "peanut powder", "pb2"], "group": "Breakfast", "meal": "Peanut Powder", "ingredient": "Fit PB Organic Roasted Peanut Powder", "unit": "g", "default_qty": 16.0, "cal": 3.75, "p": 0.438, "f": 0.094, "c": 0.312, "fib": 0.125, "water_oz": 0.0},

    # Meats (in grams)
    {"keywords": ["chicken breast", "chicken"], "group": "Dinner", "meal": "Chicken", "ingredient": "Chicken Breast", "unit": "g", "default_qty": 170.0, "cal": 1.20, "p": 0.23, "f": 0.02, "c": 0.0, "fib": 0.0, "water_oz": 0.023},
    {"keywords": ["ground beef", "93/7 beef", "taco beef", "smash patties", "beef"], "group": "Dinner", "meal": "Ground Beef", "ingredient": "93/7 Lean Ground Beef", "unit": "g", "default_qty": 170.0, "cal": 1.50, "p": 0.21, "f": 0.07, "c": 0.0, "fib": 0.0, "water_oz": 0.022},
    {"keywords": ["steak", "flat iron", "sirloin", "top round"], "group": "Dinner", "meal": "Steak", "ingredient": "Lean Steak / Top Round", "unit": "g", "default_qty": 170.0, "cal": 1.65, "p": 0.26, "f": 0.06, "c": 0.0, "fib": 0.0, "water_oz": 0.021},
    {"keywords": ["ribeye"], "group": "Dinner", "meal": "Ribeye Steak", "ingredient": "Costco USDA Choice Ribeye Steak", "unit": "g", "default_qty": 170.0, "cal": 2.50, "p": 0.20, "f": 0.19, "c": 0.0, "fib": 0.0, "water_oz": 0.019},
    {"keywords": ["shrimp"], "group": "Dinner", "meal": "Shrimp", "ingredient": "Shrimp, Cooked from Fresh", "unit": "g", "default_qty": 150.0, "cal": 0.99, "p": 0.24, "f": 0.003, "c": 0.0, "fib": 0.0, "water_oz": 0.025},
    {"keywords": ["pork tenderloin", "pork"], "group": "Dinner", "meal": "Pork Tenderloin", "ingredient": "Pork Tenderloin", "unit": "g", "default_qty": 170.0, "cal": 1.20, "p": 0.22, "f": 0.03, "c": 0.0, "fib": 0.0, "water_oz": 0.024},
    {"keywords": ["white fish", "tilapia", "cod", "fish"], "group": "Dinner", "meal": "White Fish", "ingredient": "White Fish Fillet", "unit": "g", "default_qty": 170.0, "cal": 0.96, "p": 0.20, "f": 0.015, "c": 0.0, "fib": 0.0, "water_oz": 0.026},
    {"keywords": ["sliced turkey", "deli turkey", "honey turkey", "turkey"], "group": "Lunch", "meal": "Turkey", "ingredient": "H-E-B Honey Turkey Breast Deli Meat", "unit": "g", "default_qty": 112.0, "cal": 1.25, "p": 0.172, "f": 0.027, "c": 0.006, "fib": 0.0, "water_oz": 0.025},
    {"keywords": ["canned tuna", "tuna"], "group": "Lunch", "meal": "Tuna", "ingredient": "Canned Chunk Light Tuna", "unit": "g", "default_qty": 113.0, "cal": 0.97, "p": 0.22, "f": 0.009, "c": 0.0, "fib": 0.0, "water_oz": 0.025},
    {"keywords": ["canned chicken"], "group": "Lunch", "meal": "Canned Chicken", "ingredient": "Canned Chicken Breast", "unit": "g", "default_qty": 112.0, "cal": 1.07, "p": 0.23, "f": 0.018, "c": 0.0, "fib": 0.0, "water_oz": 0.024},
    {"keywords": ["bacon"], "group": "Breakfast", "meal": "Bacon", "ingredient": "H-E-B Bacon", "unit": "g", "default_qty": 24.0, "cal": 3.33, "p": 0.25, "f": 0.25, "c": 0.0, "fib": 0.0, "water_oz": 0.010},

    # Breads, Grains, Beans, Fruits, Snacks
    {"keywords": ["higher harvest bread", "low-carb bread", "wheat bread"], "group": "Lunch", "meal": "Sandwich / Toast", "ingredient": "H-E-B Higher Harvest Low-Carb Wheat Bread", "unit": "g", "default_qty": 28.0, "cal": 2.14, "p": 0.214, "f": 0.036, "c": 0.428, "fib": 0.285, "water_oz": 0.012},
    {"keywords": ["sara lee", "delightful bread", "keto bread"], "group": "Lunch", "meal": "Sandwich / Toast", "ingredient": "Sara Lee Delightful Keto-Friendly Bread", "unit": "g", "default_qty": 45.0, "cal": 2.0, "p": 0.111, "f": 0.022, "c": 0.422, "fib": 0.133, "water_oz": 0.012},
    {"keywords": ["sourdough"], "group": "Lunch", "meal": "Toast", "ingredient": "Easy Tiger Sourdough Bread", "unit": "g", "default_qty": 40.0, "cal": 2.45, "p": 0.10, "f": 0.0, "c": 0.462, "fib": 0.025, "water_oz": 0.012},
    {"keywords": ["bagel"], "group": "Pre Workout", "meal": "Bagel", "ingredient": "Thomas' Plain Bagel", "unit": "g", "default_qty": 95.0, "cal": 2.84, "p": 0.105, "f": 0.016, "c": 0.558, "fib": 0.021, "water_oz": 0.011},
    {"keywords": ["carb balance", "mission tortilla", "tortilla"], "group": "Dinner", "meal": "Tacos / Wrap", "ingredient": "Mission Carb Balance Flour Tortilla", "unit": "g", "default_qty": 43.0, "cal": 1.63, "p": 0.116, "f": 0.046, "c": 0.442, "fib": 0.348, "water_oz": 0.010},
    {"keywords": ["protein oatmeal", "instant oatmeal", "oatmeal packet"], "group": "Breakfast", "meal": "Oatmeal", "ingredient": "H-E-B Protein Instant Oatmeal", "unit": "g", "default_qty": 43.0, "cal": 3.95, "p": 0.232, "f": 0.058, "c": 0.628, "fib": 0.093, "water_oz": 0.0},
    {"keywords": ["rolled oats", "oats", "oatmeal"], "group": "Breakfast", "meal": "Oatmeal", "ingredient": "Old Fashioned Rolled Oats", "unit": "g", "default_qty": 40.0, "cal": 3.75, "p": 0.125, "f": 0.062, "c": 0.675, "fib": 0.10, "water_oz": 0.0},
    {"keywords": ["bibigo", "sticky rice"], "group": "Dinner", "meal": "Rice Bowl", "ingredient": "Bibigo Cooked Sticky White Rice", "unit": "g", "default_qty": 210.0, "cal": 1.48, "p": 0.024, "f": 0.005, "c": 0.333, "fib": 0.005, "water_oz": 0.022},
    {"keywords": ["rice", "white rice", "jasmine rice", "brown rice"], "group": "Dinner", "meal": "Rice", "ingredient": "Rice, White, Cooked", "unit": "g", "default_qty": 100.0, "cal": 1.47, "p": 0.03, "f": 0.003, "c": 0.30, "fib": 0.005, "water_oz": 0.023},
    {"keywords": ["black beans", "pinto beans", "kidney beans", "navy beans", "beans"], "group": "Dinner", "meal": "Beans", "ingredient": "Black Beans, Dried, Cooked", "unit": "g", "default_qty": 130.0, "cal": 1.14, "p": 0.077, "f": 0.005, "c": 0.17, "fib": 0.073, "water_oz": 0.022},
    {"keywords": ["banana"], "group": "Pre Workout", "meal": "Banana", "ingredient": "Fresh Banana", "unit": "g", "default_qty": 118.0, "cal": 0.89, "p": 0.011, "f": 0.003, "c": 0.228, "fib": 0.026, "water_oz": 0.025},
    {"keywords": ["apple"], "group": "Pre Workout", "meal": "Apple", "ingredient": "H-E-B Red Apples, Sliced", "unit": "g", "default_qty": 182.0, "cal": 0.545, "p": 0.003, "f": 0.002, "c": 0.136, "fib": 0.024, "water_oz": 0.029},
    {"keywords": ["orange"], "group": "Snacks", "meal": "Orange", "ingredient": "Fresh Navel Orange", "unit": "g", "default_qty": 131.0, "cal": 0.47, "p": 0.009, "f": 0.001, "c": 0.118, "fib": 0.024, "water_oz": 0.029},
    {"keywords": ["avocado", "avacado"], "group": "Lunch", "meal": "Avocado", "ingredient": "Hass Avocado", "unit": "g", "default_qty": 50.0, "cal": 1.67, "p": 0.02, "f": 0.15, "c": 0.08, "fib": 0.068, "water_oz": 0.024},
    {"keywords": ["kashi", "kashi go"], "group": "Breakfast", "meal": "Cereal", "ingredient": "Kashi GO Protein + Fiber Cereal", "unit": "g", "default_qty": 30.0, "cal": 3.89, "p": 0.20, "f": 0.133, "c": 0.40, "fib": 0.19, "water_oz": 0.0},
    {"keywords": ["cheerios"], "group": "Midnight Snacks", "meal": "Cereal", "ingredient": "General Mills Cheerios Protein, Honey Nut", "unit": "g", "default_qty": 30.0, "cal": 3.78, "p": 0.167, "f": 0.04, "c": 0.56, "fib": 0.037, "water_oz": 0.0},
    {"keywords": ["granola", "purely elizabeth"], "group": "Breakfast", "meal": "Granola", "ingredient": "Purely Elizabeth Chocolate Sea Salt Granola", "unit": "g", "default_qty": 30.0, "cal": 4.33, "p": 0.10, "f": 0.20, "c": 0.567, "fib": 0.067, "water_oz": 0.0},
    {"keywords": ["cashew", "cashews"], "group": "Snacks", "meal": "Cashews", "ingredient": "Cashews, Raw", "unit": "g", "default_qty": 28.0, "cal": 5.33, "p": 0.182, "f": 0.439, "c": 0.303, "fib": 0.032, "water_oz": 0.002},
    {"keywords": ["good thins"], "group": "Midnight Snacks", "meal": "Crackers", "ingredient": "Good Thins Gluten-Free Snacks", "unit": "g", "default_qty": 30.0, "cal": 4.19, "p": 0.12, "f": 0.107, "c": 0.583, "fib": 0.033, "water_oz": 0.0},
    {"keywords": ["quest", "protein chips"], "group": "Snacks", "meal": "Chips", "ingredient": "Quest Protein Chips", "unit": "g", "default_qty": 32.0, "cal": 4.38, "p": 0.594, "f": 0.156, "c": 0.125, "fib": 0.031, "water_oz": 0.0},
    {"keywords": ["butter", "kerrygold"], "group": "Dinner", "meal": "Butter", "ingredient": "Kerrygold Salted Butter", "unit": "g", "default_qty": 14.0, "cal": 7.14, "p": 0.0, "f": 0.80, "c": 0.0, "fib": 0.0, "water_oz": 0.005},
    {"keywords": ["olive oil", "avocado oil"], "group": "Dinner", "meal": "Oil", "ingredient": "Extra Virgin Olive Oil", "unit": "g", "default_qty": 13.0, "cal": 9.18, "p": 0.0, "f": 1.0, "c": 0.0, "fib": 0.0, "water_oz": 0.0},
    {"keywords": ["fiber gummies", "fiber gummy", "gummies"], "group": "Gummy fibers", "meal": "Fiber Gummies", "ingredient": "H-E-B Vitamin Fiber Gummies", "unit": "gummies", "default_qty": 2.0, "cal": 5.0, "p": 0.0, "f": 0.0, "c": 0.0, "fib": 2.0, "water_oz": 0.0},
]


def parse_amount_from_text(phrase: str, unit: str, default_qty: float) -> Tuple[float, str]:
    p = phrase.lower()
    if unit in ("1 unit", "gummies"):
        num_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:units?|bottles?|cans?|shakes?|gummies|gummy)?\b", p)
        if num_m:
            return float(num_m.group(1)), unit
        return default_qty, unit

    if unit == "oz":
        oz_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:fl\s*oz|oz|ounces?)", p)
        if oz_m:
            return float(oz_m.group(1)), "oz"
        cup_m = re.search(r"(\d+(?:\.\d+)?)\s*cups?", p)
        if cup_m:
            return float(cup_m.group(1)) * 8.0, "oz"
        return default_qty, "oz"

    if unit == "cups":
        cup_m = re.search(r"(\d+(?:\.\d+)?)\s*cups?", p)
        if cup_m:
            return float(cup_m.group(1)), "cups"
        oz_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:fl\s*oz|oz|ounces?)", p)
        if oz_m:
            return round(float(oz_m.group(1)) / 8.0, 2), "cups"
        return default_qty, "cups"

    g_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:g|grams?)\b", p)
    if g_m:
        return float(g_m.group(1)), "g"

    oz_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:oz|ounces?)\b", p)
    if oz_m:
        grams = round(float(oz_m.group(1)) * 28.35)
        return float(grams), "g"

    return default_qty, unit


def parse_natural_language_day(text: str, default_group: str = "Snacks") -> List[Dict[str, Any]]:
    if not text.strip():
        return []

    parsed_items: List[Dict[str, Any]] = []

    for raw_line in re.split(r"[\n;]+", text):
        line = raw_line.strip()
        if not line:
            continue

        dash_parts = [p.strip() for p in line.split("-") if p.strip()]
        explicit_meal = dash_parts[0].title() if len(dash_parts) >= 2 else None
        search_target = " ".join(dash_parts[1:]) if len(dash_parts) >= 2 else line

        clauses = [search_target] if explicit_meal else re.split(r"\b(?:and|plus|with)\b|,|\+", line, flags=re.IGNORECASE)
        for clause in clauses:
            c_clean = clause.strip()
            if not c_clean:
                continue

            matched_db = None
            for entry in COMMON_FOOD_DB:
                for kw in entry["keywords"]:
                    if re.search(rf"\b{re.escape(kw)}s?\b", c_clean.lower()):
                        matched_db = entry
                        break
                if matched_db:
                    break

            if matched_db:
                qty, unit_label = parse_amount_from_text(c_clean, matched_db["unit"], matched_db["default_qty"])
                meal_label = explicit_meal if explicit_meal else matched_db["meal"]
                grp = "Gummy fibers" if matched_db.get("group") == "Gummy fibers" else (default_group or matched_db.get("group", "Snacks"))
                parsed_items.append(
                    {
                        "Group": grp,
                        "Meal": meal_label,
                        "Ingredient": matched_db["ingredient"],
                        "Amount": float(qty),
                        "Unit": unit_label,
                        "Calories": int(round(matched_db["cal"] * qty)),
                        "Protein": round(matched_db["p"] * qty, 1),
                        "Fat": round(matched_db["f"] * qty, 1),
                        "Carbs": round(matched_db["c"] * qty, 1),
                        "Fiber": round(matched_db["fib"] * qty, 1),
                        "Water (oz)": round(matched_db.get("water_oz", 0.0) * qty, 1),
                    }
                )

    return parsed_items


def run_windows_ocr_on_image(image_path: str) -> str:
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
        cat = "Desserts, Candy & Snacks"
        if any(k in low for k in ["frozen", "nugget", "strip", "wing", "meatball"]):
            cat = "Frozen Meat & Seafood"
        elif any(k in low for k in ["chicken", "steak", "ribeye", "flat iron", "sirloin", "ground beef", "93/7", "shrimp", "pork", "tenderloin", "tilapia", "cod", "salmon", "fish"]):
            is_raw_meat = True
            cat = "Separate Raw Meat Section"
        elif any(k in low for k in ["egg", "milk", "fairlife", "premier", "yogurt", "oikos", "cheese", "cottage", "mozzarella", "butter", "whey"]):
            cat = "Dairy & Refrigerated"
        elif any(k in low for k in ["banana", "apple", "orange", "avocado", "carrot", "garlic", "cilantro"]):
            cat = "Produce"
        elif any(k in low for k in ["bread", "sourdough", "bagel", "tortilla", "wasa", "sara lee"]):
            cat = "Bakery & Bread"
        elif any(k in low for k in ["rice", "oat", "pasta", "spaghetti", "banza", "chickpea", "mac", "bean", "broth", "sauce"]):
            cat = "Pantry & Canned"

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
