/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        carbon: {
          900: "#f0f4f8",
          800: "#ffffff",
          700: "#e8edf2",
          600: "#d1d9e0",
          500: "#9aa5b4",
          400: "#627d98",
          300: "#829ab1",
          200: "#486581",
          100: "#102a43",
        },
        accent: {
          cyan: "#0891b2",
          amber: "#d97706",
          red: "#dc2626",
          green: "#059669",
          violet: "#7c3aed",
        },
      },
    },
  },
  plugins: [],
};
