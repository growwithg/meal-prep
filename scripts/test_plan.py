#!/usr/bin/env python3
"""Guards on the planner. Run: python3 scripts/test_plan.py

These are the rules the plan has to satisfy every week, not just on the week
someone happened to look at. Adding a recipe with too little protein, or one
that lets fish end up frozen, should fail here rather than in the fridge.
"""

import datetime as dt, json, sys, tempfile, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import generate_week as g

FAIL = []


def check(cond, msg):
    if not cond:
        FAIL.append(msg)


def main():
    ing = {k: v for k, v in g.load("ingredients.json").items() if not k.startswith("_")}
    recipes = g.load("recipes.json")
    lo, hi = (round(g.PROTEIN_TARGET_PER_DAY * s) for s in g.LUNCH_SHARE)

    # ── every recipe on its own ──────────────────────────────────────────────
    for r in recipes:
        m = g.macros_for(r, ing)
        check(lo <= m["protein"] <= hi,
              f"{r['id']}: {m['protein']} g protein is outside the {lo}-{hi} g lunch window")
        check(m["fiber"] >= 10, f"{r['id']}: only {m['fiber']} g fibre")
        check(len(r["steps"]) == len(r["step_at"]) == len(r["step_min"]),
              f"{r['id']}: step timing arrays don't match the steps")
        check(max(a + d for a, d in zip(r["step_at"], r["step_min"])) == r["total_min"],
              f"{r['id']}: last step doesn't land on total_min")
        check("pork" not in json.dumps(r).lower(), f"{r['id']}: mentions pork")
        for k in r["per_portion"]:
            check(k in ing, f"{r['id']}: unknown ingredient {k}")

    ids = [r["id"] for r in recipes]
    check(len(ids) == len(set(ids)), "duplicate recipe ids")
    check(len({r["track"] for r in recipes}) == 2, "need both oven and stovetop recipes")

    # Salmon must be the wild-caught line, never farmed.
    check("Wild" in ing["wild_salmon"]["de"] and "MSC" in ing["wild_salmon"]["de"],
          "the salmon ingredient is not the wild-caught one")

    # ── the generator, over a long run of weeks ──────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        real_out, g.OUT = g.OUT, Path(tmp)
        try:
            day = dt.date(2026, 1, 2)          # a Friday
            for _ in range(52):
                plan, history = g.build_plan(day)
                (Path(tmp) / "history.json").write_text(json.dumps(history))

                meals = plan["meals"]
                check(sum(m["portions"] for m in meals) == g.PORTIONS_PER_WEEK,
                      f"{plan['week_id']}: portions don't add up to five")
                check({m["track"] for m in meals} == {"oven", "stovetop"},
                      f"{plan['week_id']}: both meals share a cooking track")
                check(meals[0]["protein_source"] != meals[1]["protein_source"],
                      f"{plan['week_id']}: both meals use the same protein")
                check(plan["summary"]["cook_minutes"] <= 90,
                      f"{plan['week_id']}: Sunday cook exceeds the 90-minute budget")

                by_id = {m["id"]: m for m in meals}
                for s in plan["schedule"]:
                    if s["storage"] == "freezer":
                        check(by_id[s["recipe_id"]]["protein_source"] != "fish",
                              f"{plan['week_id']}: a fish portion was scheduled for the freezer")

                # Cooked food shouldn't sit chilled past Wednesday.
                chilled = [s["day"] for s in plan["schedule"] if s["storage"] == "fridge"]
                check(chilled == ["Monday", "Tuesday", "Wednesday"],
                      f"{plan['week_id']}: fridge days are {chilled}")

                # Fish, if present, is eaten at the front of the week.
                fish = [i for i, s in enumerate(plan["schedule"])
                        if by_id[s["recipe_id"]]["protein_source"] == "fish"]
                check(fish in ([], [0, 1]),
                      f"{plan['week_id']}: fish is not confined to Monday and Tuesday")

                # The shopping list has to cover every gram the recipes call for.
                bought = {i["id"]: i["packs"] * i["pack_size"]
                          for grp in plan["groceries"] for i in grp["items"]}
                needed = {}
                for m in meals:
                    src = next(r for r in recipes if r["id"] == m["id"])
                    for k, v in src["per_portion"].items():
                        needed[k] = needed.get(k, 0) + v * m["portions"]
                for k, want in needed.items():
                    check(bought.get(k, 0) >= want - 0.001,
                          f"{plan['week_id']}: list buys {bought.get(k, 0)} of {k}, recipes need {want}")

                day += dt.timedelta(days=7)
        finally:
            g.OUT = real_out

    # ── re-running must not move the meals ──────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        real_out, g.OUT = g.OUT, Path(tmp)
        try:
            seen = []
            for _ in range(4):
                plan, history = g.build_plan(dt.date(2026, 3, 6))
                (Path(tmp) / "history.json").write_text(json.dumps(history))
                seen.append(tuple(m["id"] for m in plan["meals"]))
            check(len(set(seen)) == 1,
                  f"re-running the generator for one week gave different plans: {sorted(set(seen))}")
        finally:
            g.OUT = real_out

    # ── reroll swaps the meals and remembers what was eaten ─────────────────
    with tempfile.TemporaryDirectory() as tmp:
        real_out, g.OUT = g.OUT, Path(tmp)
        try:
            day = dt.date(2026, 8, 29)
            first, hist = g.build_plan(day)
            (Path(tmp) / "history.json").write_text(json.dumps(hist))
            eaten = {m["id"] for m in first["meals"]}

            second, hist = g.build_plan(day, reroll=True)
            (Path(tmp) / "history.json").write_text(json.dumps(hist))
            fresh = {m["id"] for m in second["meals"]}
            check(not (eaten & fresh),
                  f"reroll returned a meal that was already eaten: {sorted(eaten & fresh)}")
            check(any(h.get("consumed") for h in hist),
                  "reroll did not record the eaten meals as consumed")

            # A plain re-run after a reroll must be stable, and must not bring
            # the eaten meals back.
            again, hist2 = g.build_plan(day)
            check({m["id"] for m in again["meals"]} == fresh,
                  "a plain re-run after a reroll changed the plan")
            check(not (eaten & {m["id"] for m in again["meals"]}),
                  "a plain re-run after a reroll resurrected the eaten meals")

            # Rerolling repeatedly keeps finding something new until the
            # library genuinely runs out.
            seen = set(eaten) | set(fresh)
            for _ in range(2):
                nxt, hist = g.build_plan(day, reroll=True)
                (Path(tmp) / "history.json").write_text(json.dumps(hist))
                ids = {m["id"] for m in nxt["meals"]}
                check(not (ids & seen), f"repeat reroll repeated a meal: {sorted(ids & seen)}")
                seen |= ids
        finally:
            g.OUT = real_out

    if FAIL:
        print(f"FAILED ({len(FAIL)})")
        for f in FAIL[:20]:
            print("  -", f)
        return 1
    print("all planner guards passed (10 recipes, 52 generated weeks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
