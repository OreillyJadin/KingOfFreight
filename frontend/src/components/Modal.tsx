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
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/50 p-0 backdrop-blur-[2px] sm:items-center sm:p-5"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        aria-modal="true"
        role="dialog"
        aria-label={title}
        className={`max-h-[92dvh] w-full overflow-y-auto rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl ${size}`}
      >
        <header className="sticky top-0 z-10 flex items-start justify-between border-b border-slate-100 bg-white px-5 py-4 sm:px-6">
          <div>
            {eyebrow && (
              <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.15em] text-blue-600">
                {eyebrow}
              </p>
            )}
            <h2 className="text-lg font-bold text-ink">{title}</h2>
          </div>
          <button
            onClick={onClose}
            className="grid h-11 w-11 place-items-center rounded-xl text-slate-500 transition hover:bg-slate-100"
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
