import type { KeyboardEvent, ReactNode } from "react";
import { useMediaQuery } from "../useMediaQuery";
import Modal from "./Modal";
import { Card, Skeleton } from "./ui";

export function ListDetail({
  list,
  detail,
  detailTitle,
  onCloseDetail,
}: {
  list: ReactNode;
  detail: ReactNode | null;
  detailTitle: string;
  onCloseDetail: () => void;
}) {
  const wide = useMediaQuery("(min-width: 1280px)");

  if (wide) {
    return detail ? (
      <div className="grid grid-cols-[minmax(340px,420px)_1fr] items-start gap-5">
        <div className="sticky top-6 max-h-[calc(100dvh-3rem)] overflow-y-auto">
          {list}
        </div>
        <div className="sticky top-6 max-h-[calc(100dvh-3rem)] overflow-y-auto">
          <Card className="p-5">{detail}</Card>
        </div>
      </div>
    ) : (
      <div className="w-full">{list}</div>
    );
  }

  return (
    <>
      {list}
      {detail !== null && (
        <Modal title={detailTitle} onClose={onCloseDetail}>
          {detail}
        </Modal>
      )}
    </>
  );
}

export function ListRow({
  selected,
  onSelect,
  children,
}: {
  selected: boolean;
  onSelect: () => void;
  children: ReactNode;
}) {
  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const list = event.currentTarget.closest('[role="list"]');
    if (!list) return;
    const rows = Array.from(
      list.querySelectorAll<HTMLButtonElement>("button[data-list-detail-row]"),
    );
    const index = rows.indexOf(event.currentTarget);
    const next = rows[index + (event.key === "ArrowDown" ? 1 : -1)];
    if (!next) return;
    event.preventDefault();
    next.focus();
    next.click();
  }

  return (
    <button
      type="button"
      data-list-detail-row
      aria-current={selected ? "true" : undefined}
      onClick={onSelect}
      onKeyDown={handleKeyDown}
      className={`flex w-full min-h-11 flex-col items-stretch rounded-xl border px-3 py-3 text-left transition-colors duration-150 ${
        selected
          ? "border-line-strong bg-surface-3"
          : "border-transparent hover:bg-surface-2"
      }`}
    >
      {children}
    </button>
  );
}

export function ListRowSkeleton() {
  return (
    <Card className="space-y-1 p-2">
      {Array.from({ length: 6 }, (_, index) => (
        <Skeleton key={index} className="h-14" />
      ))}
    </Card>
  );
}
