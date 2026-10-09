import { useCallback, useState, type ReactNode } from "react";
import { CheckCircle2, X, XCircle } from "lucide-react";
import { ToastContext, type ToastMessage } from "../toast-context";
import { Button } from "./ui";

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
      <div
        aria-live="polite"
        className="fixed bottom-20 left-1/2 z-[100] flex w-[min(92vw,360px)] -translate-x-1/2 flex-col gap-2 md:top-20 md:right-4 md:bottom-auto md:left-auto md:translate-x-0"
      >
        {items.map((item) => (
          <div
            key={item.id}
            className={`flex items-start gap-3 rounded-xl border border-line border-l-[3px] bg-surface px-4 py-3 shadow-xl motion-safe:animate-[fw-in_160ms_ease-out] ${
              item.tone === "success" ? "border-l-ok" : "border-l-danger"
            }`}
            role={item.tone === "error" ? "alert" : "status"}
          >
            {item.tone === "success" ? (
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-ok-ink" />
            ) : (
              <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-danger-ink" />
            )}
            <span className="flex-1 text-sm text-fg-2">{item.message}</span>
            <Button
              variant="ghost"
              size="sm"
              icon={X}
              className="!h-11 !w-11 !min-h-11 -my-2 -mr-2 !p-0 rounded-lg text-subtle hover:bg-surface-3"
              aria-label="Dismiss notification"
              onClick={() => setItems((current) => current.filter((toast) => toast.id !== item.id))}
            />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
