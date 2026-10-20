(function () {
  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var ok = document.execCommand("copy");
    area.remove();
    return ok ? Promise.resolve() : Promise.reject(new Error("copy failed"));
  }

  function toast(trigger, text, failed) {
    var tip = document.createElement("div");
    tip.className = "clipboard-tooltip" + (failed ? " is-error" : "");
    tip.setAttribute("role", "status");
    tip.textContent = text;
    document.body.appendChild(tip);
    var rect = trigger.getBoundingClientRect();
    tip.style.left = rect.left + window.scrollX + rect.width / 2 - tip.offsetWidth / 2 + "px";
    tip.style.top = rect.top + window.scrollY - tip.offsetHeight - 10 + "px";
    requestAnimationFrame(function () {
      tip.classList.add("show");
    });
    setTimeout(function () {
      tip.classList.remove("show");
      setTimeout(function () {
        tip.remove();
      }, 300);
    }, 1500);
  }

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest(".copy-to-clipboard");
    if (!trigger) return;
    copy(trigger.getAttribute("data-clipboard-text") || "").then(
      function () {
        toast(trigger, "Скопировано!", false);
      },
      function () {
        toast(trigger, "Ошибка копирования!", true);
      },
    );
  });
})();
