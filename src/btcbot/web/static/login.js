const error = new URLSearchParams(location.search).get("error");
if (error) {
  document.getElementById("error").textContent =
    error === "bloqueado"
      ? "Demasiados intentos. Espera 15 minutos."
      : "Contraseña incorrecta.";
}
