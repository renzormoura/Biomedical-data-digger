/* Utilitarios comuns das propostas: tema (claro/escuro), aparicao ao rolar e contadores. */
(() => {
  const root = document.documentElement;
  try { const saved = localStorage.getItem("nx-proposta-tema"); if (saved) root.dataset.theme = saved; } catch { /* sem armazenamento */ }
  document.querySelectorAll(".toggle").forEach((btn) => btn.addEventListener("click", () => {
    const next = root.dataset.theme === "light" ? "dark" : "light";
    root.dataset.theme = next;
    try { localStorage.setItem("nx-proposta-tema", next); } catch { /* ignora */ }
    document.dispatchEvent(new CustomEvent("nx-theme", { detail: next }));
  }));

  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.NX = {
    reduced,
    /** Chama `fn(el)` na primeira vez que o elemento aparece na tela. */
    onView(selector, fn, threshold = 0.35) {
      const io = new IntersectionObserver((entries) => entries.forEach((e) => {
        if (e.isIntersecting) { io.unobserve(e.target); fn(e.target); }
      }), { threshold });
      document.querySelectorAll(selector).forEach((el) => io.observe(el));
    },
    /** Conta de 0 ate o valor em `data-count` (com `data-suffix` opcional). */
    counter(el, ms = 1400) {
      const end = Number(el.dataset.count), suffix = el.dataset.suffix || "";
      if (reduced) { el.textContent = end + suffix; return; }
      const t0 = performance.now();
      const tick = (t) => {
        const k = Math.min(1, (t - t0) / ms), eased = 1 - Math.pow(1 - k, 3);
        el.textContent = Math.round(end * eased) + suffix;
        if (k < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    },
  };
  // revelacao padrao: elementos com .rv entram subindo e aparecendo
  const style = document.createElement("style");
  style.textContent = ".rv{opacity:0;transform:translateY(26px);transition:opacity .8s cubic-bezier(.2,.7,.2,1),transform .8s cubic-bezier(.2,.7,.2,1);transition-delay:var(--d,0s)}.rv.in{opacity:1;transform:none}";
  document.head.append(style);
  document.addEventListener("DOMContentLoaded", () => NX.onView(".rv", (el) => el.classList.add("in"), 0.15));
})();
