(function () {
  "use strict";

  const MODEL_CLASS = "model-lessonattendance";
  const STATUS_QUERY_KEY = "photo_effective_status";
  const ACTION_RESCAN = "rescan_selected_photos";
  const ACTION_WITH_CONFIRM = new Set([ACTION_RESCAN]);

  const FILTERS = [
    { label: "Все", value: "" },
    { label: "Подозрительные", value: "suspicious" },
    { label: "На проверку", value: "review" },
    { label: "Нормальные", value: "clean" },
  ];

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

  const parseVerdictBucket = (rowText) => {
    const text = rowText.toLowerCase();
    if (text.includes("подозр")) return "suspicious";
    if (text.includes("на проверку") || text.includes("ожидает") || text.includes("ошибка")) {
      return "review";
    }
    if (text.includes("нормаль")) return "clean";
    return "other";
  };

  const buildFilterHref = (value) => {
    const url = new URL(window.location.href);
    if (value) {
      url.searchParams.set(STATUS_QUERY_KEY, value);
    } else {
      url.searchParams.delete(STATUS_QUERY_KEY);
    }
    url.searchParams.delete("p");
    const query = url.searchParams.toString();
    return `${url.pathname}${query ? `?${query}` : ""}`;
  };

  const renderStatusQuickPanel = () => {
    const table = qs("#result_list");
    if (!table || qs(".la-quick-panel")) return;

    const rows = qsa("tbody tr", table).filter((row) => !row.classList.contains("empty-row"));
    if (!rows.length) return;

    const counters = {
      total: rows.length,
      suspicious: 0,
      review: 0,
      clean: 0,
      other: 0,
    };
    rows.forEach((row) => {
      counters[parseVerdictBucket(toText(row))] += 1;
    });

    const currentFilter = new URL(window.location.href).searchParams.get(
      STATUS_QUERY_KEY,
    );

    const panel = createElement("section", "la-quick-panel");
    panel.setAttribute("aria-label", "Бысткая статистика фото-вердиктов");

    const statsWrap = createElement("div", "la-quick-panel__stats");
    statsWrap.append(
      createElement("span", "la-kpi-badge", `Всего: ${counters.total}`),
      createElement(
        "span",
        "la-kpi-badge la-kpi-badge--suspicious",
        `Подозрительные: ${counters.suspicious}`,
      ),
      createElement(
        "span",
        "la-kpi-badge la-kpi-badge--review",
        `На проверку: ${counters.review}`,
      ),
      createElement(
        "span",
        "la-kpi-badge la-kpi-badge--clean",
        `Нормальные: ${counters.clean}`,
      ),
    );

    const filtersWrap = createElement("div", "la-quick-panel__filters");
    FILTERS.forEach((item) => {
      const link = createElement("a", "la-filter-chip", item.label);
      link.href = buildFilterHref(item.value);
      if ((currentFilter ?? "") === item.value) {
        link.classList.add("is-active");
      }
      filtersWrap.appendChild(link);
    });

    panel.append(statsWrap, filtersWrap);

    const target =
      qs("#grp-changelist") ||
      qs(".grp-changelist-results") ||
      table.parentElement;
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
    const selectedCounter = createElement("span", "la-selected-counter");
    actionsContainer.appendChild(selectedCounter);

    const getSelectedCount = () => checkboxes.filter((item) => item.checked).length;

    const updateUI = () => {
      const selected = getSelectedCount();
      selectedCounter.textContent = `Выбрано: ${selected}`;
      actionsContainer.classList.toggle("la-actions-empty", selected === 0);
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
      const selected = getSelectedCount();
      if (!actionValue) return;
      if (selected === 0) {
        event.preventDefault();
        window.alert("Сначала выберите хотя бы одну запись.");
        return;
      }
      if (ACTION_WITH_CONFIRM.has(actionValue)) {
        const ok = window.confirm(
          `Вы уверены? Будет запущен перескан для ${selected} выбранных записей.`,
        );
        if (!ok) {
          event.preventDefault();
        }
      }
    });
  };

  const initManualVerdictHelpers = () => {
    const verdictSelect = qs("#id_photo_manual_verdict");
    if (!verdictSelect) return;

    const rowComment =
      qs(".form-row.field-photo_manual_comment") ||
      qs("#id_photo_manual_comment")?.closest(".form-row");
    const rowManualBy =
      qs(".form-row.field-photo_manual_by") ||
      qs("#id_photo_manual_by")?.closest(".form-row");
    const rowManualAt =
      qs(".form-row.field-photo_manual_at") ||
      qs("#id_photo_manual_at")?.closest(".form-row");

    const controlsWrap = createElement("div", "la-manual-quick-actions");
    const helper = createElement("div", "la-manual-help");
    const holder = verdictSelect.parentElement || verdictSelect.closest(".field-box");
    if (holder) {
      holder.append(controlsWrap, helper);
    }

    const presetButtons = [
      {
        value: "clean",
        label: "Нормальное",
        className: "la-action-btn la-action-btn--clean",
      },
      {
        value: "suspicious",
        label: "Подозрительное",
        className: "la-action-btn la-action-btn--suspicious",
      },
      {
        value: "none",
        label: "Сброс",
        className: "la-action-btn la-action-btn--reset",
      },
    ];

    const applyVerdict = (value) => {
      verdictSelect.value = value;
      verdictSelect.dispatchEvent(new Event("change", { bubbles: true }));
    };

    presetButtons.forEach((item) => {
      const button = createElement("button", item.className, item.label);
      button.type = "button";
      button.addEventListener("click", () => applyVerdict(item.value));
      controlsWrap.appendChild(button);
    });

    const updateState = () => {
      const value = String(verdictSelect.value || "none");
      if (rowComment) {
        rowComment.style.display = value === "none" ? "none" : "";
      }
      [rowManualBy, rowManualAt].forEach((row) => {
        if (!row) return;
        row.classList.toggle("la-row-muted", value === "none");
      });

      if (value === "suspicious") {
        helper.textContent = "Ручной вердикт: фото помечено как подозрительное.";
        helper.className = "la-manual-help is-suspicious";
      } else if (value === "clean") {
        helper.textContent = "Ручной вердикт: фото подтверждено как нормальное.";
        helper.className = "la-manual-help is-clean";
      } else {
        helper.textContent = "Ручной вердикт не выставлен. Действует автоматическая проверка.";
        helper.className = "la-manual-help";
      }
    };

    verdictSelect.addEventListener("change", updateState);
    updateState();
  };

  onReady(() => {
    if (!document.body.classList.contains(MODEL_CLASS)) return;
    renderStatusQuickPanel();
    initBulkActionsUX();
    initManualVerdictHelpers();
  });
})();
