/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-2": "rgb(var(--surface-2) / <alpha-value>)",
        "surface-3": "rgb(var(--surface-3) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        "line-strong": "rgb(var(--line-strong) / <alpha-value>)",
        fg: "rgb(var(--fg) / <alpha-value>)",
        "fg-2": "rgb(var(--fg-2) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        subtle: "rgb(var(--subtle) / <alpha-value>)",
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          hover: "rgb(var(--accent-hover) / <alpha-value>)",
          ink: "rgb(var(--accent-ink) / <alpha-value>)",
        },
        "on-accent": "rgb(var(--on-accent) / <alpha-value>)",
        hero: "rgb(var(--hero) / <alpha-value>)",
        "hero-fg": "rgb(var(--hero-fg) / <alpha-value>)",
        scrim: "rgb(var(--scrim) / <alpha-value>)",
        st: {
          booked: "rgb(var(--st-booked) / <alpha-value>)",
          picked: "rgb(var(--st-picked) / <alpha-value>)",
          transit: "rgb(var(--st-transit) / <alpha-value>)",
          delayed: "rgb(var(--st-delayed) / <alpha-value>)",
          delivered: "rgb(var(--st-delivered) / <alpha-value>)",
          "booked-ink": "rgb(var(--st-booked-ink) / <alpha-value>)",
          "picked-ink": "rgb(var(--st-picked-ink) / <alpha-value>)",
          "transit-ink": "rgb(var(--st-transit-ink) / <alpha-value>)",
          "delayed-ink": "rgb(var(--st-delayed-ink) / <alpha-value>)",
          "delivered-ink": "rgb(var(--st-delivered-ink) / <alpha-value>)",
        },
        warn: {
          DEFAULT: "rgb(var(--warn) / <alpha-value>)",
          ink: "rgb(var(--warn-ink) / <alpha-value>)",
        },
        "on-warn": "rgb(var(--on-warn) / <alpha-value>)",
        danger: {
          DEFAULT: "rgb(var(--danger) / <alpha-value>)",
          ink: "rgb(var(--danger-ink) / <alpha-value>)",
        },
        "on-danger": "rgb(var(--on-danger) / <alpha-value>)",
        ok: {
          DEFAULT: "rgb(var(--ok) / <alpha-value>)",
          ink: "rgb(var(--ok-ink) / <alpha-value>)",
        },
      },
      boxShadow: {
        card: "var(--shadow-card)",
      },
    },
  },
  plugins: [],
};
