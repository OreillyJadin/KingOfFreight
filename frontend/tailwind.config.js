/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        canvas: "#f5f7fb",
      },
      boxShadow: {
        card: "0 2px 10px rgba(15, 23, 42, 0.05)",
      },
    },
  },
  plugins: [],
};
