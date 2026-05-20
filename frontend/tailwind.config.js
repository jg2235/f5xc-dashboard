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
          900: "#070b10",
          800: "#0d1520",
          700: "#111d2e",
          600: "#1a2940",
          500: "#253650",
          400: "#3a5068",
          300: "#5a7a96",
          200: "#8aaec8",
          100: "#e2f0ff",
        },
        accent: {
          cyan: "#00d4ff",
          amber: "#ffaa00",
          red: "#ff2d55",
          green: "#00ff9f",
          violet: "#bf5fff",
        },
      },
    },
  },
  plugins: [],
};
