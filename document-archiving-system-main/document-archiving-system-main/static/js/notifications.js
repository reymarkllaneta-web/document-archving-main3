(function () {
  var bell = document.getElementById("notif-bell");
  var dropdown = document.getElementById("notif-dropdown");
  var items = document.getElementById("notif-items");
  var badge = document.getElementById("notif-badge");
  var markAllBtn = document.getElementById("notif-mark-all");
  var markAllForm = document.getElementById("notif-mark-all-form");
  if (!bell || !dropdown || !window.NOTIF_POLL_URL) return;

  var lastCount = parseInt(badge.dataset.count || "0", 10);
  var open = false;

  function setOpen(next) {
    open = next;
    dropdown.classList.toggle("open", open);
    bell.setAttribute("aria-expanded", open ? "true" : "false");
  }

  bell.addEventListener("click", function (e) {
    e.stopPropagation();
    setOpen(!open);
  });

  document.addEventListener("click", function (e) {
    if (open && !dropdown.contains(e.target) && e.target !== bell) setOpen(false);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && open) setOpen(false);
  });

  if (markAllBtn && markAllForm) {
    markAllBtn.addEventListener("click", function () {
      markAllForm.submit();
    });
  }

  function updateBadge(count) {
    badge.textContent = count > 0 ? count : "";
    badge.dataset.count = String(count);
    bell.classList.toggle("has-unread", count > 0);
    if (count > lastCount) {
      badge.classList.remove("pulse");
      void badge.offsetWidth; // restart the animation
      badge.classList.add("pulse");
      bell.classList.remove("has-unread");
      void bell.offsetWidth;
      bell.classList.add("has-unread");
    }
    lastCount = count;
  }

  function poll() {
    fetch(window.NOTIF_POLL_URL, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (res) {
        var count = parseInt(res.headers.get("X-Unread-Count") || "0", 10);
        return res.text().then(function (html) {
          items.innerHTML = html;
          updateBadge(count);
        });
      })
      .catch(function () { /* silent: notifications are best-effort */ });
  }

  setInterval(poll, 20000);
})();
