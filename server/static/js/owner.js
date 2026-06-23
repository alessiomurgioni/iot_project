// Owner management page: list accounts, toggle their control permission,
// and remove accounts. All calls require the owner key already unlocked
// for this session (enforced server-side); a 403 here means it expired.

const body = document.getElementById("usersBody");
const errBox = document.getElementById("ownerErr");

function showError(msg) {
  errBox.textContent = msg;
  errBox.style.display = "block";
}

function clearError() {
  errBox.style.display = "none";
}

async function loadAccounts() {
  clearError();
  try {
    const r = await fetch("/owner/api/accounts");
    if (r.status === 401) { location.href = "/login"; return; }
    if (r.status === 403) { location.href = "/owner/unlock"; return; }
    const list = await r.json();

    if (!list.length) {
      body.innerHTML = '<tr><td colspan="3" class="muted">No accounts.</td></tr>';
      return;
    }

    body.innerHTML = "";
    for (const u of list) {
      const tr = document.createElement("tr");

      const name = document.createElement("td");
      name.textContent = u.username;

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
        btn.title = "You can't remove the account you're logged in with";
      } else {
        btn.addEventListener("click", () => removeAccount(u.username));
      }
      action.appendChild(btn);

      tr.append(name, ctrl, action);
      body.appendChild(tr);
    }
  } catch (e) {
    showError("Could not load accounts. Is the server reachable?");
  }
}

async function setControl(username, canControl) {
  clearError();
  try {
    const r = await fetch("/owner/api/accounts/permission", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, can_control: canControl }),
    });
    const data = await r.json();
    if (!r.ok) { showError(data.error || "Could not update permission."); loadAccounts(); }
  } catch (e) {
    showError("Network error while updating permission.");
    loadAccounts();
  }
}

async function removeAccount(username) {
  if (!confirm(`Remove account "${username}"? This cannot be undone.`)) return;
  clearError();
  try {
    const r = await fetch("/owner/api/accounts/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    const data = await r.json();
    if (!r.ok) { showError(data.error || "Could not remove account."); return; }
    loadAccounts();
  } catch (e) {
    showError("Network error while removing the account.");
  }
}

loadAccounts();
