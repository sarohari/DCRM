document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-line-formset]").forEach((root) => {
    const container = root.querySelector("[data-line-forms]");
    const totalForms = root.querySelector('input[name$="-TOTAL_FORMS"]');
    const template = root.querySelector("[data-empty-line]");
    const subtotal = root.querySelector("[data-line-subtotal]");

    const toCents = (value) => {
      const match = String(value || "").trim().match(/^(\d+)(?:\.(\d{0,2}))?$/);
      if (!match) return 0n;
      return BigInt(match[1]) * 100n + BigInt((match[2] || "").padEnd(2, "0"));
    };

    const updateSubtotal = () => {
      let cents = 0n;
      container.querySelectorAll(".sale-line-form").forEach((line) => {
        const deleted = line.querySelector('input[type="checkbox"][name$="-DELETE"]');
        if (deleted && deleted.checked) return;
        const amount = line.querySelector('input[name$="-amount"]');
        if (amount) cents += toCents(amount.value);
      });
      subtotal.value = `${cents / 100n}.${String(cents % 100n).padStart(2, "0")}`;
    };

    root.addEventListener("click", (event) => {
      if (event.target.matches("[data-add-line]")) {
        const index = Number(totalForms.value);
        const html = template.innerHTML.replaceAll("__prefix__", String(index));
        container.insertAdjacentHTML("beforeend", html);
        totalForms.value = String(index + 1);
        updateSubtotal();
      }
      if (event.target.matches("[data-remove-line]")) {
        const line = event.target.closest(".sale-line-form");
        const deleted = line.querySelector('input[type="checkbox"][name$="-DELETE"]');
        if (deleted) {
          deleted.checked = true;
          line.hidden = true;
        }
        updateSubtotal();
      }
    });

    root.addEventListener("input", (event) => {
      if (event.target.matches('input[name$="-amount"]')) updateSubtotal();
    });
    root.addEventListener("change", (event) => {
      if (event.target.matches('input[name$="-DELETE"]')) updateSubtotal();
    });
    updateSubtotal();
  });
});
