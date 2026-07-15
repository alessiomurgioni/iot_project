async function firewatch_dash() {
    if (!window.DT_ID) return;
    try {
        const r = await fetch(`/api/twins/${window.DT_ID}/state`);
        if (!r.ok) return;
        const s = await r.json();
        document.body.classList.toggle("fire", !!s.fire);
    } catch (e) {
    }
}

if (window.DT_ID) {
    firewatch_dash();
    setInterval(firewatch_dash, 3000);
}