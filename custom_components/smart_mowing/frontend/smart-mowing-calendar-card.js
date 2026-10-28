// Compact month calendar for Smart Mowing: past mows and the planned next mow.
// Served by the integration itself, so it needs no separate HACS install.
//
//   type: custom:smart-mowing-calendar-card
//   history_entity: calendar.mahkalender          # days to mark as mowed
//   plan_entity: calendar.<name>_mow_plan          # the forecast next mow
//   title: Mähtage                                 # optional

const STRINGS = {
  de: { title: "Mähtage", mowed: "Gemäht", planned: "Geplant", count: (n, m) => `${n} Mähtag${n === 1 ? "" : "e"} im ${m}`, next: "nächstes" },
  en: { title: "Mow days", mowed: "Mowed", planned: "Planned", count: (n, m) => `${n} mow day${n === 1 ? "" : "s"} in ${m}`, next: "next" },
};

const pad = (n) => String(n).padStart(2, "0");
const isoDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function eventDays(events) {
  // All-day events end exclusively; timed events count on their start day.
  const days = new Set();
  for (const e of events || []) {
    if (e.start && e.start.date) {
      const d = new Date(`${e.start.date}T00:00:00`);
      const end = new Date(`${(e.end && e.end.date) || e.start.date}T00:00:00`);
      do {
        days.add(isoDay(d));
        d.setDate(d.getDate() + 1);
      } while (d < end);
    } else if (e.start && e.start.dateTime) {
      days.add(isoDay(new Date(e.start.dateTime)));
    }
  }
  return days;
}

class SmartMowingCalendarCard extends HTMLElement {
  setConfig(config) {
    if (!config.history_entity && !config.plan_entity) {
      throw new Error("history_entity or plan_entity is required");
    }
    this._config = config;
    this._offset = 0;
    this._mowed = new Set();
    this._planned = new Set();
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const plan = this._config.plan_entity && hass.states[this._config.plan_entity];
    // reload on month change, when the plan moves, and every 30 minutes
    const key = [
      this._offset,
      plan && plan.attributes.start_time,
      Math.floor(Date.now() / 1800000),
    ].join("|");
    if (key !== this._key) {
      this._key = key;
      this._load();
    }
  }

  get _lang() {
    const lang = ((this._hass && this._hass.language) || "en").split("-")[0];
    return STRINGS[lang] ? lang : "en";
  }

  _month() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth() + this._offset, 1);
  }

  async _fetch(entity, start, end) {
    if (!entity) return [];
    try {
      return await this._hass.callApi(
        "GET",
        `calendars/${entity}?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
      );
    } catch (err) {
      console.warn("smart-mowing-calendar-card: could not load", entity, err);
      return [];
    }
  }

  async _load() {
    const first = this._month();
    const start = new Date(first.getFullYear(), first.getMonth(), 1);
    const end = new Date(first.getFullYear(), first.getMonth() + 1, 1);
    const [history, plan] = await Promise.all([
      this._fetch(this._config.history_entity, start, end),
      this._fetch(this._config.plan_entity, start, end),
    ]);
    this._mowed = eventDays(history);
    this._planned = eventDays(plan);
    this._render();
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const t = STRINGS[this._lang];
    const locale = (this._hass && this._hass.language) || "en";
    const first = this._month();
    const daysInMonth = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
    const lead = (first.getDay() + 6) % 7; // Monday first
    const today = isoDay(new Date());
    const monthName = first.toLocaleDateString(locale, { month: "long" });

    const weekdays = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(2024, 0, 1 + i); // 2024-01-01 is a Monday
      weekdays.push(`<div class="wd">${d.toLocaleDateString(locale, { weekday: "short" }).replace(".", "")}</div>`);
    }
    const cells = [];
    for (let i = 0; i < lead; i++) cells.push('<div class="day empty"></div>');
    let count = 0;
    for (let n = 1; n <= daysInMonth; n++) {
      const key = isoDay(new Date(first.getFullYear(), first.getMonth(), n));
      const cls = ["day"];
      if (this._mowed.has(key)) {
        cls.push("mowed");
        count++;
      }
      if (this._planned.has(key)) cls.push("planned");
      if (key === today) cls.push("today");
      cells.push(`<div class="${cls.join(" ")}"><span>${n}</span></div>`);
    }

    let next = "";
    const plan = this._hass && this._config.plan_entity && this._hass.states[this._config.plan_entity];
    if (plan && plan.attributes.start_time) {
      const d = new Date(plan.attributes.start_time.replace(" ", "T"));
      next = ` · ${t.next}: ${d.toLocaleDateString(locale, { day: "numeric", month: "numeric" })}`;
    }

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 12px 16px 14px; color: var(--primary-text-color); }
        .hdr { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
        .title { font-size: 1.15em; font-weight: 500; }
        .nav { display: flex; align-items: center; gap: 4px; color: var(--secondary-text-color); }
        .nav button { background: none; border: none; cursor: pointer; color: inherit; font-size: 1.2em; padding: 0 6px; line-height: 1; }
        .nav .m { min-width: 7.5em; text-align: center; font-size: 0.95em; }
        .grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px 2px; justify-items: center; }
        .wd { font-size: 0.75em; color: var(--secondary-text-color); padding-bottom: 2px; }
        .day { width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
               font-size: 0.85em; box-sizing: border-box; border: 2px solid transparent; }
        .day.mowed { background: var(--success-color, #43a047); color: #fff; }
        .day.planned { border: 2px dashed var(--warning-color, #fb8c00); color: var(--warning-color, #fb8c00); font-weight: 600; }
        .day.today { box-shadow: 0 0 0 2px var(--primary-color); font-weight: 600; }
        .foot { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 4px 12px; margin-top: 10px;
                font-size: 0.8em; color: var(--secondary-text-color); }
        .legend span { display: inline-flex; align-items: center; gap: 4px; margin-right: 10px; }
        .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; box-sizing: border-box; }
        .dot.mowed { background: var(--success-color, #43a047); }
        .dot.planned { border: 2px dashed var(--warning-color, #fb8c00); }
      </style>
      <ha-card>
        <div class="hdr">
          <span class="title">${this._config.title || t.title}</span>
          <span class="nav">
            <button class="prev" aria-label="previous">‹</button>
            <span class="m">${first.toLocaleDateString(locale, { month: "long", year: "numeric" })}</span>
            <button class="next" aria-label="next">›</button>
          </span>
        </div>
        <div class="grid">${weekdays.join("")}${cells.join("")}</div>
        <div class="foot">
          <span class="legend"><span><i class="dot mowed"></i>${t.mowed}</span><span><i class="dot planned"></i>${t.planned}</span></span>
          <span>${t.count(count, monthName)}${next}</span>
        </div>
      </ha-card>`;
    this.shadowRoot.querySelector(".prev").onclick = () => this._shift(-1);
    this.shadowRoot.querySelector(".next").onclick = () => this._shift(1);
  }

  _shift(delta) {
    this._offset += delta;
    if (this._hass) this.hass = this._hass;
  }

  getCardSize() {
    return 5;
  }

  getGridOptions() {
    return { columns: 6, min_columns: 4, rows: "auto" };
  }
}

if (!customElements.get("smart-mowing-calendar-card")) {
  customElements.define("smart-mowing-calendar-card", SmartMowingCalendarCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "smart-mowing-calendar-card",
    name: "Smart Mowing calendar",
    description: "Compact month view of mowed days and the planned next mow.",
  });
}
