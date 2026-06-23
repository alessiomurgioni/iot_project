// Dashboard: polls /api/state and sends AC control changes.

const fmt = (v) =>
  (v === null || v === undefined || Number.isNaN(v)) ? "--" : Number(v).toFixed(1);
const accentFor = (b) =>
  b === "cool" ? "var(--cool)" : b === "heat" ? "var(--warm)" : "var(--muted)";
const verb = { cool: "Cooling", heat: "Heating", off: "Idle" };

let dragging = false; // don't overwrite the slider while the owner drags it

async function refresh() {
  try {
    const r = await fetch("/api/state");
    if (r.status === 401) { location.href = "/login"; return; }
    const s = await r.json();

    document.getElementById("indoor").textContent  = fmt(s.indoor_temp);
    document.getElementById("outdoor").textContent = fmt(s.outdoor_temp);
    document.getElementById("people").textContent  = s.people_inside ?? "--";

    // AC accent + hero tint
    const accent = accentFor(s.ac_blowing);
    document.documentElement.style.setProperty("--accent", accent);
    document.getElementById("modeLine").textContent =
      (verb[s.ac_blowing] || "Idle") + " · mode: " + s.control.mode;

    // fire
    const fc = document.getElementById("fireChip");
    if (s.fire) { fc.className = "chip fire";  fc.textContent = "FIRE — alarm active"; }
    else        { fc.className = "chip clear"; fc.textContent = "Clear"; }

    // online status
    const st = document.getElementById("status");
    const txt = document.getElementById("statusTxt");
    if (s.online) { st.classList.add("live");    txt.textContent = "Device online"; }
    else          { st.classList.remove("live"); txt.textContent = "Device offline"; }

    // controls
    const modesEl = document.getElementById("modes");
    const thrBox = document.getElementById("thrBox");
    const note = document.getElementById("noControlNote");

    if (!s.can_control) {
      modesEl.classList.add("disabled");
      thrBox.classList.add("disabled");
      if (note) note.style.display = "block";
    } else {
      modesEl.classList.remove("disabled");
      if (note) note.style.display = "none";
    }
    canControl = !!s.can_control;

    modesEl.querySelectorAll("button").forEach((b) =>
      b.classList.toggle("active", b.dataset.mode === s.control.mode));
    thrBox.classList.toggle("disabled", s.control.mode !== "auto" || !s.can_control);
    if (!dragging) {
      document.getElementById("thr").value = s.control.threshold;
      document.getElementById("thrVal").textContent =
        Number(s.control.threshold).toFixed(1);
    }
  } catch (e) {
    /* transient network error; next tick retries */
  }
}

async function sendControl(payload) {
  const r = await fetch("/api/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (r.ok) refresh();
}

let canControl = true; // updated by refresh(); guards clicks client-side only

document.querySelectorAll("#modes button").forEach((b) =>
  b.addEventListener("click", () => { if (canControl) sendControl({ mode: b.dataset.mode }); }));

const thr = document.getElementById("thr");
thr.addEventListener("input", () => {
  dragging = true;
  document.getElementById("thrVal").textContent = Number(thr.value).toFixed(1);
});
thr.addEventListener("change", () => {
  dragging = false;
  if (canControl) sendControl({ threshold: parseFloat(thr.value) });
});

refresh();
setInterval(refresh, 3000);
