(function () {
  "use strict";

  const MODEL_CLASS = "model-staffattendance";

  const onReady = (callback) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }
    callback();
  };

  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) =>
    Array.from(root.querySelectorAll(selector));

  const toText = (node) =>
    String(node?.textContent ?? "")
      .replace(/\s+/g, " ")
      .trim();

  const createElement = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text != null) element.textContent = text;
    return element;
  };

  const markRowsByState = (rows) => {
    rows.forEach((row) => {
      const text = toText(row).toLowerCase();
      const isAnomaly = text.includes("нет входа") || text.includes("нет выхода");
      const isAbsent =
        text.includes("отсутств") ||
        text.includes("больнич") ||
        text.includes("отпуск");

      if (isAnomaly) {
        row.classList.add("sa-row-anomaly");
        row.title = "Есть незавершённые или некорректные отметки входа/выхода";
      }
      if (isAbsent) {
        row.classList.add("sa-row-absent");
      }
    });
  };

  const renderStatsPanel = () => {
    const table = qs("#result_list");
    if (!table || qs(".sa-quick-panel")) return;
    const rows = qsa("tbody tr", table).filter((row) => !row.classList.contains("empty-row"));
    if (!rows.length) return;

    let anomalies = 0;
    let absences = 0;
    let remote = 0;

    rows.forEach((row) => {
      const text = toText(row).toLowerCase();
      if (text.includes("нет входа") || text.includes("нет выхода")) anomalies += 1;
      if (text.includes("отсутств") || text.includes("больнич") || text.includes("отпуск")) {
        absences += 1;
      }
      if (text.includes("удален") || text.includes("remote")) remote += 1;
    });

    const panel = createElement("section", "sa-quick-panel");
    panel.setAttribute("aria-label", "Краткая статистика текущей страницы");
    panel.append(
      createElement("span", "sa-kpi-badge", `Строк: ${rows.length}`),
      createElement("span", "sa-kpi-badge sa-kpi-badge--warn", `Аномалии: ${anomalies}`),
      createElement("span", "sa-kpi-badge sa-kpi-badge--danger", `Отсутствия: ${absences}`),
      createElement("span", "sa-kpi-badge sa-kpi-badge--info", `Удалённо: ${remote}`),
    );

    const target = qs("#grp-changelist") || qs(".grp-changelist-results") || table.parentElement;
    if (!target || !target.parentNode) return;
    target.parentNode.insertBefore(panel, target);
  };

  const initBulkActionsUX = () => {
    const form = qs("#changelist-form");
    if (!form) return;

    const actionSelect = qs('select[name="action"]', form);
    if (!actionSelect) return;

    const submitButtons = qsa(
      'button[name="index"], input[type="submit"][name="index"]',
      form,
    );
    const checkboxes = qsa("input.action-select", form);
    const toggleAll = qs("#action-toggle", form);
    const actionsContainer = actionSelect.closest(".actions") || actionSelect.parentElement;
    if (!actionsContainer) return;

    const selectedCounter = createElement("span", "sa-selected-counter");
    actionsContainer.appendChild(selectedCounter);

    const getSelectedCount = () => checkboxes.filter((item) => item.checked).length;

    const updateUI = () => {
      const selected = getSelectedCount();
      selectedCounter.textContent = `Выбрано: ${selected}`;
      const hasAction = String(actionSelect.value || "").length > 0;
      submitButtons.forEach((button) => {
        button.disabled = hasAction && selected === 0;
      });
    };

    updateUI();
    checkboxes.forEach((checkbox) => checkbox.addEventListener("change", updateUI));
    if (toggleAll) {
      toggleAll.addEventListener("change", () => {
        window.requestAnimationFrame(updateUI);
      });
    }
    actionSelect.addEventListener("change", updateUI);

    form.addEventListener("submit", (event) => {
      const actionValue = String(actionSelect.value || "");
      if (!actionValue) return;
      const selected = getSelectedCount();
      if (selected === 0) {
        event.preventDefault();
        window.alert("Сначала выберите хотя бы одну запись.");
      }
    });
  };

  const initKeyboardShortcuts = () => {
    const searchInput = qs("#searchbar");
    const resetLink = qs(".reset-filters-btn");
    document.addEventListener("keydown", (event) => {
      const target = event.target;
      const isTypingTarget =
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);

      if (event.key === "/" && !isTypingTarget && searchInput) {
        event.preventDefault();
        searchInput.focus();
        searchInput.select?.();
        return;
      }

      if (event.altKey && (event.key === "r" || event.key === "R") && resetLink) {
        event.preventDefault();
        resetLink.click();
      }
    });
  };

  onReady(() => {
    if (!document.body.classList.contains(MODEL_CLASS)) return;
    const rows = qsa("#result_list tbody tr").filter(
      (row) => !row.classList.contains("empty-row"),
    );
    markRowsByState(rows);
    renderStatsPanel();
    initBulkActionsUX();
    initKeyboardShortcuts();
  });
})();
