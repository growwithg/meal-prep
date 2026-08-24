/* Prep — weekly meal-prep planner.
   Renders app/data/plan.json. Tick state lives in localStorage, keyed by week,
   so a new plan on Friday starts with a clean list without wiping this week's. */

(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const views = {
    week: $("#view-week"),
    shop: $("#view-shop"),
    cook: $("#view-cook"),
  };

  let plan = null;
  let state = { shop: {}, steps: {} };
  let cookTab = "timeline";

  /* ── persistence ───────────────────────────────────────────────────────── */

  const storeKey = () => `prep:${plan.week_id}`;

  function loadState() {
    try {
      const raw = localStorage.getItem(storeKey());
      if (raw) state = Object.assign({ shop: {}, steps: {} }, JSON.parse(raw));
    } catch {
      /* Private mode or blocked storage — run without persistence. */
    }
  }

  function saveState() {
    try {
      localStorage.setItem(storeKey(), JSON.stringify(state));
      pruneOldWeeks();
    } catch { /* ignore */ }
  }

  function pruneOldWeeks() {
    try {
      const keys = Object.keys(localStorage).filter(k => k.startsWith("prep:")).sort();
      keys.slice(0, Math.max(0, keys.length - 6)).forEach(k => localStorage.removeItem(k));
    } catch { /* ignore */ }
  }

  /* ── helpers ───────────────────────────────────────────────────────────── */

  const esc = s => String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const fmtDate = (iso, opts = { weekday: "long", day: "numeric", month: "long" }) =>
    new Date(iso + "T12:00:00").toLocaleDateString("en-GB", opts);

  // "Sun 30 Aug" — the comma costs width the narrow date cell doesn't have.
  const shortDate = iso =>
    fmtDate(iso, { weekday: "short", day: "numeric", month: "short" }).replace(",", "");

  const todayName = () =>
    new Date().toLocaleDateString("en-GB", { weekday: "long" });

  function daysUntil(iso) {
    const target = new Date(iso + "T12:00:00");
    const now = new Date();
    now.setHours(12, 0, 0, 0);
    return Math.round((target - now) / 86400000);
  }

  function relative(iso) {
    const d = daysUntil(iso);
    if (d === 0) return "today";
    if (d === 1) return "tomorrow";
    if (d < 0) return `${-d} day${d === -1 ? "" : "s"} ago`;
    return `in ${d} days`;
  }

  const CHECK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>`;
  const ALERT = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 8.5v5M12 17h.01"/><circle cx="12" cy="12" r="9.2"/></svg>`;

  /* ── week view ─────────────────────────────────────────────────────────── */

  function renderWeek() {
    const { dates, targets, summary } = plan;
    const today = todayName();

    const overdue = daysUntil(dates.shop_by) < 0;
    const shopLeft = countUnchecked();

    const cards = plan.meals.map(m => {
      const pct = Math.min(100, m.macros.protein / targets.protein_per_day * 100);
      const lo = targets.lunch_min / targets.protein_per_day * 100;
      const hi = targets.lunch_max / targets.protein_per_day * 100;
      const days = plan.schedule.filter(s => s.recipe_id === m.id).map(s => s.day.slice(0, 3));
      return `
        <article class="glass card">
          <div class="row-between">
            <div class="grow">
              <div class="row" style="gap:8px;margin-bottom:8px">
                <span class="pill accent">Meal ${esc(m.label)}</span>
                <span class="pill">${m.portions} portions</span>
                ${m.cold_ok ? '<span class="pill cool">Good cold</span>' : ""}
              </div>
              <h2>${esc(m.name)}</h2>
              <p class="muted tiny" style="margin:6px 0 0">
                ${esc(days.join(" · "))} · ${m.total_min} min · ${esc(m.track)}
              </p>
            </div>
          </div>

          <div class="macros">
            <div class="macro"><b>${m.macros.protein}g</b><span>Protein</span></div>
            <div class="macro"><b>${m.macros.carbs}g</b><span>Carbs</span></div>
            <div class="macro"><b>${m.macros.fiber}g</b><span>Fibre</span></div>
            <div class="macro"><b>${Math.round(m.macros.kcal)}</b><span>kcal</span></div>
          </div>

          <div class="meter">
            <div class="meter-track">
              <div class="meter-zone" style="left:${lo}%;width:${hi - lo}%"></div>
              <div class="meter-fill" style="width:${pct}%"></div>
            </div>
            <p class="tiny faint" style="margin:8px 0 0">
              ${Math.round(pct)}% of your ${targets.protein_per_day} g day —
              the hatched band is the ${targets.lunch_min}–${targets.lunch_max} g you wanted from lunch.
            </p>
          </div>
        </article>`;
    }).join("");

    views.week.innerHTML = `
      <article class="glass card">
        <dl class="keydates">
          <div><dt>Shop by</dt><dd>${shortDate(dates.shop_by)}</dd></div>
          <div><dt>Cook</dt><dd>${shortDate(dates.cook_on)}</dd></div>
          <div><dt>Hands-on</dt><dd>~${summary.cook_minutes} min</dd></div>
        </dl>
        <div class="row" style="gap:8px;margin-top:14px;flex-wrap:wrap">
          <span class="pill ${overdue ? "warn" : "accent"}">Shopping ${esc(relative(dates.shop_by))}</span>
          ${shopLeft > 0
            ? `<span class="pill">${shopLeft} item${shopLeft === 1 ? "" : "s"} left to buy</span>`
            : `<span class="pill accent">List complete</span>`}
        </div>
      </article>

      ${cards}

      <p class="section-label">The five days</p>
      <article class="glass card">
        <div class="days">
          ${plan.schedule.map(s => `
            <div class="day${s.day === today ? " is-today" : ""}">
              <b>${esc(s.day.slice(0, 3))}</b>
              <span class="name">${esc(s.recipe_name)}</span>
              <span class="pill ${s.storage === "freezer" ? "cool" : ""}">${s.storage === "freezer" ? "Freeze" : "Fridge"}</span>
            </div>`).join("")}
        </div>
        <div class="note" style="margin-top:14px">
          ${ALERT}
          <span>Thursday and Friday go in the freezer on Sunday and move down to the fridge
          on Wednesday evening. Five days is too long for cooked food to sit chilled.</span>
        </div>
      </article>`;
  }

  /* ── shop view ─────────────────────────────────────────────────────────── */

  function countUnchecked() {
    let n = 0;
    plan.groceries.forEach(g => g.items.forEach(i => {
      if (!i.pantry && !state.shop[i.id]) n++;
    }));
    return n;
  }

  function countAll() {
    return plan.groceries.reduce((n, g) => n + g.items.filter(i => !i.pantry).length, 0);
  }

  function renderShop() {
    const total = countAll();
    const done = total - countUnchecked();
    const pct = total ? done / total : 0;
    const C = 2 * Math.PI * 23;

    const group = g => `
      <p class="section-label">${esc(g.aisle)}</p>
      <article class="glass list">
        ${g.items.map(i => `
          <button class="check" data-shop="${esc(i.id)}" aria-pressed="${!!state.shop[i.id]}">
            <span class="box">${CHECK}</span>
            <span class="grow">
              <span class="label">${esc(i.de)}</span>
              <span class="sub">${esc(i.en)} · need ${i.need} ${esc(i.unit)}${i.note ? " · " + esc(i.note) : ""}</span>
            </span>
            <span class="qty">${esc(i.buy_label)}</span>
          </button>`).join("")}
      </article>`;

    const shelf = plan.groceries.filter(g => g.items.some(i => !i.pantry));
    const pantry = plan.groceries.filter(g => g.items.every(i => i.pantry));

    views.shop.innerHTML = `
      <article class="glass card">
        <div class="progress">
          <svg class="ring" viewBox="0 0 52 52" aria-hidden="true">
            <circle class="bg" cx="26" cy="26" r="23"/>
            <circle class="fg" cx="26" cy="26" r="23"
                    stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - pct)}"/>
          </svg>
          <div class="grow">
            <h2>${done} of ${total}</h2>
            <p class="muted tiny" style="margin:4px 0 0">
              Everything in stock by ${fmtDate(plan.dates.shop_by, { weekday: "long" })} —
              ${esc(relative(plan.dates.shop_by))}.
            </p>
          </div>
          <button class="btn" id="resetShop" type="button">Reset</button>
        </div>
      </article>
      ${shelf.map(group).join("")}
      ${pantry.length ? `
        <p class="section-label">Already in the cupboard?</p>
        <article class="glass list">
          ${pantry[0].items.map(i => `
            <button class="check" data-shop="${esc(i.id)}" aria-pressed="${!!state.shop[i.id]}">
              <span class="box">${CHECK}</span>
              <span class="grow"><span class="label">${esc(i.de)}</span>
              <span class="sub">${esc(i.en)} · about ${i.need} ${esc(i.unit)} needed</span></span>
            </button>`).join("")}
        </article>
        <p class="tiny faint" style="margin:10px 6px 0">
          Staples aren’t counted in the total — glance down the list and only buy what has run out.
        </p>` : ""}`;
  }

  /* ── cook view ─────────────────────────────────────────────────────────── */

  function renderCook() {
    const segs = [["timeline", "Sunday run"], ...plan.meals.map(m => [m.id, `Meal ${m.label}`])];

    let body;
    if (cookTab === "timeline") {
      body = `
        <article class="glass card">
          <h2>Both pans at once</h2>
          <p class="muted tiny" style="margin:6px 0 0">
            One oven dish and one stovetop dish, started together at T+0 and finished
            in about ${plan.summary.cook_minutes} minutes.
          </p>
          <div class="legend">
            ${plan.meals.map((m, i) => {
              const lane = i === 0 ? "A" : "B";
              return `<div><i class="lane-${lane}"></i><b>${lane}</b><span class="grow">${esc(m.name)}</span></div>`;
            }).join("")}
          </div>
        </article>
        <article class="glass card">
          <div class="tl">
            ${plan.timeline.map(e => {
              const key = `tl:${e.recipe_id}:${e.step}`;
              return `
              <div class="tl-item">
                <div class="tl-time">T+${e.at}′</div>
                <div class="tl-body">
                  <span class="tl-dot lane-${e.lane}"></span>
                  <button class="check" data-step="${esc(key)}" aria-pressed="${!!state.steps[key]}" style="padding-left:0">
                    <span class="box">${CHECK}</span>
                    <span class="grow">
                      <span class="lane-tag lane-${e.lane}">${e.lane} · ${esc(e.track)} · ${e.minutes}′</span>
                      <span class="label" style="display:block;margin-top:6px">${esc(e.text)}</span>
                    </span>
                  </button>
                </div>
              </div>`;
            }).join("")}
          </div>
        </article>`;
    } else {
      const m = plan.meals.find(x => x.id === cookTab);
      body = `
        <article class="glass card">
          <h2>${esc(m.name)}</h2>
          <div class="row" style="gap:8px;margin:10px 0 0;flex-wrap:wrap">
            <span class="pill accent">${m.portions} portions</span>
            <span class="pill">${m.total_min} min</span>
            <span class="pill">${m.macros.protein} g protein each</span>
          </div>
          <div class="note" style="margin-top:14px">${ALERT}<span>${esc(m.reheat)}</span></div>
        </article>

        <p class="section-label">For ${m.portions} portions</p>
        <article class="glass list">
          ${m.ingredients.map(i => `
            <div class="check" style="cursor:default">
              <span class="grow"><span class="label">${esc(i.de)}</span>
              <span class="sub">${esc(i.en)} · ${i.per_portion} ${esc(i.unit)} per portion</span></span>
              <span class="qty">${i.total} ${esc(i.unit)}</span>
            </div>`).join("")}
        </article>

        <p class="section-label">Method</p>
        <article class="glass list">
          <ol class="steps">
            ${m.steps.map((s, i) => {
              const key = `st:${m.id}:${i + 1}`;
              return `<li><button class="check" data-step="${esc(key)}" aria-pressed="${!!state.steps[key]}">
                <span class="n">${i + 1}</span>
                <span class="grow"><span class="label">${esc(s)}</span></span>
              </button></li>`;
            }).join("")}
          </ol>
        </article>`;
    }

    views.cook.innerHTML = `
      <div class="seg" role="tablist" aria-label="Cook views" style="margin-bottom:14px">
        ${segs.map(([id, label]) =>
          `<button role="tab" data-cook="${esc(id)}" aria-selected="${cookTab === id}">${esc(label)}</button>`).join("")}
      </div>
      ${body}`;
  }

  /* ── shell ─────────────────────────────────────────────────────────────── */

  function renderHeader() {
    $("#weekId").textContent = `Week ${plan.week_id.split("-W")[1]} · ${plan.week_id.split("-")[0]}`;
    $("#dateline").textContent =
      `${fmtDate(plan.dates.week_start, { day: "numeric", month: "long" })} – ` +
      `${fmtDate(plan.dates.week_end, { day: "numeric", month: "long", year: "numeric" })}`;
  }

  function renderBadge() {
    const badge = $("#shopBadge");
    const n = countUnchecked();
    badge.textContent = n;
    badge.hidden = n === 0;
  }

  function renderAll() {
    renderHeader();
    renderWeek();
    renderShop();
    renderCook();
    renderBadge();
  }

  function moveThumb() {
    const tabs = $(".tabs");
    const active = tabs.querySelector('[aria-selected="true"]');
    const thumb = $(".thumb");
    thumb.style.width = `${active.offsetWidth}px`;
    thumb.style.transform = `translateX(${active.offsetLeft - 5}px)`;
  }

  function show(name) {
    Object.entries(views).forEach(([k, el]) => { el.hidden = k !== name; });
    document.querySelectorAll(".tabs [role=tab]").forEach(b =>
      b.setAttribute("aria-selected", String(b.dataset.view === name)));
    moveThumb();
    window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  }

  document.addEventListener("click", e => {
    const tab = e.target.closest(".tabs [role=tab]");
    if (tab) return show(tab.dataset.view);

    const seg = e.target.closest("[data-cook]");
    if (seg) { cookTab = seg.dataset.cook; renderCook(); return; }

    if (e.target.closest("#resetShop")) {
      state.shop = {};
      saveState();
      renderAll();
      return;
    }

    const shop = e.target.closest("[data-shop]");
    if (shop) {
      const id = shop.dataset.shop;
      state.shop[id] = !state.shop[id];
      shop.setAttribute("aria-pressed", String(!!state.shop[id]));
      saveState();
      renderBadge();
      // Keep the counter and ring honest without rebuilding the list under the thumb.
      const total = countAll(), done = total - countUnchecked();
      const h2 = views.shop.querySelector("h2");
      if (h2) h2.textContent = `${done} of ${total}`;
      const ring = views.shop.querySelector(".ring .fg");
      if (ring) {
        const C = 2 * Math.PI * 23;
        ring.setAttribute("stroke-dashoffset", C * (1 - (total ? done / total : 0)));
      }
      return;
    }

    const step = e.target.closest("[data-step]");
    if (step) {
      const id = step.dataset.step;
      state.steps[id] = !state.steps[id];
      step.setAttribute("aria-pressed", String(!!state.steps[id]));
      saveState();
    }
  });

  window.addEventListener("resize", moveThumb);

  /* ── boot ──────────────────────────────────────────────────────────────── */

  async function boot() {
    try {
      // Network first so a Friday regeneration shows up, embedded copy as fallback
      // (also what makes the page work opened straight off the filesystem).
      const res = await fetch("data/plan.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status);
      plan = await res.json();
    } catch {
      plan = window.__PLAN__ || null;
    }

    if (!plan) {
      $("#dateline").textContent = "No plan found.";
      views.week.innerHTML = `<article class="glass card empty">
        <p>Couldn’t load this week’s plan.</p>
        <p class="tiny">Run <code>python3 scripts/generate_week.py</code>, or reopen once you’re back online.</p>
      </article>`;
      return;
    }

    loadState();
    renderAll();
    requestAnimationFrame(moveThumb);

    if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
      navigator.serviceWorker.register("sw.js").catch(() => {});
    }
  }

  boot();
})();
