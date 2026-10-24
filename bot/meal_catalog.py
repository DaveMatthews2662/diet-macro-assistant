import json
import os
from typing import Dict, List, Any

ROTATION_FILE = "rotation_state.json"

# ==============================================================================
# LARGE ROTATING CATALOG OF SIMPLE MEALS & SNACKS ACROSS ALL 5 SLOTS
# Every option uses items from FoodInventory.md + Liked Foods (Section 8).
# Any item not currently in FoodInventory.md is flagged in `need_to_buy`.
# ==============================================================================

MEAL_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    "Pre-Workout": [
        {
            "id": "pre_1",
            "name": "PBfit & Banana Sourdough Toast",
            "prep": "Toast sourdough, mix PBfit with a splash of water into peanut butter, spread and top with sliced banana.",
            "need_to_buy": [],
            "items": [
                {"item": "Easy Tiger Sourdough Bread", "portion": "1 slice (58g)", "cal": 150, "p": 6.0, "c": 29.0, "f": 0.8, "fib": 1.0},
                {"item": "PBfit Peanut Butter Protein Powder", "portion": "2 tbsp (16g)", "cal": 70, "p": 8.0, "c": 6.0, "f": 2.0, "fib": 2.0},
                {"item": "Fresh Bananas (Raw)", "portion": "1 medium (118g)", "cal": 105, "p": 1.3, "c": 27.0, "f": 0.4, "fib": 3.1},
            ],
        },
        {
            "id": "pre_2",
            "name": "Apple Slices + Premier Chocolate Protein Shake + Gatorade Zero",
            "prep": "Grab-and-go shake, sliced red apple, and cold Gatorade Zero.",
            "need_to_buy": [],
            "items": [
                {"item": "H-E-B Red Apples (Fresh / Sliced)", "portion": "1 medium apple (182g)", "cal": 95, "p": 0.5, "c": 25.0, "f": 0.3, "fib": 4.4},
                {"item": "Premier Protein 30g Chocolate Protein Shakes", "portion": "1 shake (11 fl oz)", "cal": 160, "p": 30.0, "c": 5.0, "f": 3.0, "fib": 1.0},
                {"item": "Gatorade Zero (G Zero, All Flavors, 20 fl oz)", "portion": "1 bottle (20 fl oz)", "cal": 5, "p": 0.0, "c": 1.0, "f": 0.0, "fib": 0.0},
            ],
        },
        {
            "id": "pre_3",
            "name": "Kashi Mixed Berry Protein Cereal with Fairlife Milk",
            "prep": "Pour Kashi cereal and cold Fairlife fat-free milk into a bowl.",
            "need_to_buy": [],
            "items": [
                {"item": "Kashi GO Protein + Fiber Cereal: Mixed Berry Crunch", "portion": "1 cup (53g)", "cal": 190, "p": 10.0, "c": 37.0, "f": 2.0, "fib": 10.0},
                {"item": "Fairlife Fat-Free Ultra-Filtered Lactose-Free Milk", "portion": "1 cup (240ml)", "cal": 80, "p": 13.0, "c": 6.0, "f": 0.0, "fib": 0.0},
            ],
        },
        {
            "id": "pre_4",
            "name": "Rice Cakes with PBfit & Strawberry Jelly",
            "prep": "Mix PBfit with water, spread over 2 lightly salted rice cakes, and top with strawberry jelly.",
            "need_to_buy": [],
            "items": [
                {"item": "Quaker Lightly Salted Rice Cakes", "portion": "2 cakes (18g)", "cal": 70, "p": 1.4, "c": 15.0, "f": 0.5, "fib": 0.6},
                {"item": "PBfit Peanut Butter Protein Powder", "portion": "2 tbsp (16g)", "cal": 70, "p": 8.0, "c": 6.0, "f": 2.0, "fib": 2.0},
                {"item": "Strawberry Jelly / Jam", "portion": "1 tbsp (20g)", "cal": 50, "p": 0.0, "c": 13.0, "f": 0.0, "fib": 0.0},
            ],
        },
        {
            "id": "pre_5",
            "name": "H-E-B Protein Instant Oatmeal + Cinnamon Applesauce",
            "prep": "Microwave protein oatmeal packet with water or Fairlife milk; stir in cinnamon applesauce.",
            "need_to_buy": [],
            "items": [
                {"item": "H-E-B Protein Instant Oatmeal Packets", "portion": "1 packet (45g)", "cal": 170, "p": 10.0, "c": 27.0, "f": 3.0, "fib": 4.0},
                {"item": "Unsweetened / Cinnamon Applesauce", "portion": "1 cup (113g)", "cal": 50, "p": 0.0, "c": 13.0, "f": 0.0, "fib": 2.0},
            ],
        },
        {
            "id": "pre_6",
            "name": "Oikos Triple Zero Vanilla Greek Yogurt + Banana",
            "prep": "Slice fresh banana into a cup of Oikos Triple Zero Vanilla Greek yogurt.",
            "need_to_buy": [],
            "items": [
                {"item": "Oikos Triple Zero 15g Protein Greek Yogurt (Vanilla)", "portion": "1 cup (150g)", "cal": 100, "p": 15.0, "c": 7.0, "f": 0.0, "fib": 0.0},
                {"item": "Fresh Bananas (Raw)", "portion": "1 medium (118g)", "cal": 105, "p": 1.3, "c": 27.0, "f": 0.4, "fib": 3.1},
            ],
        },
        {
            "id": "pre_7",
            "name": "Cheerios Protein Honey Nut + Fairlife Milk",
            "prep": "Pour Cheerios Protein and cold Fairlife fat-free milk.",
            "need_to_buy": [],
            "items": [
                {"item": "General Mills Cheerios Protein: Honey Nut", "portion": "1.25 cups (55g)", "cal": 210, "p": 8.0, "c": 42.0, "f": 2.0, "fib": 3.0},
                {"item": "Fairlife Fat-Free Ultra-Filtered Lactose-Free Milk", "portion": "1 cup (240ml)", "cal": 80, "p": 13.0, "c": 6.0, "f": 0.0, "fib": 0.0},
            ],
        },
        {
            "id": "pre_8",
            "name": "Fresh Navel Orange + Kirkland Chocolate Chip Cookie Dough Protein Bar",
            "prep": "Peel the orange and unwrap the Kirkland protein bar.",
            "need_to_buy": [],
            "items": [
                {"item": "Fresh Navel Oranges (Raw)", "portion": "1 medium orange (140g)", "cal": 69, "p": 1.3, "c": 17.5, "f": 0.2, "fib": 3.1},
                {"item": "Kirkland Signature Protein Bar (Chocolate Chip Cookie Dough)", "portion": "1 bar (60g)", "cal": 190, "p": 21.0, "c": 22.0, "f": 7.0, "fib": 10.0},
            ],
        },
    ],
    "Breakfast": [
        {
            "id": "bf_1",
            "name": "Avocado Sourdough Toast + Scrambled Eggs & Egg Whites",
            "prep": "Toast sourdough, mash fresh avocado with Everything Bagel seasoning, and scramble eggs + egg whites in a pan.",
            "need_to_buy": [],
            "items": [
                {"item": "Easy Tiger Sourdough Bread", "portion": "1 slice (58g)", "cal": 150, "p": 6.0, "c": 29.0, "f": 0.8, "fib": 1.0},
                {"item": "Hass Avocados (Fresh)", "portion": "70g mashed", "cal": 112, "p": 1.4, "c": 6.0, "f": 10.3, "fib": 4.7},
                {"item": "USDA Large Whole Eggs", "portion": "2 large eggs (100g)", "cal": 143, "p": 12.6, "c": 0.7, "f": 9.5, "fib": 0.0},
                {"item": "H-E-B Cage-Free 100% Liquid Egg Whites", "portion": "150g (~2/3 cup)", "cal": 81, "p": 16.3, "c": 0.0, "f": 0.0, "fib": 0.0},
            ],
        },
        {
            "id": "bf_2",
            "name": "PBfit Sourdough Toast + Oikos Greek Yogurt & Granola Bowl",
            "prep": "Mix PBfit with water and spread on toasted sourdough. Serve alongside Oikos Triple Zero topped with Purely Elizabeth granola & berries.",
            "need_to_buy": [],
            "items": [
                {"item": "Easy Tiger Sourdough Bread", "portion": "1 slice (58g)", "cal": 150, "p": 6.0, "c": 29.0, "f": 0.8, "fib": 1.0},
                {"item": "PBfit Peanut Butter Protein Powder", "portion": "2 tbsp (16g)", "cal": 70, "p": 8.0, "c": 6.0, "f": 2.0, "fib": 2.0},
                {"item": "Oikos Triple Zero 15g Protein Greek Yogurt (Mixed Berry)", "portion": "1 cup (150g)", "cal": 100, "p": 15.0, "c": 7.0, "f": 0.0, "fib": 0.0},
                {"item": "Purely Elizabeth Ancient Grain Granola: Original Salty Sweet", "portion": "30g (1/3 cup)", "cal": 140, "p": 3.0, "c": 18.0, "f": 6.0, "fib": 2.0},
                {"item": "H-E-B Whole Frozen Blueberries", "portion": "70g (1/2 cup)", "cal": 35, "p": 0.5, "c": 9.0, "f": 0.0, "fib": 2.0},
            ],
        },
        {
            "id": "bf_3",
            "name": "Toasted Bagel with Cream Cheese + Turkey Bacon & Egg Whites",
            "prep": "Toast Thomas' plain bagel with cream cheese & Everything seasoning; pan-fry 2 slices center-cut bacon and egg whites.",
            "need_to_buy": [],
            "items": [
                {"item": "Thomas' Plain / Original Bagels", "portion": "1 bagel (95g)", "cal": 270, "p": 10.0, "c": 53.0, "f": 2.0, "fib": 2.0},
                {"item": "H-E-B Regular Cream Cheese", "portion": "2 tbsp (28g)", "cal": 100, "p": 2.0, "c": 1.0, "f": 10.0, "fib": 0.0},
                {"item": "H-E-B Thick Cut / Center Cut Bacon", "portion": "2 slices pan-fried", "cal": 80, "p": 6.0, "c": 0.0, "f": 6.0, "fib": 0.0},
                {"item": "H-E-B Cage-Free 100% Liquid Egg Whites", "portion": "184g (3/4 cup)", "cal": 100, "p": 20.0, "c": 0.0, "f": 0.0, "fib": 0.0},
            ],
        },
        {
            "id": "bf_4",
            "name": "Kashi Chocolate Crunch Protein Cereal + Fairlife Milk + Strawberries",
            "prep": "Pour Kashi Chocolate Crunch cereal, add frozen/thawed strawberries, and top with Fairlife fat-free milk.",
            "need_to_buy": [],
            "items": [
                {"item": "Kashi GO Protein + Fiber Cereal: Chocolate Crunch", "portion": "1.25 cups (66g)", "cal": 238, "p": 12.5, "c": 45.0, "f": 3.1, "fib": 12.5},
                {"item": "Fairlife Fat-Free Ultra-Filtered Lactose-Free Milk", "portion": "1.5 cups (360ml)", "cal": 120, "p": 19.5, "c": 9.0, "f": 0.0, "fib": 0.0},
                {"item": "Kirkland Signature Frozen Strawberries", "portion": "140g (1 cup)", "cal": 50, "p": 1.0, "c": 13.0, "f": 0.0, "fib": 3.0},
            ],
        },
        {
            "id": "bf_5",
            "name": "High-Fiber Breakfast Burrito (Eggs, Maple Sausage, Mozzarella & Carb Balance Tortilla)",
            "prep": "Scramble eggs + egg whites, heat maple breakfast sausage, wrap in Mission Carb Balance tortilla with mozzarella.",
            "need_to_buy": [],
            "items": [
                {"item": "Mission Carb Balance Soft Taco Flour Tortillas (70 kcal)", "portion": "2 tortillas (86g)", "cal": 140, "p": 10.0, "c": 38.0, "f": 3.0, "fib": 30.0},
                {"item": "H-E-B Maple Flavor Breakfast Sausage Links/Patties (Frozen)", "portion": "2 links/1 patty (56g)", "cal": 180, "p": 9.0, "c": 2.0, "f": 15.0, "fib": 0.0},
                {"item": "H-E-B Cage-Free 100% Liquid Egg Whites", "portion": "184g (3/4 cup)", "cal": 100, "p": 20.0, "c": 0.0, "f": 0.0, "fib": 0.0},
                {"item": "H-E-B Reduced-Fat Shredded Mozzarella Cheese", "portion": "28g (1/4 cup)", "cal": 70, "p": 7.0, "c": 1.0, "f": 4.5, "fib": 0.0},
            ],
        },
        {
            "id": "bf_6",
            "name": "Protein Oats Bowl (Rolled Oats, Whey Protein, PBfit & Blueberries)",
            "prep": "Microwave rolled oats with water/milk, then stir in 1 scoop whey protein, PBfit, and frozen blueberries.",
            "need_to_buy": [],
            "items": [
                {"item": "Old Fashioned Rolled Oats (Dry)", "portion": "1/2 cup dry (40g)", "cal": 150, "p": 5.0, "c": 27.0, "f": 3.0, "fib": 4.0},
                {"item": "Whey Protein Isolate / Concentrate Powder", "portion": "1 scoop (32g)", "cal": 120, "p": 24.0, "c": 3.0, "f": 1.5, "fib": 0.0},
                {"item": "PBfit Peanut Butter Protein Powder", "portion": "2 tbsp (16g)", "cal": 70, "p": 8.0, "c": 6.0, "f": 2.0, "fib": 2.0},
                {"item": "H-E-B Whole Frozen Blueberries", "portion": "140g (1 cup)", "cal": 70, "p": 1.0, "c": 18.0, "f": 0.0, "fib": 4.0},
            ],
        },
        {
            "id": "bf_7",
            "name": "Oikos Pro 20g Strawberry Yogurt + Chocolate Sea Salt Granola + Banana",
            "prep": "Top Oikos Pro 20g yogurt with Purely Elizabeth Chocolate Sea Salt granola and sliced banana.",
            "need_to_buy": [],
            "items": [
                {"item": "Oikos Pro 20g Protein Cultured Ultra-Filtered Yogurt (Strawberry)", "portion": "1 cup (150g)", "cal": 140, "p": 20.0, "c": 8.0, "f": 3.0, "fib": 0.0},
                {"item": "Purely Elizabeth Ancient Grain Granola: Chocolate Sea Salt", "portion": "30g (1/3 cup)", "cal": 130, "p": 3.0, "c": 17.0, "f": 6.0, "fib": 2.0},
                {"item": "Fresh Bananas (Raw)", "portion": "1 medium (118g)", "cal": 105, "p": 1.3, "c": 27.0, "f": 0.4, "fib": 3.1},
            ],
        },
        {
            "id": "bf_8",
            "name": "Cottage Cheese & Egg White Scramble on Low-Carb Wheat Toast",
            "prep": "Scramble egg whites with cottage cheese until fluffy, serve over 2 slices toasted H-E-B Higher Harvest low-carb bread.",
            "need_to_buy": [],
            "items": [
                {"item": "H-E-B Low-Fat Small Curd Cottage Cheese", "portion": "113g (1/2 cup)", "cal": 90, "p": 13.0, "c": 5.0, "f": 1.5, "fib": 0.0},
                {"item": "H-E-B Cage-Free 100% Liquid Egg Whites", "portion": "184g (3/4 cup)", "cal": 100, "p": 20.0, "c": 0.0, "f": 0.0, "fib": 0.0},
                {"item": "H-E-B Higher Harvest Low-Carb Lifestyle Wheat Bread", "portion": "2 slices (56g)", "cal": 120, "p": 12.0, "c": 24.0, "f": 2.0, "fib": 16.0},
            ],
        },
    ],
    "Lunch": [
        {
            "id": "lu_1",
            "name": "Chicken Teriyaki Bowl with Sticky White Rice & Edamame (Raw Chicken Thighs)",
            "prep": "Pan-sear diced chicken thighs (raw meat in fridge) with soy sauce, garlic, ginger & a touch of maple syrup; serve over Bibigo white rice and edamame.",
            "need_to_buy": [],
            "uses_raw_meat": "Boneless Skinless Chicken Thighs",
            "items": [
                {"item": "Boneless Skinless Chicken Thighs — 1.085 lbs in fridge", "portion": "6 oz raw (170g)", "cal": 210, "p": 33.0, "c": 0.0, "f": 7.5, "fib": 0.0},
                {"item": "Bibigo Cooked Sticky White Rice (Microwave Individual Bowls)", "portion": "1 bowl (210g)", "cal": 310, "p": 6.0, "c": 69.0, "f": 1.0, "fib": 1.0},
                {"item": "H-E-B Premier Shelled Edamame (Frozen)", "portion": "85g (2/3 cup)", "cal": 100, "p": 9.0, "c": 8.0, "f": 3.5, "fib": 4.0},
                {"item": "Soy Sauce", "portion": "1.5 tbsp (22ml)", "cal": 15, "p": 1.5, "c": 1.5, "f": 0.0, "fib": 0.0},
            ],
        },
        {
            "id": "lu_2",
            "name": "Turkey, Bacon & Avocado Sandwich on High-Fiber Wheat Bread",
            "prep": "Layer sliced honey turkey, 2 slices bacon, and mashed avocado on H-E-B Higher Harvest low-carb wheat bread.",
            "need_to_buy": [],
            "items": [
                {"item": "H-E-B Higher Harvest Low-Carb Lifestyle Wheat Bread", "portion": "2 slices (56g)", "cal": 120, "p": 12.0, "c": 24.0, "f": 2.0, "fib": 16.0},
                {"item": "H-E-B Honey Turkey Breast Deli Meat (Sliced)", "portion": "5 oz (140g)", "cal": 175, "p": 25.0, "c": 1.3, "f": 3.8, "fib": 0.0},
                {"item": "H-E-B Thick Cut / Center Cut Bacon", "portion": "2 slices pan-fried", "cal": 80, "p": 6.0, "c": 0.0, "f": 6.0, "fib": 0.0},
                {"item": "Hass Avocados (Fresh)", "portion": "50g", "cal": 80, "p": 1.0, "c": 4.3, "f": 7.3, "fib": 3.4},
            ],
        },
        {
            "id": "lu_3",
            "name": "PB&J + Protein Shake Combo (PBfit & Strawberry Jelly on Sourdough + Fairlife Shake)",
            "prep": "Make a PB&J on sourdough using reconstituted PBfit + strawberry jelly, paired with a cold Fairlife 30g chocolate shake.",
            "need_to_buy": [],
            "items": [
                {"item": "Easy Tiger Sourdough Bread", "portion": "2 slices (116g)", "cal": 300, "p": 12.0, "c": 58.0, "f": 1.5, "fib": 2.0},
                {"item": "PBfit Peanut Butter Protein Powder", "portion": "3 tbsp (24g)", "cal": 105, "p": 12.0, "c": 9.0, "f": 3.0, "fib": 3.0},
                {"item": "Strawberry Jelly / Jam", "portion": "1.5 tbsp (30g)", "cal": 75, "p": 0.0, "c": 19.5, "f": 0.0, "fib": 0.0},
                {"item": "Fairlife Nutrition Plan 30g Chocolate Protein Shakes", "portion": "1 bottle (11.5 fl oz)", "cal": 150, "p": 30.0, "c": 4.0, "f": 2.5, "fib": 1.0},
            ],
        },
        {
            "id": "lu_4",
            "name": "Ground Beef Tacos on Carb Balance Tortillas with Black Beans",
            "prep": "Brown 93/7 ground beef with cumin, garlic & onion powder; load into 2 Carb Balance tortillas with black beans and shredded mozzarella.",
            "need_to_buy": [],
            "uses_raw_meat": "93/7 Lean Ground Beef",
            "items": [
                {"item": "93/7 Lean Ground Beef — 1.09 lbs in fridge", "portion": "5 oz raw (140g)", "cal": 213, "p": 30.0, "c": 0.0, "f": 10.0, "fib": 0.0},
                {"item": "Mission Carb Balance Soft Taco Flour Tortillas (70 kcal)", "portion": "2 tortillas (86g)", "cal": 140, "p": 10.0, "c": 38.0, "f": 3.0, "fib": 30.0},
                {"item": "H-E-B Canned Black Beans (Drained / Cooked)", "portion": "1/2 cup (130g)", "cal": 110, "p": 7.0, "c": 20.0, "f": 0.5, "fib": 7.0},
                {"item": "H-E-B Reduced-Fat Shredded Mozzarella Cheese", "portion": "28g (1/4 cup)", "cal": 70, "p": 7.0, "c": 1.0, "f": 4.5, "fib": 0.0},
            ],
        },
        {
            "id": "lu_5",
            "name": "Soy-Garlic Crispy Chicken Strips & Jasmine Rice Bowl",
            "prep": "Air-fry Tyson crispy chicken strips, toss or drizzle with soy sauce, garlic & ginger, and serve over Ben's Jasmine Ready Rice.",
            "need_to_buy": [],
            "items": [
                {"item": "Tyson Crispy Chicken Breast Strips (Frozen)", "portion": "6 oz (170g)", "cal": 320, "p": 26.0, "c": 22.0, "f": 14.0, "fib": 1.0},
                {"item": "Ben's Original Ready Rice: Jasmine Rice", "portion": "1 cup (140g)", "cal": 240, "p": 4.0, "c": 50.0, "f": 2.5, "fib": 1.0},
                {"item": "Soy Sauce", "portion": "1 tbsp (15ml)", "cal": 10, "p": 1.0, "c": 1.0, "f": 0.0, "fib": 0.0},
            ],
        },
        {
            "id": "lu_6",
            "name": "Canned Chicken Quesadilla on Carb Balance Tortillas + Pinto Beans",
            "prep": "Drain canned white meat chicken, crisp in a skillet inside 2 Carb Balance tortillas with mozzarella, serve with warm pinto beans.",
            "need_to_buy": [],
            "items": [
                {"item": "Canned White Meat Chicken Breast in Water", "portion": "5 oz drained (140g)", "cal": 150, "p": 32.5, "c": 0.0, "f": 2.5, "fib": 0.0},
                {"item": "Mission Carb Balance Soft Taco Flour Tortillas (70 kcal)", "portion": "2 tortillas (86g)", "cal": 140, "p": 10.0, "c": 38.0, "f": 3.0, "fib": 30.0},
                {"item": "H-E-B Reduced-Fat Shredded Mozzarella Cheese", "portion": "28g (1/4 cup)", "cal": 70, "p": 7.0, "c": 1.0, "f": 4.5, "fib": 0.0},
                {"item": "H-E-B Canned Pinto Beans", "portion": "1/2 cup (130g)", "cal": 110, "p": 7.0, "c": 20.0, "f": 0.5, "fib": 6.0},
            ],
        },
        {
            "id": "lu_7",
            "name": "Tuna Salad on Wasa Sourdough Crispbreads + Baby Carrots",
            "prep": "Mix drained tuna with light mayo or Laughing Cow cheese wedge & lemon pepper; spread on Wasa sourdough crackers with carrots on the side.",
            "need_to_buy": [],
            "items": [
                {"item": "Starkist / H-E-B Chunk Light Canned Tuna in Water", "portion": "2 cans drained", "cal": 220, "p": 50.0, "c": 0.0, "f": 2.0, "fib": 0.0},
                {"item": "The Laughing Cow Creamy Light Swiss Cheese Wedges", "portion": "2 wedges (42g)", "cal": 60, "p": 4.0, "c": 2.0, "f": 3.0, "fib": 0.0},
                {"item": "Wasa Sourdough Swedish Style Crispbread Crackers", "portion": "4 slices (56g)", "cal": 180, "p": 6.0, "c": 40.0, "f": 1.0, "fib": 8.0},
                {"item": "Fresh Whole / Baby Carrots", "portion": "100g", "cal": 41, "p": 0.9, "c": 9.6, "f": 0.2, "fib": 2.8},
            ],
        },
        {
            "id": "lu_8",
            "name": "El Monterey Bean & Cheese Burrito + Shredded Chicken Breast",
            "prep": "Microwave El Monterey burrito, top with green chile enchilada sauce and cooked chicken breast for high protein.",
            "need_to_buy": [],
            "items": [
                {"item": "El Monterey Bean & Cheese Burritos (Frozen)", "portion": "1 burrito (142g)", "cal": 310, "p": 10.0, "c": 46.0, "f": 9.0, "fib": 5.0},
                {"item": "Boneless Skinless Chicken Breast Fillets (Frozen)", "portion": "5 oz raw (140g)", "cal": 150, "p": 32.5, "c": 0.0, "f": 2.0, "fib": 0.0},
                {"item": "Green Chile Enchilada Sauce", "portion": "1/4 cup (60g)", "cal": 20, "p": 0.0, "c": 3.0, "f": 0.5, "fib": 1.0},
            ],
        },
    ],
    "Dinner": [
        {
            "id": "di_1",
            "name": "USDA Prime Top Sirloin Steak + Roasted Sweet Potato & Edamame",
            "prep": "Pan-sear the Top Sirloin steak from your fridge with butter & garlic; serve with baked/air-fried sweet potato and steamed edamame.",
            "need_to_buy": ["Sweet Potatoes"],
            "uses_raw_meat": "Kirkland Signature USDA Prime Top Sirloin Steak",
            "items": [
                {"item": "Kirkland Signature USDA Prime Top Sirloin Steak (Boneless, Cap-Off) — 1 steak in fridge", "portion": "8 oz raw (224g)", "cal": 380, "p": 48.0, "c": 0.0, "f": 20.0, "fib": 0.0},
                {"item": "Sweet Potato (Baked / Air-Fried) [🛒 Need to buy]", "portion": "200g raw (~1 medium)", "cal": 172, "p": 3.2, "c": 40.0, "f": 0.1, "fib": 6.0},
                {"item": "H-E-B Premier Shelled Edamame (Frozen)", "portion": "85g (2/3 cup)", "cal": 100, "p": 9.0, "c": 8.0, "f": 3.5, "fib": 4.0},
            ],
        },
        {
            "id": "di_2",
            "name": "Soy-Glazed Ground Beef Korean Rice Bowl (93/7 Beef + Sticky White Rice)",
            "prep": "Brown 93/7 ground beef with soy sauce, minced garlic, minced ginger, and red pepper flakes; serve over cooked white rice.",
            "need_to_buy": [],
            "uses_raw_meat": "93/7 Lean Ground Beef",
            "items": [
                {"item": "93/7 Lean Ground Beef — 1.09 lbs in fridge", "portion": "6 oz raw (170g)", "cal": 255, "p": 36.0, "c": 0.0, "f": 12.0, "fib": 0.0},
                {"item": "Long-Grain White Rice (Dry / Cooked)", "portion": "1.25 cups cooked (198g)", "cal": 256, "p": 5.4, "c": 55.6, "f": 0.5, "fib": 0.8},
                {"item": "Soy Sauce", "portion": "1.5 tbsp (22ml)", "cal": 15, "p": 1.5, "c": 1.5, "f": 0.0, "fib": 0.0},
                {"item": "H-E-B Premier Shelled Edamame (Frozen)", "portion": "85g (2/3 cup)", "cal": 100, "p": 9.0, "c": 8.0, "f": 3.5, "fib": 4.0},
            ],
        },
        {
            "id": "di_3",
            "name": "Honey-Soy Teriyaki Chicken Thighs + Crispy Air-Fried Potatoes",
            "prep": "Cook chicken thighs with soy sauce, garlic, ginger & maple syrup; serve with cubed air-fried potatoes.",
            "need_to_buy": ["Potatoes (Russet or Gold)"],
            "uses_raw_meat": "Boneless Skinless Chicken Thighs",
            "items": [
                {"item": "Boneless Skinless Chicken Thighs — 1.085 lbs in fridge", "portion": "7 oz raw (198g)", "cal": 245, "p": 38.5, "c": 0.0, "f": 8.8, "fib": 0.0},
                {"item": "Potatoes (Cubed & Air-Fried) [🛒 Need to buy]", "portion": "250g raw", "cal": 193, "p": 5.0, "c": 44.0, "f": 0.3, "fib": 5.5},
                {"item": "Soy Sauce", "portion": "1.5 tbsp (22ml)", "cal": 15, "p": 1.5, "c": 1.5, "f": 0.0, "fib": 0.0},
                {"item": "Pure Maple Syrup", "portion": "1 tbsp (15ml)", "cal": 50, "p": 0.0, "c": 13.0, "f": 0.0, "fib": 0.0},
            ],
        },
        {
            "id": "di_4",
            "name": "Soy-Garlic Gulf Shrimp Stir-Fry with Sticky White Rice & Edamame",
            "prep": "Sauté thawed Texas Gulf shrimp in a skillet with soy sauce, garlic & ginger for 3–4 mins; serve over Bibigo sticky white rice and edamame.",
            "need_to_buy": [],
            "items": [
                {"item": "H-E-B Wild Caught Texas Gulf Shrimp (Large, Raw, Peeled, Frozen)", "portion": "8 oz raw (224g)", "cal": 200, "p": 46.0, "c": 0.0, "f": 2.0, "fib": 0.0},
                {"item": "Bibigo Cooked Sticky White Rice (Microwave Individual Bowls)", "portion": "1 bowl (210g)", "cal": 310, "p": 6.0, "c": 69.0, "f": 1.0, "fib": 1.0},
                {"item": "H-E-B Premier Shelled Edamame (Frozen)", "portion": "85g (2/3 cup)", "cal": 100, "p": 9.0, "c": 8.0, "f": 3.5, "fib": 4.0},
                {"item": "Soy Sauce", "portion": "1.5 tbsp (22ml)", "cal": 15, "p": 1.5, "c": 1.5, "f": 0.0, "fib": 0.0},
            ],
        },
        {
            "id": "di_5",
            "name": "Barilla Protein+ Spaghetti & H-E-B Italian Meatballs in Marinara",
            "prep": "Boil Barilla Protein+ spaghetti, bake/air-fry Italian meatballs, toss with warm marinara and grated parmesan.",
            "need_to_buy": [],
            "items": [
                {"item": "Barilla Protein+ (10g Protein) Thin Spaghetti Pasta", "portion": "2 oz dry (56g)", "cal": 190, "p": 10.0, "c": 38.0, "f": 1.0, "fib": 5.0},
                {"item": "H-E-B Italian Style Meatballs (Frozen, Raw)", "portion": "5 oz (140g)", "cal": 315, "p": 25.0, "c": 7.0, "f": 20.0, "fib": 1.0},
                {"item": "Marinara / Traditional Pasta Sauce", "portion": "1/2 cup (125g)", "cal": 70, "p": 2.0, "c": 10.0, "f": 2.0, "fib": 2.0},
                {"item": "Grated Parmesan Cheese", "portion": "1 tbsp (5g)", "cal": 20, "p": 2.0, "c": 0.0, "f": 1.5, "fib": 0.0},
            ],
        },
        {
            "id": "di_6",
            "name": "Banza Chickpea Mac & Cheese + Diced Chicken Breast",
            "prep": "Boil Banza chickpea mac & cheese shells and stir in cooked diced chicken breast.",
            "need_to_buy": [],
            "items": [
                {"item": "Banza Chickpea Pasta Cheddar Mac & Cheese Shells (16g Protein)", "portion": "2.5 oz dry (70g)", "cal": 270, "p": 16.0, "c": 43.0, "f": 4.5, "fib": 5.0},
                {"item": "Boneless Skinless Chicken Breast Fillets (Frozen)", "portion": "6 oz raw (170g)", "cal": 180, "p": 39.0, "c": 0.0, "f": 2.3, "fib": 0.0},
            ],
        },
        {
            "id": "di_7",
            "name": "Top Sirloin Steak + Sticky White Rice & Charro Beans",
            "prep": "Pan-sear the Top Sirloin steak from the fridge, serve with microwave sticky white rice and warm H-E-B charro beans.",
            "need_to_buy": [],
            "uses_raw_meat": "Kirkland Signature USDA Prime Top Sirloin Steak",
            "items": [
                {"item": "Kirkland Signature USDA Prime Top Sirloin Steak (Boneless, Cap-Off) — 1 steak in fridge", "portion": "7 oz raw (198g)", "cal": 333, "p": 42.0, "c": 0.0, "f": 17.5, "fib": 0.0},
                {"item": "Hill Country Fare Quick Heat Long-Grain White Rice", "portion": "1 cup (140g)", "cal": 210, "p": 4.0, "c": 45.0, "f": 1.5, "fib": 1.0},
                {"item": "H-E-B Charro / Baked Beans", "portion": "1/2 cup (130g)", "cal": 130, "p": 7.0, "c": 22.0, "f": 2.0, "fib": 6.0},
            ],
        },
        {
            "id": "di_8",
            "name": "Cajun Chicken Nuggets + Ben's Spanish Style Rice & Black Beans",
            "prep": "Air-fry Tyson white meat chicken nuggets dusted with Cajun seasoning; serve with Ben's Spanish Rice and black beans.",
            "need_to_buy": [],
            "items": [
                {"item": "Tyson White Meat Chicken Nuggets (Frozen)", "portion": "10 nuggets (180g)", "cal": 420, "p": 26.0, "c": 26.0, "f": 24.0, "fib": 2.0},
                {"item": "Ben's Original Ready Rice: Spanish Style", "portion": "1/2 cup (70g)", "cal": 110, "p": 2.5, "c": 22.0, "f": 1.3, "fib": 1.0},
                {"item": "H-E-B Canned Black Beans (Drained / Cooked)", "portion": "1/2 cup (130g)", "cal": 110, "p": 7.0, "c": 20.0, "f": 0.5, "fib": 7.0},
            ],
        },
    ],
    "Snacks": [
        {
            "id": "sn_1",
            "name": "Oikos Triple Zero Greek Yogurt + Purely Elizabeth Granola",
            "prep": "Top Oikos Triple Zero Greek yogurt with Purely Elizabeth granola.",
            "need_to_buy": [],
            "items": [
                {"item": "Oikos Triple Zero 15g Protein Greek Yogurt (Strawberry)", "portion": "1 cup (150g)", "cal": 100, "p": 15.0, "c": 7.0, "f": 0.0, "fib": 0.0},
                {"item": "Purely Elizabeth Ancient Grain Granola: Original Salty Sweet", "portion": "30g (1/3 cup)", "cal": 140, "p": 3.0, "c": 18.0, "f": 6.0, "fib": 2.0},
            ],
        },
        {
            "id": "sn_2",
            "name": "Kirkland Chocolate Brownie Protein Bar + H-E-B Fiber Gummies",
            "prep": "Unwrap Kirkland protein bar and take a serving of fiber gummies (up to 10g fiber cap).",
            "need_to_buy": [],
            "items": [
                {"item": "Kirkland Signature Protein Bar (Chocolate Brownie)", "portion": "1 bar (60g)", "cal": 190, "p": 21.0, "c": 22.0, "f": 7.0, "fib": 10.0},
                {"item": "H-E-B Vitamin Fiber Gummies (Peach, Strawberry & Berry — Max 10g Fiber/Day)", "portion": "2 gummies", "cal": 15, "p": 0.0, "c": 6.0, "f": 0.0, "fib": 5.0},
            ],
        },
        {
            "id": "sn_3",
            "name": "Quest Tortilla Protein Chips + Kirkland Grass-Fed Beef Stick",
            "prep": "Grab a bag of Quest protein chips and a Kirkland beef stick.",
            "need_to_buy": [],
            "items": [
                {"item": "Quest Tortilla Style Protein Chips", "portion": "1 bag (32g)", "cal": 140, "p": 19.0, "c": 5.0, "f": 4.5, "fib": 1.0},
                {"item": "Kirkland Signature Grass-Fed Beef Stick", "portion": "1 stick (28g)", "cal": 90, "p": 6.0, "c": 1.0, "f": 7.0, "fib": 0.0},
            ],
        },
        {
            "id": "sn_4",
            "name": "Halo Top Vanilla Bean Ice Cream + PBfit Drizzle",
            "prep": "Scoop Halo Top Vanilla Bean and drizzle with PBfit mixed with water.",
            "need_to_buy": [],
            "items": [
                {"item": "Halo Top Light Ice Cream: Vanilla Bean", "portion": "2/3 cup (95g)", "cal": 100, "p": 6.0, "c": 19.0, "f": 2.0, "fib": 3.0},
                {"item": "PBfit Peanut Butter Protein Powder", "portion": "2 tbsp (16g)", "cal": 70, "p": 8.0, "c": 6.0, "f": 2.0, "fib": 2.0},
            ],
        },
        {
            "id": "sn_5",
            "name": "Fairlife 30g Chocolate Protein Shake + Light Butter Popcorn",
            "prep": "Cold Fairlife chocolate shake plus a bowl of microwave light butter popcorn.",
            "need_to_buy": [],
            "items": [
                {"item": "Fairlife Nutrition Plan 30g Chocolate Protein Shakes", "portion": "1 bottle (11.5 fl oz)", "cal": 150, "p": 30.0, "c": 4.0, "f": 2.5, "fib": 1.0},
                {"item": "Hill Country Fare Microwave Popcorn: Light Butter", "portion": "3 cups popped (24g)", "cal": 100, "p": 2.0, "c": 15.0, "f": 3.5, "fib": 3.0},
            ],
        },
        {
            "id": "sn_6",
            "name": "Tillamook Sharp Cheddar Portion + Good Thins + Sliced Red Apple",
            "prep": "Pair a 21g Tillamook cheddar packet with Good Thins corn/rice snacks and sliced apple.",
            "need_to_buy": [],
            "items": [
                {"item": "Tillamook Sharp Cheddar Individual Cheese Portions (21g Packets)", "portion": "1 packet (21g)", "cal": 90, "p": 5.0, "c": 0.0, "f": 8.0, "fib": 0.0},
                {"item": "Good Thins Gluten-Free Corn & Rice Snacks (130 kcal)", "portion": "1 serving (30g)", "cal": 130, "p": 2.0, "c": 24.0, "f": 3.0, "fib": 1.0},
                {"item": "H-E-B Red Apples (Fresh / Sliced)", "portion": "100g sliced", "cal": 52, "p": 0.3, "c": 14.0, "f": 0.2, "fib": 2.4},
            ],
        },
        {
            "id": "sn_7",
            "name": "Cottage Cheese + Frozen Strawberries & Jell-O Sugar-Free Cup",
            "prep": "Bowl of H-E-B low-fat cottage cheese with strawberries, plus a sugar-free Jell-O cup.",
            "need_to_buy": [],
            "items": [
                {"item": "H-E-B Low-Fat Small Curd Cottage Cheese", "portion": "113g (1/2 cup)", "cal": 90, "p": 13.0, "c": 5.0, "f": 1.5, "fib": 0.0},
                {"item": "Kirkland Signature Frozen Strawberries", "portion": "140g (1 cup)", "cal": 50, "p": 1.0, "c": 13.0, "f": 0.0, "fib": 3.0},
                {"item": "Jell-O Sugar-Free Ready-to-Eat Strawberry Gelatin Cups", "portion": "1 cup", "cal": 10, "p": 1.0, "c": 0.0, "f": 0.0, "fib": 0.0},
            ],
        },
        {
            "id": "sn_8",
            "name": "Babybel Cheese + Cashews & Raisins",
            "prep": "Grab 1 Babybel cheese wheel, a small handful of cashews, and raisins.",
            "need_to_buy": [],
            "items": [
                {"item": "Babybel Original Circular Wax Semisoft Cheeses", "portion": "1 wheel (21g)", "cal": 70, "p": 5.0, "c": 0.0, "f": 6.0, "fib": 0.0},
                {"item": "Raw / Roasted Cashews", "portion": "15g (~10 cashews)", "cal": 85, "p": 2.5, "c": 4.5, "f": 6.5, "fib": 0.5},
                {"item": "Seedless Raisins", "portion": "20g (2 tbsp)", "cal": 60, "p": 0.5, "c": 15.5, "f": 0.0, "fib": 1.0},
            ],
        },
    ],
}


def load_rotation_state() -> Dict[str, int]:
    if os.path.exists(ROTATION_FILE):
        try:
            with open(ROTATION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {slot: 0 for slot in MEAL_CATALOG}


def save_rotation_state(state: Dict[str, int]):
    with open(ROTATION_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_rotating_options(slot: str, count: int = 5, advance: bool = True, dislikes: List[str] = None) -> List[Dict[str, Any]]:
    """Return `count` rotating options for `slot`, skipping anything matching `dislikes`."""
    pool = MEAL_CATALOG.get(slot, [])
    if dislikes:
        low_dislikes = [d.lower() for d in dislikes if d]
        filtered = []
        for m in pool:
            text_blob = (m["name"] + " " + " ".join(i["item"] for i in m["items"])).lower()
            if not any(d in text_blob for d in low_dislikes):
                filtered.append(m)
        if filtered:
            pool = filtered

    if not pool:
        return []

    state = load_rotation_state()
    start_idx = state.get(slot, 0) % len(pool)
    picked = [pool[(start_idx + i) % len(pool)] for i in range(min(count, len(pool)))]

    if advance:
        state[slot] = (start_idx + count) % len(pool)
        save_rotation_state(state)

    return picked


def find_option_by_id(opt_id: str) -> Dict[str, Any]:
    for slot, pool in MEAL_CATALOG.items():
        for m in pool:
            if m["id"] == opt_id:
                return {**m, "slot": slot}
    return {}


def format_option_step1_label(opt: Dict[str, Any]) -> str:
    """Step 1: Name ONLY + [🛒 Need to buy: ...] if applicable (Rule 6a & 4c)."""
    label = opt["name"]
    if opt.get("need_to_buy"):
        label += f" [🛒 Need to buy: {', '.join(opt['need_to_buy'])}]"
    return label


def format_option_step2_details(opt: Dict[str, Any], scale: float = 1.0) -> str:
    """Step 2: Exact Portions (Grams/Cups/Units) + Calories, Protein, Carbs, Fats, Fiber (Rule 6b)."""
    lines = [f"🍽️ *{opt['name']}*"]
    if opt.get("need_to_buy"):
        lines.append(f"🛒 *Need to buy:* {', '.join(opt['need_to_buy'])}")
    lines.append(f"🧑‍🍳 *Prep:* {opt['prep']}\n")
    lines.append("*Ingredients & Exact Amounts:*")

    tot_cal, tot_p, tot_c, tot_f, tot_fib = 0, 0.0, 0.0, 0.0, 0.0
    for it in opt["items"]:
        cal = int(round(it["cal"] * scale))
        p = round(it["p"] * scale, 1)
        c = round(it["c"] * scale, 1)
        f = round(it["f"] * scale, 1)
        fib = round(it["fib"] * scale, 1)
        tot_cal += cal
        tot_p += p
        tot_c += c
        tot_f += f
        tot_fib += fib

        portion_str = it["portion"]
        if abs(scale - 1.0) > 0.05:
            portion_str = f"{scale:.2f}x ({it['portion']})"

        lines.append(
            f"• *{it['item']}*: `{portion_str}`\n"
            f"  ↳ `{cal} kcal` | `{p:g}g P` | `{c:g}g C` | `{f:g}g F` | `{fib:g}g Fiber`"
        )

    lines.append(
        f"\n📊 *Meal Total:*\n"
        f"• *Calories:* `{tot_cal} kcal`\n"
        f"• *Protein:* `{round(tot_p, 1):g}g`\n"
        f"• *Carbs:* `{round(tot_c, 1):g}g`\n"
        f"• *Fats:* `{round(tot_f, 1):g}g`\n"
        f"• *Fiber:* `{round(tot_fib, 1):g}g`"
    )
    return "\n".join(lines)
