/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        ink: "#0f1630",
        canvas: "#f6f5f1",
        brand: {
          50: "#eef3ff",
          100: "#dce6fd",
          200: "#bccdfa",
          300: "#8eaaf5",
          400: "#5b7fec",
          500: "#3a5be0",
          600: "#2a44c9",
          700: "#2336a3",
          800: "#1f2f82",
          900: "#1d2a66",
          950: "#121a3d",
        },
        gold: {
          50: "#fdf8ec",
          100: "#faefcf",
          200: "#f4dc9b",
          300: "#edc463",
          400: "#e6ad3a",
          500: "#d99423",
          600: "#bf731b",
          700: "#9f5419",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(16, 24, 40, 0.04), 0 6px 20px rgba(16, 24, 40, 0.06)",
      },
    },
  },
  plugins: [],
};
