/* Microgreens single-plot card */
window.customCards = window.customCards || [];
window.customCards.push({
  type: "microgreens-plot-card",
  name: "Microgreens Plot Card",
  description: "Shows a single microgreens plot"
});

class MicrogreensPlotCard extends HTMLElement {
  setConfig(cfg) {
    if (!cfg || !cfg.plot_id) throw new Error("plot_id is required");
    this._cfg = cfg;
  }
  getCardSize(){ return 2; }

  set hass(h) {
    this._hass = h;
    if (!this._root) this._render();
    this._update();
  }

  _eid(id){ return `sensor.microgreens_plot_${String(id).toLowerCase()}`; }

  _render() {
    const r = (this._root = this.attachShadow({mode:"open"}));
    const css = document.createElement("style");
    css.textContent = `
      .tile{padding:12px;border:1px solid var(--divider-color);border-radius:12px}
      .hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
      .title{font-weight:700}
      .left{display:flex;gap:10px;align-items:baseline}
      .state{text-transform:capitalize}
      .state.idle{color:var(--secondary-text-color)}
      .state.covered{color:var(--warning-color)}
      .state.uncovered{color:var(--primary-color)}
      .state.mature{color:var(--success-color,#00c853)}
      .muted{color:var(--secondary-text-color);font-size:12px}
      .row{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:start;margin-top:8px}
      .btns{display:flex;justify-content:flex-end}
      button{padding:8px 12px;border-radius:10px;border:1px solid var(--primary-color);background:var(--primary-color);color:#fff;cursor:pointer;font-weight:500}
      button.secondary{background:var(--secondary-background-color);color:var(--primary-text-color);border-color:var(--divider-color)}
      button.ok-anim{
        background:var(--success-color,#00c853)!important;
        border-color:var(--success-color,#00c853)!important;
        transition:background 120ms ease,border-color 120ms ease,transform 120ms ease;
        transform:scale(1.02)
      }
      @keyframes mg-pulse{0%{transform:scale(1)}50%{transform:scale(1.06)}100%{transform:scale(1)}}
      button.ok-anim{animation:mg-pulse 220ms ease-out}
      /* compact mode */
      :host([compact]) .tile{padding:8px}
      :host([compact]) .muted{font-size:11px}
      :host([compact]) button{padding:6px 10px;border-radius:8px}
    `;
    r.appendChild(css);

    const card = document.createElement("ha-card");
    card.innerHTML = `
      <div class="tile">
        <div class="hdr">
          <div class="left">
            <div id="t" class="title"></div>
            <div id="state" class="state idle">idle</div>
          </div>
          <div id="plant" class="muted"></div>
        </div>
        <div class="row">
          <div>
            <div id="un" class="muted">Uncover: —</div>
            <div id="hv" class="muted">Harvest: —</div>
          </div>
          <div class="btns">
            <button id="clear" class="secondary" data-label="Clear">Clear</button>
          </div>
        </div>
      </div>
    `;
    r.appendChild(card);

    r.getElementById("clear").onclick = async () => {
      const pid = this._cfg.plot_id;
      if (!pid) return;
      const s = this._hass.states[this._eid(pid)];
      if (!s || s.state === "idle") return; // nothing to clear
      if (!confirm(`Clear plot ${pid}?`)) return;
      await this._hass.callService("microgreens","unassign",{plot_id: pid});
      this._flashOK(r.getElementById("clear"));
    };
  }

  _flashOK(btn){
    if (!btn) return;
    const prev = btn.textContent;
    btn.classList.add("ok-anim");
    btn.textContent = "✓";
    setTimeout(()=>{ btn.classList.remove("ok-anim"); btn.textContent = prev; }, 500);
  }

  _update() {
    const id = this._cfg.plot_id;
    const e = this._hass.states[this._eid(id)];
    const t = this._root.getElementById("t");
    const st = this._root.getElementById("state");
    const plant = this._root.getElementById("plant");
    const un = this._root.getElementById("un");
    const hv = this._root.getElementById("hv");

    const title = this._cfg.title || `Plot ${id}`;
    t.textContent = title;

    const state = e ? e.state : "idle";
    st.className = `state ${state}`;
    st.textContent = state;

    const a = e ? e.attributes : {};
    plant.textContent = a.plant_name || "";

    un.textContent = `Uncover: ${a.cover_end || "—"}`;
    hv.textContent = `Harvest: ${a.harvest_date || "—"}`;

    // compact attribute toggle
    if (this._cfg.compact) this.setAttribute("compact",""); else this.removeAttribute("compact");
    // disable Clear when idle
    this._root.getElementById("clear").disabled = (state === "idle");
  }
}

if (!customElements.get("microgreens-plot-card")) {
  customElements.define("microgreens-plot-card", MicrogreensPlotCard);
}
