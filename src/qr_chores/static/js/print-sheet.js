(() => {
  const btn = document.getElementById("print-sheet-btn");
  if (!btn) return;
  btn.addEventListener("click", () => window.print());
})();
