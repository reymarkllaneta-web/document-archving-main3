(function () {
  function current() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function paint(theme) {
    document.querySelectorAll(".theme-toggle").forEach(function (btn) {
      btn.classList.toggle("is-dark", theme === "dark");
      btn.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
    });
  }

  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
    paint(theme);
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".theme-toggle");
    if (!btn) return;
    apply(current() === "dark" ? "light" : "dark");
  });

  paint(current());
})();
