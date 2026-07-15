/* Sidebar nav behavior (zensical has no per-section expand / accordion):
   1. Accordion — opening a top-level group closes the others.
   2. "Getting Started" (#__nav_2) starts expanded when no other group is open
      (i.e. the active page isn't inside one). Plain checkbox state only — the
      theme's md-toggle--indeterminate class is deliberately NOT used, since
      zensical's bundle also manages that class and fights external users.
   Re-applies on instant navigation via document$ (replay subject).
   Top-level toggle ids are __nav_<n>; #__nav_2 = 2nd item — update if nav
   order changes. */
(function () {
  var TOP = /^__nav_\d+$/;
  function topToggles() {
    return Array.prototype.filter.call(
      document.querySelectorAll("input.md-nav__toggle"),
      function (el) { return TOP.test(el.id); }
    );
  }
  function apply() {
    var toggles = topToggles();
    toggles.forEach(function (input) {
      if (input.dataset.arvelAccordion) return;
      input.dataset.arvelAccordion = "1";
      input.addEventListener("change", function () {
        if (!input.checked) return;
        topToggles().forEach(function (other) {
          if (other !== input) other.checked = false;
        });
      });
    });
    var gs = document.getElementById("__nav_2");
    if (gs && !toggles.some(function (t) { return t.checked; })) gs.checked = true;
  }
  if (window.document$ && window.document$.subscribe) window.document$.subscribe(apply);
  else document.addEventListener("DOMContentLoaded", apply);
})();
