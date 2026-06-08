const menuButton = document.querySelector(".menu-toggle");
const mainMenu = document.querySelector(".main-nav");

if (menuButton && mainMenu) {
  menuButton.addEventListener("click", () => {
    const isOpen = menuButton.getAttribute("aria-expanded") === "true";
    menuButton.setAttribute("aria-expanded", String(!isOpen));
    mainMenu.classList.toggle("is-open", !isOpen);
  });

  mainMenu.addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      menuButton.setAttribute("aria-expanded", "false");
      mainMenu.classList.remove("is-open");
    }
  });
}

document.querySelectorAll("[data-auto-submit]").forEach((field) => {
  field.addEventListener("change", () => field.form?.requestSubmit());
});

document.querySelectorAll("[data-href]").forEach((element) => {
  element.addEventListener("click", (event) => {
    if (event.target.closest("a, button, input, select")) return;
    window.location.href = element.dataset.href;
  });
});
