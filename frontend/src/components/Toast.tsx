import { useCallback, useState, type ReactNode } from "react";
import { CheckCircle2, X, XCircle } from "lucide-react";
import { ToastContext, type ToastMessage } from "../toast-context";

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastMessage[]>([]);
  const showToast = useCallback(
    (message: string, tone: ToastMessage["tone"] = "success") => {
      const id = Date.now() + Math.random();
      setItems((current) => [...current, { id, message, tone }]);
      window.setTimeout(
        () => setItems((current) => current.filter((item) => item.id !== id)),
        3600,
      );
    },
    [],
  );
  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed right-4 top-20 z-[100] flex w-[min(92vw,360px)] flex-col gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className="flex items-start gap-3 rounded-xl border border-line bg-surface px-4 py-3 shadow-xl"
            role="status"
          >
            {item.tone === "success" ? (
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-ok-ink" />
            ) : (
              <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-danger-ink" />
            )}
            <span className="flex-1 text-sm text-fg-2">{item.message}</span>
            <button
              className="grid h-7 w-7 place-items-center rounded-lg text-subtle hover:bg-surface-3"
              aria-label="Dismiss notification"
              onClick={() => setItems((current) => current.filter((toast) => toast.id !== item.id))}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
