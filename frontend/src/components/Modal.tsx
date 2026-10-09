import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "./ui";

export default function Modal({
  title,
  eyebrow,
  onClose,
  children,
  footer,
  size = "max-w-2xl",
}: {
  title: string;
  eyebrow?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: string;
}) {
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const previousFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const dialog = dialogRef.current;
    const focusable = dialog?.querySelector<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    (focusable ?? dialog)?.focus();

    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, []);

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;

    const dialog = dialogRef.current;
    if (!dialog) return;
    const focusable = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
    if (!focusable.length) {
      event.preventDefault();
      dialog.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-scrim/60 p-0 backdrop-blur-[2px] sm:items-center sm:p-5"
      role="presentation"
      onKeyDown={handleKeyDown}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        aria-modal="true"
        role="dialog"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`max-h-[92dvh] w-full overflow-y-auto rounded-t-2xl border border-line bg-surface pb-[env(safe-area-inset-bottom)] shadow-2xl motion-safe:animate-[fw-in_160ms_ease-out] sm:rounded-2xl ${size}`}
      >
        <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-line-strong sm:hidden" />
        <header className="sticky top-0 z-10 flex items-start justify-between border-b border-line/60 bg-surface px-5 py-4 sm:px-6">
          <div>
            {eyebrow && (
              <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.15em] text-fg-2">
                {eyebrow}
              </p>
            )}
            <h2 id={titleId} className="text-lg font-bold text-fg tabular-nums">{title}</h2>
          </div>
          <Button
            onClick={onClose}
            variant="ghost"
            size="sm"
            icon={X}
            className="!h-11 !w-11 !min-h-11 !p-0 rounded-xl text-muted hover:bg-surface-3"
            aria-label="Close dialog"
          />
        </header>
        <div className="px-5 py-5 sm:px-6">{children}</div>
        {footer && (
          <div className="sticky bottom-0 flex justify-end gap-2 border-t border-line bg-surface px-5 py-3 sm:px-6">
            {footer}
          </div>
        )}
      </section>
    </div>
  );
}
