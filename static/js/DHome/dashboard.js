// Per-twin dashboard. All fetches are scoped to window.DT_ID, set by the
// template. Permission (can_control) is per-device and comes from /state.
const DT = window.DT_ID;
const api = (p) => `/api/twins/${DT}${p}`;

const fmt = (v) =>
    (v === null || v === undefined || Number.isNaN(v)) ? "--" : Number(v).toFixed(1);
const accentFor = (b) =>
    b === "cool" ? "var(--cool)" : b === "heat" ? "var(--warm)" : "var(--muted)";
const verb = {cool: "Cooling", heat: "Heating", off: "Idle"};

let dragging = false;
let canControl = true;
let acControllable = true;
let winControllable = true;

async function refresh() {
    try {
        const r = await fetch(api("/state"));
        if (r.status === 401) {
            location.href = "/login";
            return;
        }
        if (r.status === 403) {
            location.href = "/";
            return;
        }
        const s = await r.json();

        document.getElementById("indoor").textContent = fmt(s.indoor_temp);
        document.getElementById("outdoor").textContent = fmt(s.outdoor_temp);
        document.getElementById("people").textContent = s.people_inside ?? "--";

        const accent = accentFor(s.ac_blowing);
        document.documentElement.style.setProperty("--accent", accent);

        const fc = document.getElementById("fireChip");
        if (s.fire) {
            fc.className = "chip fire";
            fc.textContent = "FIRE DETECTED";
        } else {
            fc.className = "chip clear";
            fc.textContent = "Clear";
        }

        const fire = !!s.fire;
        canControl = !!s.can_control;
        const windowsOpen = s.control.windows === "open";
        const locked = !canControl || fire;
        acControllable = !locked && !windowsOpen;
        winControllable = !locked;

        const st = document.getElementById("status");
        const txt = document.getElementById("statusTxt");
        if (s.online) {
            st.classList.add("live");
            txt.textContent = "Device online";
        } else {
            st.classList.remove("live");
            txt.textContent = "Device offline";
        }

        const acModes = document.getElementById("modes_ac");
        const thrBox = document.getElementById("thrBox");
        const acNote = document.getElementById("noControlNote");
        acModes.classList.toggle("disabled", !acControllable);

        if (acNote) {
            if (fire) {
                acNote.textContent = "Fire detected — AC locked off until it clears.";
                acNote.style.display = "block";
            } else if (!canControl) {
                acNote.textContent = "Your account can view but not change AC settings.";
                acNote.style.display = "block";
            } else if (windowsOpen) {
                acNote.textContent = "The AC is off while the windows are open. Close the windows to control it.";
                acNote.style.display = "block";
            } else {
                acNote.style.display = "none";
            }
        }
        acModes.querySelectorAll("button").forEach((b) =>
            b.classList.toggle("active", b.dataset.mode === s.control.mode));

        thrBox.classList.toggle("disabled", s.control.mode !== "auto" || !acControllable);
        if (!dragging) {
            document.getElementById("thr").value = s.control.threshold;
            document.getElementById("thrVal").textContent = Number(s.control.threshold).toFixed(1);
        }

        const winModes = document.getElementById("modes_win");
        const winNote = document.getElementById("noControlNote_win");
        winModes.classList.toggle("disabled", !winControllable);
        if (winNote) {
            if (fire) {
                winNote.textContent = "Fire detected — windows locked closed until it clears.";
                winNote.style.display = "block";
            } else if (!canControl) {
                winNote.textContent = "Your account can view but not change Windows settings.";
                winNote.style.display = "block";
            } else {
                winNote.style.display = "none";
            }
        }
        winModes.querySelectorAll("button").forEach((b) =>
            b.classList.toggle("active", b.dataset.window === s.control.windows));
    } catch (e) {
    }
}

async function sendControl(payload) {
    const r = await fetch(api("/control"), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
    });
    if (r.ok) refresh();
}

document.querySelectorAll("#modes_ac button").forEach((b) =>
    b.addEventListener("click", () => {
        if (acControllable) sendControl({mode: b.dataset.mode});
    }));
document.querySelectorAll("#modes_win button").forEach((b) =>
    b.addEventListener("click", () => {
        if (winControllable) sendControl({windows: b.dataset.window});
    }));

const thr = document.getElementById("thr");
thr.addEventListener("input", () => {
    dragging = true;
    document.getElementById("thrVal").textContent = Number(thr.value).toFixed(1);
});
thr.addEventListener("change", () => {
    dragging = false;
    if (acControllable) sendControl({threshold: parseFloat(thr.value)});
});

refresh();
setInterval(refresh, 3000);
