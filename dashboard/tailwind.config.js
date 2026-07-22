/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Todos los tokens se resuelven vía CSS variables definidas en index.css
        // bajo .dark / .light. El formato "R G B" + <alpha-value> deja funcionar
        // los modificadores de opacidad de Tailwind (p. ej. bg-accent/10).
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-2": "rgb(var(--surface-2) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        "border-strong": "rgb(var(--border-strong) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        faint: "rgb(var(--faint) / <alpha-value>)",
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          hover: "rgb(var(--accent-hover) / <alpha-value>)",
        },
        high: "rgb(var(--high) / <alpha-value>)",
        medium: "rgb(var(--medium) / <alpha-value>)",
        low: "rgb(var(--low) / <alpha-value>)",
        success: "rgb(var(--success) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.18)",
        glow: "0 4px 20px rgba(var(--accent) / 0.28)",
        lift: "0 8px 30px rgba(0,0,0,0.30)",
      },
      borderRadius: {
        xl2: "14px",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease both",
        "fade-in": "fade-in 0.25s ease both",
      },
    },
  },
  plugins: [],
};
