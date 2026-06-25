async function fireWatch() {
    try {
        const r = await fetch("/api/state");
        if (!r.ok) return;
        const s = await r.json();
        document.body.classList.toggle("fire", !!s.fire);
    } catch (e) {
    }
}

fireWatch();
setInterval(fireWatch, 3000);