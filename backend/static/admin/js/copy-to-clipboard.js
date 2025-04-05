document.addEventListener("DOMContentLoaded", function () {
  var clipboardElements = document.querySelectorAll(".copy-to-clipboard");

  if (clipboardElements.length > 0) {
    var clipboard = new ClipboardJS(".copy-to-clipboard", {
      text: function (trigger) {
        return trigger.getAttribute("data-clipboard-text");
      },
    });

    clipboard.on("success", function (e) {
      var tooltip = document.createElement("div");
      tooltip.className = "clipboard-tooltip";
      tooltip.textContent = "Скопировано!";
      document.body.appendChild(tooltip);

      var rect = e.trigger.getBoundingClientRect();
      tooltip.style.position = "absolute";
      tooltip.style.left =
        rect.left +
        window.scrollX +
        rect.width / 2 -
        tooltip.offsetWidth / 2 +
        "px";
      tooltip.style.top =
        rect.top + window.scrollY - tooltip.offsetHeight - 10 + "px";
      tooltip.style.backgroundColor = "#4CAF50";
      tooltip.style.color = "white";
      tooltip.style.padding = "5px 10px";
      tooltip.style.borderRadius = "3px";
      tooltip.style.fontSize = "14px";
      tooltip.style.zIndex = "9999";
      tooltip.style.opacity = "0";
      tooltip.style.transition = "opacity 0.3s";

      setTimeout(function () {
        tooltip.style.opacity = "1";
      }, 10);

      setTimeout(function () {
        tooltip.style.opacity = "0";
        setTimeout(function () {
          document.body.removeChild(tooltip);
        }, 300);
      }, 1500);

      var originalBg = e.trigger.style.backgroundColor;
      var originalColor = e.trigger.style.color;

      e.trigger.style.backgroundColor = "#4CAF50";
      e.trigger.style.color = "white";
      e.trigger.style.transition = "all 0.3s";

      setTimeout(function () {
        e.trigger.style.backgroundColor = originalBg;
        e.trigger.style.color = originalColor;
      }, 500);

      e.clearSelection();
    });

    clipboard.on("error", function (e) {
      console.error("Action:", e.action);
      console.error("Trigger:", e.trigger);

      var tooltip = document.createElement("div");
      tooltip.className = "clipboard-tooltip";
      tooltip.textContent = "Ошибка копирования!";
      document.body.appendChild(tooltip);

      var rect = e.trigger.getBoundingClientRect();
      tooltip.style.position = "absolute";
      tooltip.style.left =
        rect.left +
        window.scrollX +
        rect.width / 2 -
        tooltip.offsetWidth / 2 +
        "px";
      tooltip.style.top =
        rect.top + window.scrollY - tooltip.offsetHeight - 10 + "px";
      tooltip.style.backgroundColor = "#F44336";
      tooltip.style.color = "white";
      tooltip.style.padding = "5px 10px";
      tooltip.style.borderRadius = "3px";
      tooltip.style.fontSize = "14px";
      tooltip.style.zIndex = "9999";
      tooltip.style.opacity = "0";
      tooltip.style.transition = "opacity 0.3s";

      setTimeout(function () {
        tooltip.style.opacity = "1";
      }, 10);

      setTimeout(function () {
        tooltip.style.opacity = "0";
        setTimeout(function () {
          document.body.removeChild(tooltip);
        }, 300);
      }, 1500);
    });

    clipboardElements.forEach(function (el) {
      el.style.cursor = "pointer";
      el.title = "Нажмите, чтобы скопировать";
      el.style.padding = "4px 8px";
      el.style.borderRadius = "3px";
      el.style.transition = "background-color 0.2s";

      el.addEventListener("mouseover", function () {
        this.style.backgroundColor = "#f0f0f0";
      });

      el.addEventListener("mouseout", function () {
        this.style.backgroundColor = "";
      });
    });
  }
});
