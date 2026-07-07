// Per-twin management page. Lists this device's members and lets the owner
// revoke control or remove them. All endpoints are scoped to window.DT_ID.
const DT = window.DT_ID;
const body = document.getElementById("usersBody");
const errBox = document.getElementById("ownerErr");

function showError(msg) { errBox.textContent = msg; errBox.style.display = "block"; }
function clearError() { errBox.style.display = "none"; }

async function loadMembers() {
    clearError();
    try {
        const r = await fetch(`/twins/${DT}/api/members`);
        if (r.status === 401) { location.href = "/login"; return; }
        if (r.status === 403) { location.href = "/"; return; }
        const list = await r.json();

        if (!list.length) {
            body.innerHTML = '<tr><td colspan="4" class="muted">No accounts.</td></tr>';
            return;
        }
        body.innerHTML = "";
        for (const u of list) {
            const tr = document.createElement("tr");

            const name = document.createElement("td");
            name.textContent = u.username;

            const role = document.createElement("td");
            const rb = document.createElement("span");
            rb.className = "badge " + (u.role === "owner" ? "owner" : "member");
            rb.textContent = u.role;
            role.appendChild(rb);

            const ctrl = document.createElement("td");
            const label = document.createElement("label");
            label.className = "toggle";
            const toggle = document.createElement("input");
            toggle.type = "checkbox";
            toggle.checked = !!u.can_control;
            toggle.addEventListener("change", () => setControl(u.username, toggle.checked));
            const track = document.createElement("span");
            track.className = "toggle-track";
            label.append(toggle, track);
            ctrl.appendChild(label);

            const action = document.createElement("td");
            const btn = document.createElement("button");
            btn.className = "btn-del";
            btn.textContent = "Remove";
            if (u.username === window.CURRENT_USER) {
                btn.disabled = true;
                btn.title = "You can't remove yourself from this device";
            } else {
                btn.addEventListener("click", () => removeMember(u.username));
            }
            action.appendChild(btn);

            tr.append(name, role, ctrl, action);
            body.appendChild(tr);
        }
    } catch (e) {
        showError("Could not load accounts. Is the server reachable?");
    }
}

async function setControl(username, canControl) {
    clearError();
    try {
        const r = await fetch(`/twins/${DT}/api/members/permission`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({username, can_control: canControl}),
        });
        const data = await r.json();
        if (!r.ok) { showError(data.error || "Could not update permission."); loadMembers(); }
    } catch (e) { showError("Network error while updating permission."); loadMembers(); }
}

async function removeMember(username) {
    if (!confirm(`Remove "${username}" from this device?`)) return;
    clearError();
    try {
        const r = await fetch(`/twins/${DT}/api/members/remove`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({username}),
        });
        const data = await r.json();
        if (!r.ok) { showError(data.error || "Could not remove account."); return; }
        loadMembers();
    } catch (e) { showError("Network error while removing the account."); }
}

async function deviceStatus() {
    try {
        const r = await fetch(`/api/twins/${DT}/state`);
        if (r.status === 401) { location.href = "/login"; return; }
        const s = await r.json();
        const st = document.getElementById("status");
        const txt = document.getElementById("statusTxt");
        if (s.online) { st.classList.add("live"); txt.textContent = "Device online"; }
        else { st.classList.remove("live"); txt.textContent = "Device offline"; }
    } catch (e) {}
}

async function firewatch_dash() {
    if (!window.DT_ID) return;
    try {
        const r = await fetch(`/api/twins/${window.DT_ID}/state`);
        if (!r.ok) return;
        const s = await r.json();
        document.body.classList.toggle("fire", !!s.fire);
    } catch (e) {}
}
if (window.DT_ID) {
    firewatch_dash();
    setInterval(firewatch_dash, 3000);
}


deviceStatus();
loadMembers();
setInterval(deviceStatus, 3000);
