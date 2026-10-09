/* eslint-disable react-refresh/only-export-components */
import {
  forwardRef,
  useRef,
  type ButtonHTMLAttributes,
  type ComponentPropsWithoutRef,
  type ElementType,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Loader2, type LucideIcon } from "lucide-react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "warn";
export type ButtonSize = "sm" | "md" | "lg";
export type BadgeTone = "neutral" | "accent" | "ok" | "warn" | "danger" | "info";

const buttonVariants: Record<ButtonVariant, string> = {
  primary: "bg-accent text-on-accent hover:bg-accent-hover",
  secondary: "border border-line-strong bg-surface text-fg-2 hover:bg-surface-2 hover:text-fg",
  ghost: "text-fg-2 hover:bg-surface-2 hover:text-fg",
  danger: "bg-danger text-on-danger hover:bg-danger/90",
  warn: "bg-warn text-on-warn hover:bg-warn/90",
};

const buttonSizes: Record<ButtonSize, string> = {
  sm: "min-h-11 md:min-h-9 rounded-lg px-3 text-xs",
  md: "min-h-11 rounded-xl px-4 text-sm",
  lg: "min-h-12 rounded-xl px-5 text-sm",
};

export function buttonClass(
  variant: ButtonVariant = "secondary",
  size: ButtonSize = "md",
  extra = "",
) {
  return [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50",
    buttonSizes[size],
    buttonVariants[variant],
    extra,
  ]
    .filter(Boolean)
    .join(" ");
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: LucideIcon;
  loading?: boolean;
  full?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "secondary",
      size = "md",
      icon: Icon,
      loading = false,
      full = false,
      className = "",
      disabled,
      type = "button",
      children,
      ...props
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        className={buttonClass(
          variant,
          size,
          `${full ? "w-full" : ""} ${className}`,
        )}
        {...props}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          Icon && <Icon className="h-4 w-4" />
        )}
        {children}
      </button>
    );
  },
);

export const fieldClass =
  "w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-fg placeholder:text-subtle outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/25 disabled:opacity-60 aria-[invalid=true]:border-danger";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className = "", ...props }, ref) {
    return (
      <input
        ref={ref}
        className={`${fieldClass} h-10 ${className}`}
        {...props}
      />
    );
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className = "", ...props }, ref) {
    return (
      <select
        ref={ref}
        className={`${fieldClass} h-10 ${className}`}
        {...props}
      />
    );
  },
);

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className = "", ...props }, ref) {
  return (
    <textarea
      ref={ref}
      className={`${fieldClass} py-2.5 leading-6 resize-y ${className}`}
      {...props}
    />
  );
});

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
  className = "",
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}) {
  const content = (
    <>
      {htmlFor ? (
        <label
          htmlFor={htmlFor}
          className="mb-1.5 block text-xs font-semibold text-fg-2"
        >
          {label}
        </label>
      ) : (
        <span className="mb-1.5 block text-xs font-semibold text-fg-2">
          {label}
        </span>
      )}
      {children}
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {error && (
        <p className="mt-1 text-xs font-medium text-danger-ink" role="alert">
          {error}
        </p>
      )}
    </>
  );

  return htmlFor ? (
    <div className={className}>{content}</div>
  ) : (
    <label className={`block ${className}`}>{content}</label>
  );
}

type CardProps<T extends ElementType> = {
  as?: T;
  className?: string;
} & ComponentPropsWithoutRef<T>;

export function Card<T extends ElementType = "div">({
  as,
  className = "",
  ...props
}: CardProps<T>) {
  const Component = as ?? "div";
  return (
    <Component
      className={`rounded-2xl border border-line bg-surface shadow-card ${className}`}
      {...props}
    />
  );
}

const badgeTones: Record<BadgeTone, string> = {
  neutral: "bg-surface-3 text-fg-2",
  accent: "bg-accent/15 text-accent-ink",
  ok: "bg-ok/15 text-ok-ink",
  warn: "bg-warn/15 text-warn-ink",
  danger: "bg-danger/15 text-danger-ink",
  info: "bg-st-booked/15 text-st-booked-ink",
};

export function Badge({
  tone = "neutral",
  children,
  className = "",
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold ${badgeTones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function Tabs<T extends string>({
  items,
  value,
  onChange,
  ariaLabel,
}: {
  items: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
}) {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  function moveFocus(current: T, direction: -1 | 1) {
    const index = items.findIndex((item) => item.value === current);
    const nextIndex = (index + direction + items.length) % items.length;
    const next = items[nextIndex];
    onChange(next.value);
    tabRefs.current[nextIndex]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="inline-flex flex-wrap gap-1 rounded-xl border border-line bg-surface p-1"
    >
      {items.map((item, index) => (
        <button
          key={item.value}
          ref={(element) => {
            tabRefs.current[index] = element;
          }}
          type="button"
          role="tab"
          aria-selected={value === item.value}
          tabIndex={value === item.value ? 0 : -1}
          onClick={() => onChange(item.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowRight") {
              event.preventDefault();
              moveFocus(item.value, 1);
            } else if (event.key === "ArrowLeft") {
              event.preventDefault();
              moveFocus(item.value, -1);
            }
          }}
          className={`min-h-11 md:min-h-9 rounded-lg px-3 text-sm font-semibold ${
            value === item.value
              ? "bg-surface-3 text-fg"
              : "text-muted hover:text-fg"
          }`}
        >
          {item.label}
          {item.count !== undefined && (
            <span className="ml-1.5 tabular-nums text-xs text-muted">
              {item.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`motion-safe:animate-pulse rounded-md bg-surface-3 ${className}`}
    />
  );
}

export function CardListSkeleton({
  count = 4,
  className = "",
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={`grid gap-4 lg:grid-cols-2 ${className}`}
    >
      <span className="sr-only">Loading…</span>
      {Array.from({ length: count }, (_, index) => (
        <Card key={index} className="space-y-4 p-5">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-1/2" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-9 w-2/3" />
        </Card>
      ))}
    </div>
  );
}
