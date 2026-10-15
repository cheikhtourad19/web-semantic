"use strict";

const menuToggle = document.querySelector("[data-toggle-sidebar]");
function closeSidebar() {
  document.body.classList.remove("nav-open");
  menuToggle?.setAttribute("aria-expanded", "false");
}
menuToggle?.addEventListener("click", () => {
  const open = document.body.classList.toggle("nav-open");
  menuToggle.setAttribute("aria-expanded", String(open));
});
document.querySelector("[data-close-sidebar]")?.addEventListener("click", closeSidebar);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeSidebar();
    document.querySelectorAll("details[open]").forEach((menu) => (menu.open = false));
  }
});
document.addEventListener("click", (event) => {
  document.querySelectorAll(".user-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
});
document.querySelectorAll("[data-dismiss-message]").forEach((button) => {
  button.addEventListener("click", () => button.closest(".notification").remove());
});
document.querySelectorAll("[data-auto-submit]").forEach((input) => {
  input.addEventListener("change", () => input.form.requestSubmit());
});
document.querySelector("[data-toggle-password]")?.addEventListener("click", (event) => {
  const button = event.currentTarget;
  const input = button.parentElement.querySelector("input");
  const visible = input.type === "password";
  input.type = visible ? "text" : "password";
  button.setAttribute("aria-pressed", String(visible));
  button.setAttribute("aria-label", visible ? "Masquer le mot de passe" : "Afficher le mot de passe");
});

document.querySelectorAll("[data-choice-container]").forEach((container) => {
  const checkboxes = [...container.querySelectorAll('input[type="checkbox"]')];
  const count = container.querySelector("[data-choice-count]");
  const updateCount = () => {
    const selected = checkboxes.filter((input) => input.checked).length;
    count.textContent = `${selected} sélectionné${selected > 1 ? "s" : ""}`;
    const summary = container.closest("details")?.querySelector("[data-disclosure-count]");
    if (summary) summary.textContent = selected ? count.textContent : (container.closest("details").dataset.required === "true" ? "Au moins un élément" : "Facultatif");
  };
  checkboxes.forEach((input) => input.addEventListener("change", updateCount));
  container.querySelector("[data-clear-choices]")?.addEventListener("click", () => {
    checkboxes.forEach((input) => {
      input.checked = false;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    updateCount();
  });
  container.querySelector("[data-choice-search]")?.addEventListener("input", (event) => {
    const text = event.target.value.toLocaleLowerCase("fr");
    let visible = 0;
    checkboxes.forEach((input) => {
      const option = input.closest("label").parentElement;
      option.hidden = !option.textContent.toLocaleLowerCase("fr").includes(text);
      if (!option.hidden) visible++;
    });
    const empty = container.querySelector(".choice-empty");
    if (empty) empty.hidden = visible > 0;
  });
  updateCount();
});

const entityForm = document.querySelector("[data-entity-form]");
if (entityForm) {
  const title = entityForm.querySelector("[data-title-input]");
  const preview = entityForm.querySelector("[data-title-preview]");
  if (title && preview) {
    const fallback = preview.textContent;
    title.addEventListener("input", () => (preview.textContent = title.value.trim() || fallback));
  }
  const updateSource = () => {
    const source = entityForm.querySelector('input[name="source"]:checked')?.value;
    if (!source) return;
    const file = source === "file";
    entityForm.querySelector('[data-field="url"]').hidden = file;
    entityForm.querySelector('[data-field="file"]').hidden = !file;
    entityForm.querySelector('[name="url"]').disabled = file;
    entityForm.querySelector('[name="file"]').disabled = !file;
    const type = entityForm.querySelector('[name="resource_type"]');
    if (file && type) type.value = "DocumentPDF";
  };
  entityForm.querySelectorAll('input[name="source"]').forEach((radio) => radio.addEventListener("change", updateSource));
  updateSource();
  let changed = false;
  let submitting = false;
  entityForm.addEventListener("change", () => (changed = true));
  entityForm.addEventListener("input", (event) => {
    if (!event.target.matches("[data-choice-search]")) changed = true;
  });
  entityForm.addEventListener("submit", () => {
    submitting = true;
    entityForm.classList.add("is-saving");
    const button = entityForm.querySelector("[data-save-button]");
    if (button) {
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (changed && !submitting) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  document.querySelector("[data-form-error]")?.focus();
}
