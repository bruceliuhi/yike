"use strict";

const focusKey = "yike-filter-focus";
const filterForm = document.querySelector("[data-auto-submit]");

if (filterForm) {
  const savedFocus = sessionStorage.getItem(focusKey);
  if (savedFocus) {
    const control = filterForm.elements.namedItem(savedFocus);
    if (control && typeof control.focus === "function") control.focus();
    sessionStorage.removeItem(focusKey);
  }

  filterForm.querySelectorAll("select").forEach((control) => {
    control.addEventListener("change", () => {
      sessionStorage.setItem(focusKey, control.name);
      filterForm.requestSubmit();
    });
  });

  let submitTimer;
  filterForm.querySelectorAll("input:not([type='hidden'])").forEach((control) => {
    control.addEventListener("input", () => {
      window.clearTimeout(submitTimer);
      submitTimer = window.setTimeout(() => {
        sessionStorage.setItem(focusKey, control.name);
        filterForm.requestSubmit();
      }, 450);
    });
  });
}

document.querySelectorAll("[data-selectable-row]").forEach((row) => {
  row.addEventListener("pointerdown", () => row.classList.add("is-selected"));
});

const detail = document.querySelector("[data-detail-reveal]");
if (detail) window.requestAnimationFrame(() => detail.classList.add("is-visible"));

const statusStrip = document.querySelector("[data-status-strip]");
if (statusStrip) {
  window.setTimeout(() => statusStrip.classList.add("is-dismissed"), 4200);
}

document.querySelectorAll("input[type='datetime-local']").forEach((control) => {
  if (control.value) return;
  const localNow = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
  control.value = localNow;
});
