"""Reading a food entry's name for things worth noticing.

Ported from the one-data dashboard's `config/food_flags.json`. Kept as code
rather than a JSON file for one reason: nothing edits these at runtime, and a
file means a deploy-time path to get wrong for a rule that only ever changes
when someone edits the source anyway.

**Applied at read time, never stored.** `DietEntry` records what was eaten, not
what it contained (see the model docstring). Flagging is an opinion about a
string, and opinions change - "chai" was not on the caffeine list until it was.
A stored column would freeze every past entry against the rule that happened to
be in force the day it was logged, so the archive would disagree with itself.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FoodFlag:
    key: str
    label: str
    #: Whether this reads as a problem or as something to keep doing. The UI
    #: cannot infer it - "high sugar" and "good protein" are the same shape of
    #: fact - and colouring both alike is what made the dashboard's food log
    #: unreadable at a glance.
    tone: str
    keywords: tuple[str, ...]


FLAGS: tuple[FoodFlag, ...] = (
    FoodFlag(
        "dairy",
        "Dairy",
        "watch",
        (
            "milk",
            "cheese",
            "butter",
            "cream",
            "yogurt",
            "yoghurt",
            "ice cream",
            "whey",
            "lactose",
            "dairy",
            "custard",
            "gelato",
            "ricotta",
            "mozzarella",
            "parmesan",
            "brie",
            "cheddar",
            "feta",
        ),
    ),
    FoodFlag(
        "caffeine",
        "Caffeine",
        "watch",
        (
            "coffee",
            "espresso",
            "latte",
            "cappuccino",
            "flat white",
            "long black",
            "mocha",
            "tea",
            "green tea",
            "black tea",
            "iced tea",
            "energy drink",
            "red bull",
            "monster",
            "cola",
            "coke",
            "pepsi",
            "matcha",
            "chai",
            "pre-workout",
            "preworkout",
        ),
    ),
    FoodFlag(
        "high_sugar",
        "High sugar",
        "watch",
        (
            "juice",
            "soft drink",
            "soda",
            "lollies",
            "candy",
            "chocolate",
            "cake",
            "biscuit",
            "cookie",
            "muffin",
            "donut",
            "doughnut",
            "jam",
            "honey",
            "syrup",
            "ice cream",
            "jelly",
            "gummy",
            "fruit bar",
        ),
    ),
    FoodFlag(
        "good_protein",
        "Good protein",
        "good",
        (
            "chicken",
            "beef",
            "steak",
            "mince",
            "tuna",
            "salmon",
            "sardine",
            "egg",
            "tofu",
            "tempeh",
            "protein shake",
            "protein powder",
            "fish",
            "prawn",
            "shrimp",
            "lamb",
            "pork",
            "turkey",
            "cottage cheese",
        ),
    ),
    FoodFlag(
        "ldl_lowering",
        "LDL-lowering",
        "good",
        (
            "oats",
            "oatmeal",
            "porridge",
            "avocado",
            "olive oil",
            "almonds",
            "walnuts",
            "flaxseed",
            "chia",
            "psyllium",
            "beans",
            "lentils",
            "chickpeas",
            "broccoli",
            "spinach",
            "kale",
            "blueberry",
            "strawberry",
            "apple",
            "pear",
            "kiwi",
        ),
    ),
)

FLAGS_BY_KEY: dict[str, FoodFlag] = {f.key: f for f in FLAGS}


def flags_for(name: str) -> list[str]:
    """Which flag keys a food name matches. Substring, case-insensitive.

    Substring rather than word matching because the names are typed on a phone
    with no autocomplete: "coffee w milk", "2x flat white" and "coffee." all
    have to match, and a tokeniser that gets any of those wrong is worse than
    the false positive it prevents.
    """
    lowered = (name or "").lower()
    return [f.key for f in FLAGS if any(kw in lowered for kw in f.keywords)]


def catalogue() -> list[dict]:
    """The vocabulary, so the UI labels a key it did not hard-code."""
    return [{"key": f.key, "label": f.label, "tone": f.tone} for f in FLAGS]
