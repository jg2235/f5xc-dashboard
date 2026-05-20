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
          900: "#f2f2f2",
          800: "#ffffff",
          700: "#e5e5e5",
          600: "#cccccc",
          500: "#999999",
          400: "#666666",
          300: "#888888",
          200: "#333333",
          100: "#111111",
        },
        accent: {
          cyan: "#0077a8",
          amber: "#b45309",
          red: "#b91c1c",
          green: "#047857",
          violet: "#6d28d9",
        },
      },
    },
  },
  plugins: [],
};
