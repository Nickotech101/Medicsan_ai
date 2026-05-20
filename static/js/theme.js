(function () {
  const saved = localStorage.getItem("mediscan-theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);

  function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("mediscan-theme", next);

    const btn = document.getElementById("themeBtn");
    if (btn) btn.textContent = next === "dark" ? "🌙 Dark" : "☀ Light";
  }

  function setActiveNav() {
    const path = window.location.pathname.replace(/\/+$/, "") || "/";
    document.querySelectorAll(".nav-link").forEach((link) => {
      const href = link.getAttribute("href");
      if (href === path || (path === "/" && href === "/")) {
        link.classList.add("active");
      } else {
        link.classList.remove("active");
      }
    });
  }

  function bindNavToggle() {
    const toggle = document.getElementById("navToggle");
    const links = document.querySelector(".navbar-links");
    if (!toggle || !links) return;

    toggle.addEventListener("click", () => {
      const open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open);
    });

    links.querySelectorAll(".nav-link").forEach((link) => {
      link.addEventListener("click", () => {
        if (links.classList.contains("open")) {
          links.classList.remove("open");
          toggle.setAttribute("aria-expanded", "false");
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("themeBtn");
    if (btn) {
      const current = document.documentElement.getAttribute("data-theme") || "dark";
      btn.textContent = current === "dark" ? "🌙 Dark" : "☀ Light";
      btn.addEventListener("click", toggleTheme);
    }
    setActiveNav();
    bindNavToggle();
  });
})();
