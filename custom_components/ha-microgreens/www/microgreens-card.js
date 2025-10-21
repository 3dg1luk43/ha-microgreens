window.customCards = window.customCards || [];
window.customCards.push({ type: "microgreens-card", name: "Microgreens Card", description: "Manage microgreens" });

class MicrogreensCard extends HTMLElement {
  setConfig(c){ this._config=c||{}; }
  getCardSize(){ return 4; }
  set hass(h){
    this._hass = h;
    if (!this._root) this._render();
    this._update();

    if (this._isOpen("dlgPlots")) {
      const sel = this._root.getElementById("pl_select");
      const inNew = this._isPlotsNew() || (sel && !sel.value);

      // If creating a new plot and user is typing, do not refresh the modal
      if (inNew && (this._isFocused("pl_id") || this._isFocused("pl_label"))) return;

      // Otherwise refresh, but don't clobber ID/Label if focused (handled inside _refreshPlotsModal)
      this._refreshPlotsModal();
    }
  }

  _render(){
    const r=this._root=this.attachShadow({mode:"open"});
    const css=document.createElement("style");
    css.textContent = `
      /* base layout */
      .wrap{padding:12px;}
      .actions{display:flex;gap:10px;margin:8px 0;flex-wrap:wrap}

      /* buttons */
      button{padding:8px 12px;border-radius:10px;border:1px solid var(--primary-color);background:var(--primary-color);color:#fff;cursor:pointer;font-weight:500}
      button.secondary{background:var(--secondary-background-color);color:var(--primary-text-color);border-color:var(--divider-color)}
      button.small{padding:4px 10px;font-size:12px;border-radius:8px}

      /* tiles grid */
      .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
      .tile{padding:12px;border:1px solid var(--divider-color);border-radius:12px}

      /* tile header */
      .hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
      .left{display:flex;gap:10px;align-items:baseline}
      .title{font-weight:700}
      .state{text-transform:capitalize}
      .state.idle{color:var(--secondary-text-color)}
      .state.covered{color:var(--warning-color)}
      .state.uncovered{color:var(--primary-color)}
      .state.mature{color:var(--success-color,#00c853)}
      .muted{color:var(--secondary-text-color);font-size:12px}

      /* dialogs */
      dialog::backdrop{background:rgba(0,0,0,.4)}
      dialog{border:none;border-radius:12px;padding:16px;background:var(--card-background-color);color:var(--primary-text-color);min-width:420px;max-width:95vw}
      .modal-head{display:flex;align-items:center;justify-content:space-between;margin:0 0 8px 0}
      .modal-close{padding:4px 10px;border-radius:8px;border:1px solid var(--divider-color);background:var(--secondary-background-color);color:var(--primary-text-color);cursor:pointer}

      /* forms */
      label{font-size:12px;color:var(--secondary-text-color)}
      .field label{display:block;font-size:12px;color:var(--secondary-text-color);margin-bottom:4px}
      select,input[type="date"],input[type="text"],input[type="number"]{padding:8px;min-width:170px;border-radius:8px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color)}
      input.invalid{border-color:var(--error-color)}
      .row{display:flex;gap:10px;align-items:center;margin:8px 0;flex-wrap:wrap}
      .end,.btns{display:flex;justify-content:flex-end;gap:10px;margin-top:10px}

      /* Profiles: 3-col grid (Name aligns above Uncover) */
      .pf-grid{display:grid;grid-template-columns:repeat(3,minmax(140px,1fr));gap:10px;margin:8px 0}
      .pf-grid .col1{grid-column:1}
      .pf-grid .col2{grid-column:2}
      .pf-grid .col3{grid-column:3}
      .pf-grid .row1{grid-row:1}
      .pf-grid .row2{grid-row:2}
      .pf-grid .wide{grid-column:1 / -1}

      /* Plot body: text left, Clear button right */
      .meta-row-right{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:start;margin-top:8px}
      .meta-left .line{margin:2px 0}
      .meta-right{display:flex;justify-content:flex-end;align-items:flex-start}

      /* success flash (✓) */
      button.ok-anim{
        background:var(--success-color,#00c853)!important;
        border-color:var(--success-color,#00c853)!important;
        transition:background 120ms ease,border-color 120ms ease,transform 120ms ease;
        transform:scale(1.02)
      }
      @keyframes mg-pulse{0%{transform:scale(1)}50%{transform:scale(1.06)}100%{transform:scale(1)}}
      button.ok-anim{animation:mg-pulse 220ms ease-out}

      /* responsive tweaks */
      @media (max-width:900px){
        .pf-grid{grid-template-columns:repeat(2,minmax(140px,1fr))}
        .pf-grid .col3{grid-column:1 / -1} /* Water drops under on tablets */
      }
      @media (max-width:500px){
        .grid{grid-template-columns:1fr}
        dialog{min-width:0}
        select,input{min-width:140px}
        .pf-grid{grid-template-columns:1fr}
        .pf-grid .col1,.pf-grid .col2,.pf-grid .col3,.pf-grid .wide{grid-column:1;grid-row:auto}
      }
      @media (max-width:480px){
        .meta-row-right{grid-template-columns:1fr}
        .meta-right{justify-content:flex-start;margin-top:6px}
      }
    `;

    r.appendChild(css);

    const card=document.createElement("ha-card");
    card.innerHTML=`
      <div class="wrap">
        <div class="actions">
          <button id="btnDeploy">Deploy</button>
          <button id="btnProfiles" class="secondary">Profiles</button>
          <button id="btnPlots" class="secondary">Plots</button>
        </div>
        <div id="grid" class="grid"></div>
      </div>

      <!-- Deploy dialog -->
      <dialog id="dlgDeploy">
        <h3>Deploy</h3>
        <div class="row">
          <div><label>Idle plot</label><br/><select id="d_plot"></select></div>
          <div><label>Profile</label><br/><select id="d_profile"></select></div>
          <div><label>Start</label><br/><input id="d_start" type="date"></div>
        </div>
        <div class="end">
          <button id="d_cancel" class="secondary">Cancel</button>
          <button id="d_ok" data-label="Deploy">Deploy</button>
        </div>
      </dialog>

      <!-- Profiles dialog -->
      <dialog id="dlgProfiles">
        <div class="modal-head">
          <h3 style="margin:0">Profiles</h3>
          <button id="p_close" class="modal-close">Close</button>
        </div>

        <div class="field" style="margin-bottom:8px;">
          <label>Select profile</label>
          <select id="p_select"></select>
        </div>

        <div class="pf-grid">
          <!-- Row 1 -->
          <div class="field col1 row1">
            <label>ID *</label>
            <input id="p_id" type="text" placeholder="rukola">
          </div>
          <div class="field col2 row1">
            <label>Name *</label>
            <input id="p_name" type="text" placeholder="Rukola">
          </div>
          <!-- (column 3 row1 intentionally empty to keep columns aligned) -->

          <!-- Row 2 -->
          <div class="field col1 row2">
            <label>Cover days</label>
            <input id="p_cover" type="number" min="0" inputmode="numeric" placeholder="3">
          </div>
          <div class="field col2 row2">
            <label>Uncover days</label>
            <input id="p_uncover" type="number" min="0" inputmode="numeric" placeholder="8">
          </div>
          <div class="field col3 row2">
            <label>Water every (days)</label>
            <input id="p_water" type="number" min="0" inputmode="numeric" placeholder="1">
          </div>

          <!-- Notes full width -->
          <div class="field wide">
            <label>Notes</label>
            <input id="p_notes" type="text" placeholder="Any specific handling">
          </div>
        </div>


        <div class="btns">
          <button id="p_new" class="secondary" data-label="New">New</button>
          <button id="p_delete" class="secondary" data-label="Delete">Delete</button>
          <button id="p_save" data-label="Save" disabled>Save</button>
        </div>
      </dialog>

      <!-- Plots dialog -->
      <dialog id="dlgPlots">
        <div class="modal-head">
          <h3 style="margin:0">Plots</h3>
          <button id="pl_close" class="modal-close">Close</button>
        </div>

        <div class="row" style="margin-bottom:8px">
          <div style="flex:1;min-width:220px">
            <label>Select plot</label><br/>
            <select id="pl_select"></select>
          </div>
        </div>

        <div class="row">
          <div>
            <label>ID *</label><br/>
            <input id="pl_id" type="text" placeholder="A7">
          </div>
          <div style="flex:1;min-width:220px">
            <label>Label *</label><br/>
            <input id="pl_label" type="text" placeholder="Tray A7">
          </div>
        </div>

        <div class="btns">
          <button id="pl_new" class="secondary" data-label="New">New</button>
          <button id="pl_delete" class="secondary" data-label="Delete">Delete</button>
          <button id="pl_save" data-label="Save" disabled>Save</button>
        </div>
      </dialog>

    `;
    r.appendChild(card);

    // buttons
    r.getElementById("btnDeploy").onclick=()=>this._openDeploy();
    r.getElementById("btnProfiles").onclick=()=>this._openProfiles();
    r.getElementById("btnPlots").onclick=()=>this._openPlots();

    // deploy dlg
    r.getElementById("d_cancel").onclick=()=>r.getElementById("dlgDeploy").close();
    r.getElementById("d_ok").onclick=()=>this._deployOk();

    // profiles dlg
    r.getElementById("p_close").onclick=()=>r.getElementById("dlgProfiles").close();
    r.getElementById("p_new").onclick=()=>this._profileClear();
    r.getElementById("p_save").onclick=()=>this._profileSave();
    r.getElementById("p_delete").onclick=()=>this._profileDelete();
    r.getElementById("p_select").onchange=()=>this._profileLoadFromSelect();

    // live validation + enter-to-save (keep as you had)
    ["p_id","p_name","p_cover","p_uncover","p_water","p_notes"].forEach(k=>{
      const el = r.getElementById(k);
      el.addEventListener("input", ()=>this._profileValidate());
      el.addEventListener("keydown", (ev)=>{
        if (ev.key === "Enter" && !r.getElementById("p_save").disabled) {
          ev.preventDefault(); this._profileSave();
        }
      });
    });

    // plots dlg
    r.getElementById("pl_close").onclick=()=>r.getElementById("dlgPlots").close();
    r.getElementById("pl_new").onclick=()=>this._plotNew();
    r.getElementById("pl_delete").onclick=(ev)=>this._plotDelete(ev.currentTarget);
    r.getElementById("pl_save").onclick=(ev)=>this._plotSave(ev.currentTarget);
    r.getElementById("pl_select").onchange=()=>this._plotLoad();

    ["pl_id","pl_label"].forEach(k=>{
      const el = r.getElementById(k);
      el.addEventListener("input", ()=>this._plotValidate());
      el.addEventListener("keydown", (ev)=>{
        if (ev.key === "Enter" && !r.getElementById("pl_save").disabled) {
          ev.preventDefault(); this._plotSave(r.getElementById("pl_save"));
        }
      });
    });
  }

  _meta(){
    const e=this._hass.states["sensor.microgreens_meta"];
    const a=e?e.attributes:{};
    return {plots:a.plots||[], profiles:(a.profiles||[]).map(p=>({notes:"", ...p}))};
  }
  _eid(id){ return `sensor.microgreens_plot_${String(id).toLowerCase()}`; }

  _update(){
    const {plots}=this._meta();
    const g=this._root.getElementById("grid");
    g.innerHTML="";
    plots.forEach(p=>{
      const s=this._hass.states[this._eid(p.id)];
      const st=s? s.state : "idle";
      const a=s? s.attributes : {};
      const div=document.createElement("div");
      div.className="tile";
      div.innerHTML = `
        <div class="hdr">
          <div class="left">
            <div class="title">${p.label}</div>
            <div class="state ${st}">${st}</div>
          </div>
          <div class="muted">${a.plant_name || ""}</div>
        </div>

        <div class="meta-row-right">
          <div class="meta-left">
            <div class="line muted">${a.cover_end ? `Uncover: ${a.cover_end}` : `Uncover: —`}</div>
            <div class="line muted">${a.harvest_date ? `Harvest: ${a.harvest_date}` : `Harvest: —`}</div>
          </div>
          <div class="meta-right">
            <button class="secondary" data-label="Clear" data-act="clear" data-plot="${p.id}" ${st==='idle'?'disabled':''}>
              Clear
            </button>
          </div>
        </div>
      `;
      div.querySelectorAll("button").forEach(b => b.onclick = (ev) => this._tileAction(b.dataset, ev.currentTarget));
      g.appendChild(div);

    });
  }

  // ---- Deploy modal
  _openDeploy(){
    const m=this._meta();
    const idle = m.plots.filter(p=>{
      const s=this._hass.states[this._eid(p.id)];
      return !s || s.state === "idle";
    });
    const sync=(id,arr,v,t)=>{const el=this._root.getElementById(id); el.innerHTML=""; arr.forEach(i=>{const o=document.createElement("option");o.value=i[v];o.textContent=i[t]; el.appendChild(o)});};
    sync("d_plot", idle, "id","label");
    sync("d_profile", m.profiles, "id","name");
    const d=new Date(); d.setMinutes(d.getMinutes()-d.getTimezoneOffset());
    this._root.getElementById("d_start").value=d.toISOString().slice(0,10);
    if (idle.length === 0) { alert("All plots are occupied. Unassign/harvest a plot first."); return; }
    this._root.getElementById("dlgDeploy").showModal();
  }
  async _deployOk(){
    const plot=this._root.getElementById("d_plot").value;
    const profile=this._root.getElementById("d_profile").value;
    const start=this._root.getElementById("d_start").value;
    if(!plot||!profile||!start) return;
    const s=this._hass.states[this._eid(plot)];
    if (s && s.state !== "idle") { alert(`Plot ${plot} is occupied.`); return; }

    const okBtn = this._root.getElementById("d_ok");
    await this._hass.callService("microgreens","deploy",{plot_id:plot,profile_id:profile,start_date:start});
    this._flashOK(okBtn);
    setTimeout(()=>{ this._root.getElementById("dlgDeploy").close(); }, 550);
  }


  // ---- Profiles
  _openProfiles(){
    this._refreshProfilesSelect();           // build from current state
    this._profileLoadFromSelect();           // load the first/selected profile
    this._root.getElementById("dlgProfiles").showModal();
    this._profileValidate();
  }


  _profileClear(){
    ["p_id","p_name","p_cover","p_uncover","p_water","p_notes"].forEach(k=>this._root.getElementById(k).value="");
    this._root.getElementById("p_id").focus();
    this._profileValidate();
  }

  _profileLoadFromSelect(){
    const id=this._root.getElementById("p_select").value;
    const p=(this._meta().profiles||[]).find(x=>x.id===id); 
    if(!p){ this._profileClear(); return; }
    this._root.getElementById("p_id").value=p.id||"";
    this._root.getElementById("p_name").value=p.name||"";
    if (p.cover_days !== undefined) this._root.getElementById("p_cover").value=p.cover_days;
    if (p.uncover_days !== undefined) this._root.getElementById("p_uncover").value=p.uncover_days;
    if (p.water !== undefined) this._root.getElementById("p_water").value=p.water;
    if (p.notes !== undefined) this._root.getElementById("p_notes").value=p.notes;
    this._profileValidate();
  }
  _refreshProfilesSelect(keepId){
    const sel = this._root.getElementById("p_select");
    if (!sel) return;
    const list = (this._meta().profiles || []);
    sel.innerHTML = "";
    for (const p of list) {
      const o = document.createElement("option");
      o.value = p.id;
      o.textContent = `${p.name} (${p.id})`;
      sel.appendChild(o);
    }
    if (keepId && list.some(x => x.id === keepId)) sel.value = keepId;
    else if (sel.options.length) sel.value = sel.options[0].value;
  }


  async _profileSave(){
    const id=this._root.getElementById("p_id").value.trim();
    const name=this._root.getElementById("p_name").value.trim();
    if(!id||!name) return;
    const btn = this._root.getElementById("p_save");
    await this._hass.callService("microgreens","profile_upsert",{
      id, name,
      cover_days:Number(this._root.getElementById("p_cover").value||0),
      uncover_days:Number(this._root.getElementById("p_uncover").value||0),
      watering_frequency_days:Number(this._root.getElementById("p_water").value||1),
      notes:this._root.getElementById("p_notes").value||""
    });
    this._flashOK(btn);
    this._refreshProfilesSelect(id);
    this._profileLoadFromSelect();
    this._profileValidate();
  }


  async _profileDelete(){
    const id=this._root.getElementById("p_select").value;
    if(!id) return;
    if(!confirm(`Delete profile ${id}?`)) return;
    await this._hass.callService("microgreens","profile_delete",{id});
    this._profileClear();
  }
  _profileValidate(){
    const id = this._root.getElementById("p_id");
    const name = this._root.getElementById("p_name");
    const save = this._root.getElementById("p_save");

    const okId = !!id.value.trim();
    const okName = !!name.value.trim();

    id.classList.toggle("invalid", !okId);
    name.classList.toggle("invalid", !okName);
    if (save) save.disabled = !(okId && okName);
  }


  // ---- Plots
  _openPlots(){
    this._refreshPlotsModal();
    this._root.getElementById("dlgPlots").showModal();
    this._plotValidate();
  }

  _getMetaPlotLabel(id){
    const m = this._meta().plots || [];
    const cur = m.find(x => x.id === id);
    return cur ? (cur.label || id) : null;
  }

  _plotLoad(){
    this._setPlotsNew(false);
    const id = this._root.getElementById("pl_select").value;
    const meta = this._meta();
    const cur = (meta.plots||[]).find(x=>x.id===id);
    this._root.getElementById("pl_id").value = cur ? cur.id : "";
    this._root.getElementById("pl_label").value = cur ? (cur.label || id) : "";
    this._plotValidate();
  }

  _plotNew(){
    this._setPlotsNew(true);
    const sel = this._root.getElementById("pl_select");
    if (sel) sel.value = "";
    this._root.getElementById("pl_id").value = "";
    this._root.getElementById("pl_label").value = "";
    this._plotValidate();
    this._root.getElementById("pl_id").focus();
  }

  _plotValidate(){
    const id    = this._root.getElementById("pl_id");
    const label = this._root.getElementById("pl_label");
    const save  = this._root.getElementById("pl_save");
    const ok = !!id.value.trim() && !!label.value.trim();
    id.classList.toggle("invalid", !id.value.trim());
    label.classList.toggle("invalid", !label.value.trim());
    save.disabled = !ok;
  }

  async _plotSave(btn){
    const sel    = this._root.getElementById("pl_select");
    const id     = this._root.getElementById("pl_id").value.trim();
    const label  = this._root.getElementById("pl_label").value.trim();
    if (!id || !label) return;

    const exists = (this._meta().plots||[]).some(x=>x.id===id);
    if (exists) await this._hass.callService("microgreens","plot_rename",{plot_id:id,label});
    else        await this._hass.callService("microgreens","plot_add",{plot_id:id,label});

    this._flashOK(btn);
    this._setPlotsNew(false);              // leave new mode
    this._refreshPlotsModal();
    if (sel) sel.value = id;               // keep selection on saved id
    this._plotValidate();
  }
  async _plotDelete(btn){
    const id = (this._root.getElementById("pl_select").value || this._root.getElementById("pl_id").value || "").trim();
    if (!id) return;
    if (!confirm(`Delete plot ${id}?`)) return;

    await this._hass.callService("microgreens","plot_remove",{plot_id:id});
    this._flashOK(btn);
    this._setPlotsNew(false);              // ensure we exit new mode after delete
    this._refreshPlotsModal();
  }
  // --- Plots "new" mode flag
  _setPlotsNew(on){ this._ui = this._ui || {}; this._ui.plotsNew = !!on; }
  _isPlotsNew(){ return !!(this._ui && this._ui.plotsNew); }

  _isOpen(id) {
    const dlg = this._root.getElementById(id);
    return !!(dlg && dlg.open);
  }
  _isFocused(id){
    const el = this._root.getElementById(id);
    return this._root.activeElement === el;
  }
  // local edit state for the Plots modal label
  _setLabelDirty(on) {
    const sel = this._root.getElementById("pl_select");
    this._edit = this._edit || {};
    this._edit.dirty = !!on;
    this._edit.plotId = sel ? sel.value : null;
  }
  _isLabelDirtyForCurrent() {
    const sel = this._root.getElementById("pl_select");
    return !!(this._edit?.dirty && sel && this._edit.plotId === sel.value);
  }

  _refreshPlotsModal(){
    const sel = this._root.getElementById("pl_select");
    const idIn = this._root.getElementById("pl_id");
    const labelIn = this._root.getElementById("pl_label");
    if (!sel || !idIn || !labelIn) return;

    const meta = this._meta();
    const prev = sel.value;
    const newMode = this._isPlotsNew() || !prev;  // explicit new mode or nothing selected

    // rebuild options
    sel.innerHTML = "";

    // Placeholder when creating a new plot
    if (newMode) {
      const ph = document.createElement("option");
      ph.value = "";
      ph.textContent = "— New plot —";
      sel.appendChild(ph);
    }

    (meta.plots||[]).forEach(p=>{
      const o=document.createElement("option");
      o.value=p.id; o.textContent=`${p.label} (${p.id})`;
      sel.appendChild(o);
    });

    if (newMode) {
      sel.value = "";  // keep placeholder selected
    } else {
      // keep selection if still present, else pick first actual plot
      const exists = (meta.plots||[]).some(x=>x.id===prev);
      const chosen = exists ? prev : (meta.plots?.[0]?.id || "");
      if (chosen) sel.value = chosen;
    }

    const cur = (meta.plots||[]).find(x=>x.id===sel.value);

    // Only overwrite text inputs if not actively editing them
    if (!this._isFocused("pl_id"))    idIn.value    = cur ? cur.id : (newMode ? "" : "");
    if (!this._isFocused("pl_label")) labelIn.value = cur ? (cur.label || cur.id) : (newMode ? "" : "");

    this._plotValidate();
  }

  // ---- Tile actions
  async _tileAction(d, el){
    if (d.act === "clear") {
      if (!confirm(`Clear plot ${d.plot}? This removes its deployment.`)) return;
      await this._hass.callService("microgreens","unassign",{plot_id:d.plot});
      this._flashOK(el);
    }
  }

  _flashOK(btn, hold=800){
    if(!btn) return;
    const orig = btn.getAttribute("data-label") || btn.textContent;
    btn.classList.add("ok-anim");
    btn.disabled = true;
    btn.textContent = "✓";
    setTimeout(()=>{
      btn.classList.remove("ok-anim");
      btn.disabled = false;
      btn.textContent = orig;
    }, hold);
  }

}
if (!customElements.get("microgreens-card")) {
  customElements.define("microgreens-card", MicrogreensCard);
}