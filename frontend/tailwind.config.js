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
          900: "#0a0d12",
          800: "#0f1319",
          700: "#161b24",
          600: "#1d2330",
          500: "#2a3142",
          400: "#4a536a",
          300: "#7a8599",
          200: "#a3acbf",
          100: "#dde2eb",
        },
        accent: {
          cyan: "#3de3ff",
          amber: "#ffb547",
          red: "#ff4d6d",
          green: "#32d296",
          violet: "#9f6bff",
        },
      },
    },
  },
  plugins: [],
};
