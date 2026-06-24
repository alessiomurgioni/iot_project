// Adds a show/hide eye-icon button to any input inside a .field-wrap.
// Usage: wrap the input in <div class="field-wrap">...</div> and call
// initPasswordToggles() once the DOM is ready (this file does that on load).

const EYE_OPEN =
  '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" ' +
  'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z"/>' +
  '<circle cx="12" cy="12" r="3"/></svg>';

const EYE_CLOSED =
  '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" ' +
  'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="M3 3l18 18"/>' +
  '<path d="M10.6 10.6a3 3 0 0 0 4.24 4.24"/>' +
  '<path d="M9.4 5.5A11.5 11.5 0 0 1 12 5c7 0 11 7 11 7a14 14 0 0 1-3.1 3.6"/>' +
  '<path d="M6.1 6.1A14 14 0 0 0 1 12s4 7 11 7a10.6 10.6 0 0 0 3.4-.56"/></svg>';

function initPasswordToggles() {
  document.querySelectorAll(".field-wrap").forEach((wrap) => {
    const input = wrap.querySelector("input");
    if (!input || wrap.querySelector(".toggle-visibility")) return; // already wired

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "toggle-visibility";
    btn.setAttribute("aria-label", "Show value");
    btn.innerHTML = EYE_OPEN;

    btn.addEventListener("click", () => {
      const hidden = input.type === "password";
      input.type = hidden ? "text" : "password";
      btn.innerHTML = hidden ? EYE_CLOSED : EYE_OPEN;
      btn.setAttribute("aria-label", hidden ? "Hide value" : "Show value");
    });

    wrap.appendChild(btn);
  });
}

document.addEventListener("DOMContentLoaded", initPasswordToggles);
