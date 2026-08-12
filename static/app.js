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

const encodeForm = (values) => new URLSearchParams(values).toString();

document.querySelectorAll("[data-activity-form]").forEach((form) => {
  const sessionInput = form.elements.namedItem("activity_session_id");
  const status = form.querySelector("[data-activity-status]");
  let sessionId = "";
  let paused = false;
  let idleTimer;
  let submitting = false;

  const post = async (path, values) => {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: encodeForm(values),
    });
    if (!response.ok) throw new Error(`activity request failed: ${response.status}`);
    return response.json();
  };

  const start = async () => {
    if (sessionId) return;
    const result = await post("/activity/start", {
      run_id: form.dataset.runId,
      signal_id: form.dataset.signalId,
      activity_kind: form.dataset.activityForm,
    });
    sessionId = result.activity_session_id;
    paused = result.state === "PAUSED";
    sessionInput.value = sessionId;
    if (paused) await event("RESUME");
    if (status) status.textContent = "活动计时中；隐藏窗口或 60 秒无操作会暂停。";
  };

  const event = async (eventKind) => {
    if (!sessionId) return;
    await post(`/activity/${encodeURIComponent(sessionId)}/events`, {
      event_kind: eventKind,
    });
    paused = eventKind.startsWith("PAUSE");
  };

  const armIdle = () => {
    window.clearTimeout(idleTimer);
    idleTimer = window.setTimeout(() => {
      if (!paused && !submitting) event("PAUSE_IDLE").catch(() => {});
    }, 60000);
  };

  form.addEventListener("focusin", () => start().then(armIdle).catch(() => {}), { once: true });
  ["input", "pointerdown", "keydown"].forEach((name) => {
    form.addEventListener(name, () => {
      if (paused) event("RESUME").catch(() => {});
      armIdle();
    });
  });
  document.addEventListener("visibilitychange", () => {
    if (!sessionId || submitting) return;
    if (document.hidden && !paused) event("PAUSE_HIDDEN").catch(() => {});
    if (!document.hidden && paused) event("RESUME").then(armIdle).catch(() => {});
  });
  window.addEventListener("pagehide", () => {
    if (!sessionId || submitting) return;
    const payload = encodeForm({ event_kind: "CANCEL" });
    navigator.sendBeacon(
      `/activity/${encodeURIComponent(sessionId)}/events`,
      new Blob([payload], { type: "application/x-www-form-urlencoded" }),
    );
    sessionId = "";
  });
  form.addEventListener("submit", async (browserEvent) => {
    if (submitting) return;
    browserEvent.preventDefault();
    try {
      await start();
      if (paused) await event("RESUME");
      await event("COMPLETE");
      submitting = true;
      form.requestSubmit();
    } catch (error) {
      if (status) status.textContent = "活动事实未完成，请重试后再保存。";
    }
  });
});
