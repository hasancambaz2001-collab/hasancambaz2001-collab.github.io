const button = document.getElementById("ping");
const status = document.getElementById("status");

button?.addEventListener("click", () => {
  const now = new Date().toLocaleTimeString();
  status.textContent = `Hello from dvgreenpass.com at ${now}`;
});
