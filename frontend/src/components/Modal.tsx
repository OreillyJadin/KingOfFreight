import { X } from "lucide-react";
import type { ReactNode } from "react";

export default function Modal({
  title,
  eyebrow,
  onClose,
  children,
  size = "max-w-2xl",
}: {
  title: string;
  eyebrow?: string;
  onClose: () => void;
  children: ReactNode;
  size?: string;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-scrim/60 p-0 backdrop-blur-[2px] sm:items-center sm:p-5"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        aria-modal="true"
        role="dialog"
        aria-label={title}
        className={`max-h-[92dvh] w-full overflow-y-auto rounded-t-2xl bg-surface shadow-2xl sm:rounded-2xl ${size}`}
      >
        <header className="sticky top-0 z-10 flex items-start justify-between border-b border-line/60 bg-surface px-5 py-4 sm:px-6">
          <div>
            {eyebrow && (
              <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.15em] text-accent-ink">
                {eyebrow}
              </p>
            )}
            <h2 className="text-lg font-bold text-fg tabular-nums">{title}</h2>
          </div>
          <button
            onClick={onClose}
            className="grid h-11 w-11 place-items-center rounded-xl text-muted transition hover:bg-surface-3"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </header>
        <div className="px-5 py-5 sm:px-6">{children}</div>
      </section>
    </div>
  );
}
