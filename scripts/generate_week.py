#!/usr/bin/env python3
"""Generate the meal-prep plan for the upcoming week.

Runs every Friday. Picks two recipes for the Sunday cook, schedules the five
lunch portions across Monday to Friday, computes macros from the ingredient
table, and rolls the whole thing up into a Rewe shopping list.

Writes app/data/plan.json (the current week) and app/data/history.json
(the recipe ids of recent weeks, so the picker doesn't repeat itself).
"""

import argparse, json, math, random, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "scripts" / "data"
OUT = ROOT / "app" / "data"

PORTIONS_PER_WEEK = 5
PROTEIN_TARGET_PER_DAY = 170          # g/day, the reader's overall target
LUNCH_SHARE = (1 / 3, 1 / 2)          # the prepped lunch should cover this slice of it
HISTORY_WEEKS = 3                     # don't repeat a recipe within this many weeks
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
FREEZE_FROM_DAY = 3                   # index 3 = Thursday; those portions get frozen
AISLE_ORDER = ["Produce", "Fresh meat & fish", "Chilled & dairy",
               "Frozen", "Cans & jars", "Dry goods", "Pantry staples"]


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def eating_week_monday(today):
    """The Monday of the week these meals get eaten.

    Generated on a Friday, the plan is for the Monday three days later. Run on
    any other day, it targets the next Monday that hasn't started yet.
    """
    ahead = (7 - today.weekday()) % 7      # Monday == 0
    return today + dt.timedelta(days=ahead or 7)


def macros_for(recipe, ingredients):
    """Per-portion macros, summed from the ingredient table."""
    total = {"protein": 0.0, "carbs": 0.0, "fiber": 0.0, "fat": 0.0, "kcal": 0.0}
    for key, grams in recipe["per_portion"].items():
        ing = ingredients[key]
        for k in total:
            total[k] += ing[k] * grams / 100.0
    return {k: round(v, 1) for k, v in total.items()}


def recent_ids(history, weeks):
    """Recipe ids used across the last `weeks` distinct weeks in history.

    Counted by week rather than by entry, because a rerolled week holds more
    than one entry — the meals that were eaten and the ones that replaced them.
    """
    seen, ids = [], set()
    for entry in reversed(history):
        if entry["week_id"] not in seen:
            if len(seen) == weeks:
                break
            seen.append(entry["week_id"])
        ids.update(entry["recipe_ids"])
    return ids


def pick_recipes(recipes, history, week_monday):
    """One oven recipe and one stovetop recipe, so the two can run in parallel.

    Avoids anything cooked in the last few weeks and never pairs two meals with
    the same protein. If the library is too small to honour the full exclusion
    window, the window is narrowed a week at a time rather than the rule being
    abandoned outright — a three-week-old repeat beats a one-week-old one. The
    choice is seeded by the week, so re-running gives the same plan.
    """
    rng = random.Random(week_monday.isoformat())
    for weeks in range(HISTORY_WEEKS, -1, -1):
        pool = [r for r in recipes if r["id"] not in recent_ids(history, weeks)]
        pairs = [(a, b)
                 for a in pool if a["track"] == "oven"
                 for b in pool if b["track"] == "stovetop"
                 and a["protein_source"] != b["protein_source"]]
        if pairs:
            return rng.choice(pairs)
    raise RuntimeError("no oven/stovetop pair with different proteins exists")


def order_meals(a, b):
    """Decide which meal is eaten first, and how the five portions split.

    Fish is the constraint: cooked fish keeps about two days, and fish bought
    frozen must not be refrozen after cooking. So a fish meal always goes at
    the front of the week with two portions, and never gets frozen.
    """
    if a["protein_source"] == "fish":
        first, second, split = a, b, (2, 3)
    elif b["protein_source"] == "fish":
        first, second, split = b, a, (2, 3)
    else:
        first, second, split = a, b, (3, 2)
    return first, second, split


def build_schedule(first, second, split):
    schedule = []
    for i, day in enumerate(DAYS):
        recipe = first if i < split[0] else second
        frozen = i >= FREEZE_FROM_DAY
        schedule.append({
            "day": day,
            "recipe_id": recipe["id"],
            "recipe_name": recipe["name"],
            "storage": "freezer" if frozen else "fridge",
            "note": ("Freeze Sunday. Move to the fridge on Wednesday evening."
                     if frozen else "Straight into the fridge."),
        })
    return schedule


def build_grocery_list(meals, ingredients):
    """Aggregate every ingredient across both meals and round up to Rewe packs."""
    totals = {}
    for meal in meals:
        for key, per_portion in meal["recipe"]["per_portion"].items():
            totals[key] = totals.get(key, 0) + per_portion * meal["portions"]

    aisles = {}
    for key, grams in sorted(totals.items()):
        ing = ingredients[key]
        packs = math.ceil(grams / ing["pack"])
        entry = {
            "id": key,
            "de": ing["de"],
            "en": ing["en"],
            "need": int(round(grams)),
            "unit": ing["unit"],
            "packs": packs,
            "pack_size": ing["pack"],
            "buy_label": f"{packs} × {ing['pack']} {ing['unit']}",
            "pantry": bool(ing.get("pantry")),
        }
        if ing.get("note"):
            entry["note"] = ing["note"]
        aisles.setdefault(ing["aisle"], []).append(entry)

    return [{"aisle": a, "items": aisles[a]} for a in AISLE_ORDER if a in aisles]


def build_timeline(first, second):
    """Merge both recipes into one Sunday running order.

    Both start at T+0 — that is the point of pairing an oven recipe with a
    stovetop one. Steps are sorted by the minute they begin.
    """
    lanes = [("A", first), ("B", second)]
    events = []
    for lane, recipe in lanes:
        for i, text in enumerate(recipe["steps"]):
            events.append({
                "lane": lane,
                "track": recipe["track"],
                "recipe_id": recipe["id"],
                "recipe_name": recipe["name"],
                "at": recipe["step_at"][i],
                "minutes": recipe["step_min"][i],
                "step": i + 1,
                "text": text,
            })
    events.sort(key=lambda e: (e["at"], e["lane"]))
    cook = max(r["total_min"] for _, r in lanes)
    return events, cook


def build_plan(today=None, reroll=False):
    ingredients = {k: v for k, v in load("ingredients.json").items()
                   if not k.startswith("_")}
    recipes = load("recipes.json")
    history_path = OUT / "history.json"
    history = json.loads(history_path.read_text()) if history_path.exists() else []

    today = today or dt.date.today()
    monday = eating_week_monday(today)
    sunday = monday - dt.timedelta(days=1)     # cook day
    saturday = monday - dt.timedelta(days=2)   # everything in stock by now
    iso_year, iso_week, _ = monday.isocalendar()
    week_id = f"{iso_year}-W{iso_week:02d}"

    # A reroll means the meals currently planned for this week have actually
    # been eaten, so they're marked as such and stop being candidates.
    if reroll:
        for h in history:
            if h["week_id"] == week_id:
                h["consumed"] = True

    # Keep this week's consumed entries — something already eaten must not come
    # back — but drop a merely-planned one, so an ordinary re-run doesn't see
    # its own previous output as "recent" and move meals already shopped for.
    history = [h for h in history if h["week_id"] != week_id or h.get("consumed")]
    a, b = pick_recipes(recipes, history, monday)
    first, second, split = order_meals(a, b)

    meals = []
    for label, recipe, portions in (("A", first, split[0]), ("B", second, split[1])):
        m = macros_for(recipe, ingredients)
        meals.append({
            "label": label,
            "portions": portions,
            "recipe": recipe,
            "macros": m,
            "protein_share": [round(m["protein"] / PROTEIN_TARGET_PER_DAY * 100)],
        })

    timeline, cook_minutes = build_timeline(first, second)
    proteins = [m["macros"]["protein"] for m in meals]
    weighted = sum(m["macros"]["protein"] * m["portions"] for m in meals) / PORTIONS_PER_WEEK

    plan = {
        "week_id": week_id,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "dates": {
            "shop_by": saturday.isoformat(),
            "cook_on": sunday.isoformat(),
            "week_start": monday.isoformat(),
            "week_end": (monday + dt.timedelta(days=4)).isoformat(),
        },
        "targets": {
            "protein_per_day": PROTEIN_TARGET_PER_DAY,
            "lunch_min": round(PROTEIN_TARGET_PER_DAY * LUNCH_SHARE[0]),
            "lunch_max": round(PROTEIN_TARGET_PER_DAY * LUNCH_SHARE[1]),
        },
        "summary": {
            "cook_minutes": cook_minutes,
            "portions": PORTIONS_PER_WEEK,
            "protein_low": min(proteins),
            "protein_high": max(proteins),
            "protein_avg": round(weighted, 1),
            "in_target": all(
                round(PROTEIN_TARGET_PER_DAY * LUNCH_SHARE[0]) <= p <=
                round(PROTEIN_TARGET_PER_DAY * LUNCH_SHARE[1]) for p in proteins),
        },
        "meals": [{
            "label": m["label"],
            "portions": m["portions"],
            "id": m["recipe"]["id"],
            "name": m["recipe"]["name"],
            "track": m["recipe"]["track"],
            "protein_source": m["recipe"]["protein_source"],
            "active_min": m["recipe"]["active_min"],
            "total_min": m["recipe"]["total_min"],
            "reheat": m["recipe"]["reheat"],
            "cold_ok": m["recipe"]["cold_ok"],
            "macros": m["macros"],
            "steps": m["recipe"]["steps"],
            "ingredients": [
                {"de": ingredients[k]["de"], "en": ingredients[k]["en"],
                 "per_portion": v, "total": round(v * m["portions"]),
                 "unit": ingredients[k]["unit"]}
                for k, v in m["recipe"]["per_portion"].items()
            ],
        } for m in meals],
        "schedule": build_schedule(first, second, split),
        "groceries": build_grocery_list(meals, ingredients),
        "timeline": timeline,
    }

    history.append({"week_id": week_id, "recipe_ids": [first["id"], second["id"]]})
    return plan, history[-12:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="pretend today is this ISO date (for testing)")
    ap.add_argument("--dry-run", action="store_true", help="print a summary, write nothing")
    ap.add_argument("--reroll", action="store_true",
                    help="this week's meals have been eaten — pick a different pair")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    plan, history = build_plan(today, reroll=args.reroll)

    if args.dry_run:
        s = plan["summary"]
        print(f"{plan['week_id']}  cook {plan['dates']['cook_on']}  ~{s['cook_minutes']} min")
        for m in plan["meals"]:
            print(f"  {m['label']} ×{m['portions']}  {m['name']}")
            print(f"      {m['macros']['protein']} g protein · {m['macros']['fiber']} g fibre "
                  f"· {m['macros']['carbs']} g carbs · {m['macros']['kcal']} kcal")
        print(f"  protein in target window: {s['in_target']}")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    # Keep the old timestamp when nothing else moved, so a re-run doesn't show
    # up as a change and the Friday job has nothing to commit.
    existing = OUT / "plan.json"
    if existing.exists():
        try:
            prev = json.loads(existing.read_text(encoding="utf-8"))
            stamp = prev.pop("generated_at", None)
            if prev == {k: v for k, v in plan.items() if k != "generated_at"} and stamp:
                plan["generated_at"] = stamp
        except (ValueError, OSError):
            pass

    blob = json.dumps(plan, ensure_ascii=False, indent=2)
    (OUT / "plan.json").write_text(blob, encoding="utf-8")
    # Same data as a plain script, so the page still works opened from the
    # filesystem (where fetch() of a local file is blocked) and on first paint.
    (OUT / "plan.js").write_text(f"window.__PLAN__ = {blob};\n", encoding="utf-8")
    (OUT / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote app/data/plan.json for {plan['week_id']}")


if __name__ == "__main__":
    main()
