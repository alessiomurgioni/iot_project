const fmt = (v) =>
    (v === null || v === undefined || Number.isNaN(v)) ? "--" : Number(v).toFixed(1);
const accentFor = (b) =>
    b === "cool" ? "var(--cool)" : b === "heat" ? "var(--warm)" : "var(--muted)";
const verb = {cool: "Cooling", heat: "Heating", off: "Idle"};

let dragging = false;        // don't overwrite the slider while the owner drags it
let canControl = true;       // permission: may change AC / windows at all
let acControllable = true;   // permission AND windows closed AND no fire
let winControllable = true;  // permission AND no fire


async function refresh() {
    try {
        const r = await fetch("/api/state");
        if (r.status === 401) {
            location.href = "/login";
            return;
        }
        const s = await r.json();

        document.getElementById("indoor").textContent = fmt(s.indoor_temp);
        document.getElementById("outdoor").textContent = fmt(s.outdoor_temp);
        document.getElementById("people").textContent = s.people_inside ?? "--";

        // AC accent + hero tint
        const accent = accentFor(s.ac_blowing);
        document.documentElement.style.setProperty("--accent", accent);
        document.getElementById("modeLine").textContent =
            (verb[s.ac_blowing] || "Idle") + " · mode: " + s.control.mode;

        // fire chip
        const fc = document.getElementById("fireChip");
        if (s.fire) {
            fc.className = "chip fire";
            fc.textContent = "FIRE DETECTED";
        } else {
            fc.className = "chip clear";
            fc.textContent = "Clear";
        }

        // ── Controllability flags ────────────────────────────────────
        const fire = !!s.fire;
        canControl = !!s.can_control;
        const windowsOpen = s.control.window === "open";

        const locked = !canControl || fire;   // either reason greys things out
        acControllable = !locked && !windowsOpen;
        winControllable = !locked;

        // online status
        const st = document.getElementById("status");
        const txt = document.getElementById("statusTxt");
        if (s.online) {
            st.classList.add("live");
            txt.textContent = "Device online";
        } else {
            st.classList.remove("live");
            txt.textContent = "Device offline";
        }

        // ── AC controls ──────────────────────────────────────────────
        const acModes = document.getElementById("modes_ac");
        const thrBox = document.getElementById("thrBox");
        const acNote = document.getElementById("noControlNote");

        acModes.classList.toggle("disabled", !acControllable);

        // Note text depends on WHY the AC is locked (fire takes priority).
        if (acNote) {
            if (fire) {
                acNote.textContent = "Fire detected — AC locked off until it clears.";
                acNote.style.display = "block";
            } else if (!canControl) {
                acNote.textContent = "Your account can view but not change AC settings.";
                acNote.style.display = "block";
            } else if (windowsOpen) {
                acNote.textContent =
                    "The AC is off while the windows are open. Close the windows to control it.";
                acNote.style.display = "block";
            } else {
                acNote.style.display = "none";
            }
        }

        acModes.querySelectorAll("button").forEach((b) =>
            b.classList.toggle("active", b.dataset.mode === s.control.mode));

        // Threshold is part of the AC section: locked when AC is locked, or when the mode isn't "auto".
        thrBox.classList.toggle("disabled", s.control.mode !== "auto" || !acControllable);
        if (!dragging) {
            document.getElementById("thr").value = s.control.threshold;
            document.getElementById("thrVal").textContent =
                Number(s.control.threshold).toFixed(1);
        }

        // ── Window controls ──────────────────────────────────────────
        const winModes = document.getElementById("modes_win");
        const winNote = document.getElementById("noControlNote_win");

        // Windows are gated by permission and by fire (never by AC state).
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
            b.classList.toggle("active", b.dataset.window === s.control.window));
    } catch (e) {
    }
}

async function sendControl(payload) {
    const r = await fetch("/api/control", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
    });
    if (r.ok) refresh();
}

// AC mode buttons
document.querySelectorAll("#modes_ac button").forEach((b) =>
    b.addEventListener("click", () => {
        if (acControllable) sendControl({mode: b.dataset.mode});
    }));

// Window buttons
document.querySelectorAll("#modes_win button").forEach((b) =>
    b.addEventListener("click", () => {
        if (winControllable) sendControl({window: b.dataset.window});
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