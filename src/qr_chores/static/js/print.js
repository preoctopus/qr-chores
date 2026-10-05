(() => {
  document.addEventListener("DOMContentLoaded", () => {
    const printBtn = document.getElementById("print-btn");
    if (printBtn) {
      printBtn.addEventListener("click", () => {
        window.print();
      });
    }
  });
})();
