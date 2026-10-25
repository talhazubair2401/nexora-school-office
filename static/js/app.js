/* Small helpers; no build step. */
(function () {
  "use strict";
  const C = { indigo: "#241f5c", green: "#2f7d3a", red: "#c0312b", amber: "#c98a0b", muted: "#5f6478", rule: "#eceef4" };
  window.IFS = C;
  if (window.Chart) {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = C.muted;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.plugins.tooltip.backgroundColor = C.indigo;
    Chart.defaults.plugins.legend.labels.boxWidth = 12;
    Chart.defaults.scale.grid.color = C.rule;
    Chart.defaults.scale.border.display = false;
  }
  window.readData = (id) => { const el = document.getElementById(id); return el ? JSON.parse(el.textContent) : null; };

  // Auto-submit filter dropdowns
  document.querySelectorAll("form[data-autosubmit] select, form[data-autosubmit] input[type=month]").forEach((el) =>
    el.addEventListener("change", () => el.form.requestSubmit()));

  // New admission: fill the class's usual fee and next roll number
  const feeData = window.readData("class-fees");
  const rollData = window.readData("class-rolls");
  const cls = document.getElementById("id_classroom");
  if (cls && feeData) {
    cls.addEventListener("change", () => {
      const fee = document.getElementById("id_monthly_fee");
      const roll = document.getElementById("id_roll_no");
      if (fee && feeData[cls.value] !== undefined) fee.value = feeData[cls.value];
      if (roll && rollData && rollData[cls.value] !== undefined) roll.value = rollData[cls.value];
      updateNet();
    });
  }
  function updateNet() {
    const fee = document.getElementById("id_monthly_fee"), disc = document.getElementById("id_discount");
    const out = document.getElementById("net-fee");
    if (!fee || !disc || !out) return;
    const n = Math.max((parseFloat(fee.value) || 0) - (parseFloat(disc.value) || 0), 0);
    out.textContent = "Rs. " + n.toLocaleString("en-PK");
  }
  ["id_monthly_fee", "id_discount"].forEach((id) => { const el = document.getElementById(id); if (el) el.addEventListener("input", updateNet); });
  updateNet();

  // Class colour swatches
  document.querySelectorAll(".swatch").forEach((b) => b.addEventListener("click", () => {
    const input = document.getElementById("id_colour");
    input.value = b.dataset.colour;
    document.querySelectorAll(".swatch").forEach((x) => x.classList.toggle("selected", x === b));
  }));

  // Marks grid: absent box disables the input; Enter moves down the column
  document.querySelectorAll("[data-absent-for]").forEach((box) => {
    const input = document.getElementById(box.dataset.absentFor);
    const sync = () => { if (input) { input.disabled = box.checked; if (box.checked) input.value = ""; } };
    box.addEventListener("change", sync); sync();
  });
  const grid = document.querySelector(".marks-grid");
  if (grid) {
    grid.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || !e.target.classList.contains("mark-in")) return;
      e.preventDefault();
      const col = e.target.dataset.col, row = parseInt(e.target.dataset.row, 10);
      let next = null;
      for (let r = row + 1; ; r++) {
        const cand = grid.querySelector(`.mark-in[data-col="${col}"][data-row="${r}"]`);
        if (!cand) break;
        if (!cand.disabled) { next = cand; break; }
      }
      if (next) { next.focus(); next.select(); }
    });
    grid.addEventListener("input", (e) => {
      if (!e.target.classList.contains("mark-in")) return;
      const max = parseFloat(e.target.dataset.full), v = parseFloat(e.target.value);
      e.target.classList.toggle("is-invalid", e.target.value !== "" && !/^[aA]/.test(e.target.value) && (isNaN(v) || v < 0 || v > max));
    });
  }

  // Test subjects editor
  const subjList = document.getElementById("subject-rows");
  if (subjList) {
    const tpl = document.getElementById("subject-row-tpl");
    const addRow = (name = "", full = "") => {
      const node = tpl.content.firstElementChild.cloneNode(true);
      node.querySelector("[name=subj_name]").value = name;
      node.querySelector("[name=subj_full]").value = full;
      subjList.appendChild(node);
    };
    document.getElementById("add-subject").addEventListener("click", () => addRow("", document.getElementById("default-full").value || 100));
    subjList.addEventListener("click", (e) => { if (e.target.closest(".remove-subject")) e.target.closest(".subject-row").remove(); });
    const classSubjects = window.readData("class-subjects");
    const clsSel = document.getElementById("id_classroom");
    const fill = () => {
      if (!classSubjects || !clsSel) return;
      const names = classSubjects[clsSel.value] || [];
      const full = document.getElementById("default-full").value || 100;
      subjList.innerHTML = "";
      names.forEach((n) => addRow(n, full));
      document.getElementById("no-subjects").classList.toggle("d-none", names.length > 0 || !clsSel.value);
    };
    if (clsSel && classSubjects && !subjList.children.length) { clsSel.addEventListener("change", fill); fill(); }
    else if (clsSel && classSubjects) clsSel.addEventListener("change", fill);
    const applyAll = document.getElementById("apply-full");
    if (applyAll) applyAll.addEventListener("click", () => {
      const full = document.getElementById("default-full").value;
      subjList.querySelectorAll("[name=subj_full]").forEach((i) => (i.value = full));
    });
  }


  // ---------------------------------------------------------------------------
  // Back button: remembers the pages you visited in this window and returns
  // to the one you came from. Form pages (edit, receive, delete …) are skipped
  // so "Back" never takes you into a form you already saved.
  // ---------------------------------------------------------------------------
  const NAV_KEY = "ifsNav";
  const FORM_PAGE = /\/(new|edit|receive|remove|delete|leave|restore|password|marks|first-time|login)\/?$/;
  const here = () => location.pathname + location.search;
  const readNav = () => { try { return JSON.parse(sessionStorage.getItem(NAV_KEY)) || []; } catch (e) { return []; } };
  const saveNav = (nav) => { try { sessionStorage.setItem(NAV_KEY, JSON.stringify(nav.slice(-60))); } catch (e) {} };
  window.IFSNav = {
    replaceCurrent(url) {           // used by the live search, which changes the address without a reload
      const nav = readNav();
      if (nav.length && nav[nav.length - 1].split("?")[0] === location.pathname) nav[nav.length - 1] = url;
      saveNav(nav);
    },
  };
  (function trackPage() {
    let nav = readNav();
    let cameBack = false;
    try { cameBack = sessionStorage.getItem("ifsNavBack") === "1"; sessionStorage.removeItem("ifsNavBack"); } catch (e) {}
    if (FORM_PAGE.test(location.pathname) || window.self !== window.top || /\/preview\//.test(location.pathname)) return;
    if (cameBack) return;
    if (nav[nav.length - 1] !== here()) nav.push(here());
    saveNav(nav);
  })();
  function goBack(fallback) {
    let nav = readNav();
    if (!FORM_PAGE.test(location.pathname) && nav[nav.length - 1] === here()) nav.pop();
    while (nav.length && nav[nav.length - 1] === here()) nav.pop();
    const target = nav.length ? nav[nav.length - 1] : (fallback || "/");
    saveNav(nav);
    try { sessionStorage.setItem("ifsNavBack", "1"); } catch (e) {}
    location.href = target;
  }
  window.IFSBack = goBack;
  document.querySelectorAll("[data-back]").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    goBack(a.getAttribute("href"));
  }));
  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (e.altKey && e.key === "ArrowLeft" && document.querySelector("[data-back]")) { e.preventDefault(); goBack(document.querySelector("[data-back]").getAttribute("href")); }
    if (typing || document.activeElement.isContentEditable || e.altKey || e.ctrlKey || e.metaKey) return;
    // Backspace (when not typing in a box) goes back one screen, like Alt + Left arrow
    if (e.key === "Backspace" && document.querySelector("[data-back]") && !document.querySelector(".modal.show")) {
      e.preventDefault();
      goBack(document.querySelector("[data-back]").getAttribute("href"));
      return;
    }
    // Student page: ← → move to the previous / next student of the class
    if (e.key === "ArrowLeft" && document.getElementById("prev-student")) location.href = document.getElementById("prev-student").href;
    if (e.key === "ArrowRight" && document.getElementById("next-student")) location.href = document.getElementById("next-student").href;
  });

  // ---------------------------------------------------------------------------
  // "Are you sure?" box for buttons marked data-confirm
  // ---------------------------------------------------------------------------
  const modalEl = document.getElementById("confirm-modal");
  let pendingForm = null;
  document.addEventListener("submit", (e) => {
    const form = e.target;
    const msg = form.dataset.confirm || (e.submitter && e.submitter.dataset.confirm);
    if (!msg || form.dataset.confirmed === "1" || !modalEl || !window.bootstrap) return;
    e.preventDefault();
    pendingForm = form;
    pendingForm._submitter = e.submitter;
    document.getElementById("confirm-text").innerHTML = msg;
    const yes = document.getElementById("confirm-yes");
    yes.textContent = form.dataset.confirmYes || "Yes";
    yes.className = "btn " + (form.dataset.confirmDanger ? "btn-danger" : "btn-primary");
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
    setTimeout(() => yes.focus(), 250);
  }, true);
  if (modalEl) document.getElementById("confirm-yes").addEventListener("click", () => {
    if (!pendingForm) return;
    pendingForm.dataset.confirmed = "1";
    bootstrap.Modal.getOrCreateInstance(modalEl).hide();
    pendingForm.requestSubmit(pendingForm._submitter || undefined);
  });

  // ---------------------------------------------------------------------------
  // Students page: results appear while typing
  // ---------------------------------------------------------------------------
  const liveInput = document.querySelector("[data-live-search]");
  if (liveInput) {
    const form = liveInput.form;
    let timer = null, last = "", ctrl = null;
    const run = () => {
      const params = new URLSearchParams(new FormData(form));
      params.delete("page");
      const qs = params.toString();
      if (qs === last) return;
      last = qs;
      if (ctrl) ctrl.abort();
      ctrl = new AbortController();
      fetch(location.pathname + "?" + qs + "&partial=1", { signal: ctrl.signal, headers: { "X-Requested-With": "fetch" } })
        .then((r) => r.text()).then((html) => {
          const box = document.getElementById("student-results");
          box.outerHTML = html;
          const total = document.getElementById("student-results").dataset.total;
          const label = document.getElementById("total-label");
          if (label) label.textContent = total + " found";
          const url = location.pathname + "?" + qs;
          history.replaceState(null, "", url);
          window.IFSNav.replaceCurrent(url);
          const exp = document.getElementById("export-link");
          if (exp) exp.href = exp.href.split("?")[0] + "?" + qs;
        }).catch(() => {});
    };
    liveInput.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 220); });
    form.addEventListener("submit", (e) => { e.preventDefault(); clearTimeout(timer); last = ""; run(); });
    // the dropdowns already submit the form (data-autosubmit) — that now runs the live search
    const end = liveInput.value.length; liveInput.setSelectionRange(end, end);
  }

  // ---------------------------------------------------------------------------
  // Search bar at the top: suggestions while typing
  // ---------------------------------------------------------------------------
  const topQ = document.getElementById("top-q");
  const box = document.getElementById("suggest-box");
  if (topQ && box) {
    let timer = null, ctrl = null, active = -1;
    const esc = (t) => String(t || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const links = () => Array.from(box.querySelectorAll("a.sg-item"));
    const highlight = (i) => { const l = links(); l.forEach((a, n) => a.classList.toggle("active", n === i)); active = i; if (l[i]) l[i].scrollIntoView({ block: "nearest" }); };
    const hide = () => { box.hidden = true; active = -1; };
    const show = (data) => {
      if (!data.q) { hide(); return; }
      let html = "";
      if (!data.groups.length) html = `<div class="sg-empty">No student found for “${esc(data.q)}”.</div>`;
      data.groups.forEach((g) => {
        html += `<div class="sg-title">${esc(g.title)}</div>`;
        g.items.forEach((s) => {
          html += `<a class="sg-item" href="${esc(s.url)}" role="option"><span class="class-dot" style="background:${esc(s.colour)}"></span>
            <span class="sg-main"><b>${esc(s.name)}</b>${s.father ? ` <span class="text-muted">· father ${esc(s.father)}</span>` : ""}
            <small class="d-block text-muted">${esc(s.cls)} · ${esc(s.adm)}${s.phone ? " · " + esc(s.phone) : ""}${s.status ? " · " + esc(s.status) : ""}</small></span></a>`;
        });
        if (g.more) html += `<div class="sg-more">+ ${g.more} more — press Enter to see all</div>`;
      });
      box.innerHTML = html;
      box.hidden = false;
      active = -1;
    };
    topQ.addEventListener("input", () => {
      clearTimeout(timer);
      const q = topQ.value.trim();
      if (!q) { hide(); return; }
      timer = setTimeout(() => {
        if (ctrl) ctrl.abort();
        ctrl = new AbortController();
        fetch(topQ.dataset.suggest + "?q=" + encodeURIComponent(q), { signal: ctrl.signal }).then((r) => r.json()).then(show).catch(() => {});
      }, 180);
    });
    topQ.addEventListener("keydown", (e) => {
      const l = links();
      if (e.key === "ArrowDown" && l.length) { e.preventDefault(); highlight(Math.min(active + 1, l.length - 1)); }
      else if (e.key === "ArrowUp" && l.length) { e.preventDefault(); highlight(Math.max(active - 1, 0)); }
      else if (e.key === "Enter" && active >= 0 && l[active]) { e.preventDefault(); location.href = l[active].href; }
      else if (e.key === "Escape") hide();
    });
    document.addEventListener("click", (e) => { if (!e.target.closest(".topsearch")) hide(); });
  }

  // Attendance: live counts, and "Mark everyone present"
  const attForm = document.getElementById("att-form");
  if (attForm) {
    const recount = () => {
      const c = { P: 0, A: 0, L: 0 };
      attForm.querySelectorAll("input.btn-check:checked").forEach((i) => { c[i.value] = (c[i.value] || 0) + 1; });
      document.querySelectorAll("[data-count]").forEach((el) => { el.textContent = c[el.dataset.count] || 0; });
    };
    attForm.addEventListener("change", recount);
    const all = attForm.querySelector("[data-all-present]");
    if (all) all.addEventListener("click", () => {
      attForm.querySelectorAll('input.btn-check[value="P"]').forEach((i) => { i.checked = true; });
      attForm.dispatchEvent(new Event("input", { bubbles: true }));
      recount();
    });
  }

  // Daily collection: compare the cash counted with what should be in the drawer
  const counted = document.getElementById("cash-counted");
  if (counted) {
    const due = Number(document.querySelector("[data-cash-due]").dataset.cashDue || 0);
    const out = document.getElementById("cash-result");
    const fmt = (n) => "Rs. " + Math.abs(n).toLocaleString("en-US");
    counted.addEventListener("input", () => {
      const raw = counted.value.replace(/[^0-9]/g, "");
      if (!raw) { out.hidden = true; return; }
      const diff = Number(raw) - due;
      out.hidden = false;
      out.className = "cash-result mt-2 " + (diff === 0 ? "ok" : diff < 0 ? "short" : "extra");
      out.textContent = diff === 0 ? "✓ Matches. All cash is accounted for."
        : diff < 0 ? fmt(diff) + " short. Check today's receipts."
        : fmt(diff) + " extra. A payment may not have been entered.";
    });
  }

  // Water ripple: a soft wave spreads from the exact point you press
  const RIPPLE = ".btn, .vbtn, .att-btn, .board, a.figure, .sidebar .nav-link, .dropdown-item, .page-link, .vswitch button";
  const calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.addEventListener("pointerdown", (e) => {
    if (calm || e.button > 0) return;
    const el = e.target.closest(RIPPLE);
    if (!el || el.disabled || el.classList.contains("disabled")) return;
    if (!el.classList.contains("rpl-host")) {
      if (getComputedStyle(el).position === "static") el.style.position = "relative";
      el.classList.add("rpl-host");
    }
    const r = el.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const size = 2 * Math.hypot(Math.max(x, r.width - x), Math.max(y, r.height - y));
    ["rpl", "rpl-ring"].forEach((cls) => {
      const w = document.createElement("span");
      w.className = cls;
      w.setAttribute("aria-hidden", "true");
      w.style.width = w.style.height = size + "px";
      w.style.left = (x - size / 2) + "px";
      w.style.top = (y - size / 2) + "px";
      el.appendChild(w);
      w.addEventListener("animationend", () => w.remove());
      setTimeout(() => w.remove(), 1500);
    });
  }, { passive: true });

  // Warn before leaving a form with unsaved changes
  document.querySelectorAll("form[data-warn]").forEach((form) => {
    let dirty = false;
    form.addEventListener("input", () => (dirty = true));
    form.addEventListener("submit", () => (dirty = false));
    window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
  });
})();
