const addDeviceButton = document.getElementById("show-add-device");
const addDeviceSection = document.getElementById("add-device-section");
const cancelAddDeviceButton = document.getElementById("cancel-add-device");

addDeviceButton.addEventListener("click", () => {
    addDeviceSection.hidden = false;
    addDeviceButton.hidden = true;
    document.getElementById("did").focus();
});

cancelAddDeviceButton.addEventListener("click", () => {
    addDeviceSection.querySelector(".add-device-error")?.remove();
    addDeviceSection.querySelector("form")?.reset();

    addDeviceSection.hidden = true;
    addDeviceButton.hidden = false;
});
document.addEventListener("click", async (event) => {
    const button = event.target.closest(".device-remove");
    if (!button) return;

    event.preventDefault();
    event.stopPropagation();

    const dtId = button.dataset.dtId;
    const deviceName = button.dataset.deviceName;

    if (!confirm(`Remove "${deviceName}" from your devices?`)) {
        return;
    }

    button.disabled = true;

    try {
        const r = await fetch(
            `/twins/${encodeURIComponent(dtId)}/api/members/leave`,
            {
                method: "POST",
                headers: {"Content-Type": "application/json"}
            }
        );

        const data = await r.json();

        if (!r.ok) {
            throw new Error(data.error || "Could not remove device.");
        }

        button.closest(".device-card-wrap").remove();

    } catch (e) {
        alert(e.message || "Network error while removing the device.");
        button.disabled = false;
    }
});


async function refreshHomeFireStates() {
    const cards = document.querySelectorAll(".device-card[data-dt-id]");

    await Promise.all(
        [...cards].map(async (card) => {
            const dtId = card.dataset.dtId;

            try {
                const response = await fetch(
                    `/api/twins/${encodeURIComponent(dtId)}/state?_=${Date.now()}`,
                    {cache: "no-store"}
                );

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const state = await response.json();

                card.classList.toggle(
                    "fire",
                    state.fire
                );
            } catch (error) {
                console.error(`Could not refresh ${dtId}:`, error);
            }
        })
    );
}

refreshHomeFireStates();