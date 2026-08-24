# Prep

A weekly meal-prep planner. Two lunch meals across five workdays, cooked in one
Sunday session, from a shopping list you fill at Rewe on Saturday.

It's a small web app that installs to the iPhone home screen and works offline.
Every Friday it picks the next week's meals by itself.

<!-- Screens: Week, Shop, Cook -->

## Put it on your phone

1. Open **https://growwithg.github.io/meal-prep/** in **Safari** (not Chrome).
2. Tap **Share** — the square with the arrow.
3. Scroll down, tap **Add to Home Screen**.

It gets an icon, opens fullscreen with no browser bars, and works without
signal — useful in the parts of the shop where reception dies.

## The three screens

**Week** — the two meals, their macros, and which day each portion is eaten.
The bar under each meal shows what share of the 170 g daily protein target that
lunch covers; the hatched band is the 57–85 g the lunch is meant to land in.

**Shop** — the full list rounded up to Rewe pack sizes, grouped in the order you
walk the store. German shelf names are the headline, English underneath, so the
list matches what's actually printed on the label. Tick items off as you go.
Cupboard staples are listed separately and don't count toward the total.

**Cook** — the Sunday running order with both recipes merged into one timeline,
plus each recipe on its own with quantities scaled to its portion count.

Ticks are stored on the device, keyed by week, so Friday's new plan arrives with
a clean list and doesn't wipe the one you're still working through.

Updates to the app itself arrive one launch late: the cached copy is served
immediately and a fresh one is fetched in the background, so a change pushed
today shows up the next time you open it.

## How the plan is built

`scripts/generate_week.py` picks the meals and writes `app/data/plan.json`.

- **One oven dish, one stovetop dish.** That's what lets both run from T+0
  without fighting over a burner, and why the whole cook lands in 40–45 minutes
  rather than the sum of the two.
- **Different protein in each meal**, and nothing repeated from the last three
  weeks.
- **Protein per portion is computed, not asserted.** Every figure in the app is
  summed from `scripts/data/ingredients.json` at the gram amounts the recipe
  actually calls for. Change a quantity and the macros, the shopping list and
  the pack counts all follow.
- **Seeded by the week**, so re-running the generator for a given week gives the
  same plan — including a re-run after the week has already been published,
  which must not move meals you may have shopped for.

### Where the meals sit in the week

Cooked on Sunday and eaten through Friday is six days, which is too long for
food to sit chilled. So:

- Monday, Tuesday and Wednesday portions go in the fridge.
- Thursday and Friday portions are frozen on Sunday and moved down to the
  fridge on Wednesday evening.
- A **fish** meal is always the one eaten Monday and Tuesday, and never gets
  frozen — cooked fish keeps about two days, and fish bought frozen shouldn't be
  refrozen after cooking.

That last rule is why a fish week splits 2+3 instead of the usual 3+2.

## The recipe library

Ten recipes, each landing between 66 and 82 g of protein and 14–27 g of fibre
per portion. Constraints they're written to:

- **No pork.**
- **Salmon is wild-caught only** — the `wild_salmon` ingredient is the MSC Alaska
  line, and the tests fail if that changes.
- **Everything reheats in a microwave**, since these are eaten at a desk.
- **Everything is sold at Rewe**, listed under the German name on the shelf.

## Running it yourself

```sh
python3 scripts/generate_week.py            # write next week's plan
python3 scripts/generate_week.py --dry-run  # print it without writing
python3 scripts/generate_week.py --date 2026-09-11   # pretend it's that Friday
python3 scripts/test_plan.py                # the checks below
python3 scripts/make_icons.py               # redraw the app icons

python3 -m http.server 8000 --directory app # then open localhost:8000
```

No dependencies beyond Python 3 — the icons are drawn by a hand-rolled PNG
writer rather than an image library.

`app/index.html` also opens straight off the filesystem: the generator writes
the plan a second time as `app/data/plan.js`, which the page falls back to when
`fetch` of a local file is blocked.

## The checks

`scripts/test_plan.py` runs the rules over all ten recipes and 52 generated
weeks. It fails if a recipe drifts out of the 57–85 g protein window or under
10 g fibre, if step timings stop adding up to the stated total, if a week ever
pairs two oven dishes or two meals with the same protein, if the Sunday cook
would run past 90 minutes, if a fish portion is scheduled into the freezer, if
the shopping list buys less of anything than the recipes need, or if
regenerating one week twice produces two different plans.

## Adding a recipe

Append to `scripts/data/recipes.json` with per-portion gram amounts keyed to
`ingredients.json`, a `track` of `oven` or `stovetop`, and `step_at`/`step_min`
arrays whose last step lands exactly on `total_min`. Add any new ingredient to
`ingredients.json` with its per-100 g nutrition, German shelf name and Rewe pack
size. Then run `python3 scripts/test_plan.py` — it will tell you if the protein,
fibre or timings don't hold up.

Ten recipes gives about five weeks before the no-repeat rule starts reusing
pairs, so the library is worth growing.

## Automation

`.github/workflows/meal-plan.yml` runs at 04:00 UTC each Friday — 06:00 in
Berlin in summer, 05:00 in winter — regenerates the plan, commits it, and
deploys `app/` to GitHub Pages. It runs the checks first, so a broken recipe
stops the plan rather than shipping it. Pushes to `main` redeploy the app
without touching the current week's meals.
