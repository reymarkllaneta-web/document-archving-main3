document.addEventListener("click", function (e) {
  var btn = e.target.closest(".password-toggle");
  if (!btn) return;
  var input = btn.closest(".password-field").querySelector("input");
  var showing = btn.classList.toggle("is-visible");
  input.type = showing ? "text" : "password";
  btn.setAttribute("aria-label", showing ? "Hide password" : "Show password");
});
