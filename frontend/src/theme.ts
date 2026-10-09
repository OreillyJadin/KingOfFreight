import { useSyncExternalStore } from "react";

export type Theme = "dark" | "light";

type Listener = () => void;

const listeners = new Set<Listener>();
let theme: Theme =
  typeof document !== "undefined" && document.documentElement.dataset.theme === "light"
    ? "light"
    : "dark";

function subscribe(listener: Listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return theme;
}

function setTheme(nextTheme: Theme) {
  theme = nextTheme;
  document.documentElement.dataset.theme = nextTheme;
  try {
    localStorage.setItem("fw-theme", nextTheme);
  } catch {
    // The in-memory theme still works when storage is unavailable.
  }
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta)
    meta.content =
      nextTheme === "dark" ? "rgb(11, 18, 32)" : "rgb(247, 248, 250)";
  listeners.forEach((listener) => listener());
}

export function useTheme(): {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggle: () => void;
} {
  const currentTheme = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return {
    theme: currentTheme,
    setTheme,
    toggle: () => setTheme(currentTheme === "dark" ? "light" : "dark"),
  };
}
