const pendingForms = new Set();

document.addEventListener("submit", (event) => {
  const form = event.target;
  const message = event.submitter?.dataset.pendingMessage;
  if (pendingForms.has(form)) {
    event.preventDefault();
    return;
  }
  if (!message) return;

  pendingForms.add(form);
  form.querySelector("[data-pending-status]").textContent = message;
});

window.addEventListener("pageshow", () => {
  for (const form of pendingForms) {
    form.querySelector("[data-pending-status]").textContent = "";
  }
  pendingForms.clear();
});
