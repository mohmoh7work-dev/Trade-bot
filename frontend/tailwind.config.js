/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fff5f5",
          100: "#fde8e8",
          200: "#f9cfd1",
          300: "#f3a5aa",
          400: "#ea6f78",
          500: "#e0414d",
          600: "#d62839",
          700: "#b31d2d",
          800: "#8f1a27",
          900: "#5c1019",
        },
        ink: { DEFAULT: "#2a1215", soft: "#6b4a4e", faint: "#9c8083" },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica Neue",
          "Arial", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(92,16,25,0.04), 0 8px 24px -12px rgba(214,40,57,0.18)",
        sheet: "0 -8px 40px -12px rgba(92,16,25,0.35)",
      },
    },
  },
  plugins: [],
};
