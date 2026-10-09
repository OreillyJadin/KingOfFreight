import { useId } from "react";

export function FifthWheelMark({
  className,
  title,
}: {
  className?: string;
  title?: string;
}) {
  const id = `fw-mask-${useId().replace(/:/g, "")}`;
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <defs>
        <mask id={id}>
          <rect width="32" height="32" fill="white" />
          <circle cx="16" cy="14.5" r="3.4" fill="black" />
          <path d="M14.1 16.2H17.9L20.8 31.5H11.2Z" fill="black" />
        </mask>
      </defs>
      <circle cx="16" cy="16" r="14.5" fill="currentColor" mask={`url(#${id})`} />
    </svg>
  );
}

export function Wordmark({
  className = "",
  markClassName,
}: {
  className?: string;
  markClassName?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <FifthWheelMark className={markClassName ?? "h-8 w-8 text-accent"} />
      <span className="text-[17px] font-extrabold tracking-tight">Fifth Wheel</span>
    </span>
  );
}
