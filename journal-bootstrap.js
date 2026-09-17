    // Apply saved theme synchronously so the page doesn't flash the wrong
    // palette before journal.js runs. Matches getStoredTheme() / applyTheme()
    // in journal.js.
    (function () {
      try {
        if (localStorage.getItem("journal_hide_pnl") === "true") document.body.classList.add("is-private");
        if (localStorage.getItem("journal_theme") === "light") {
          document.body.classList.add("is-light");
        }
      } catch (_) { /* storage disabled — stay on default dark */ }
    })();
