import { Moon, Sun } from "lucide-react";
import { useTheme } from "../theme";

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggle } = useTheme();
  const label = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  const Icon = theme === "dark" ? Sun : Moon;

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className={`grid h-11 w-11 place-items-center rounded-xl text-muted transition hover:bg-surface-2 hover:text-fg ${className}`}
    >
      <Icon className="h-5 w-5" />
    </button>
  );
}
