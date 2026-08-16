import { COLUMN_BY_ID, PRIORITY_META } from "@/lib/types";
import type { ItemType, Priority, TaskStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PriorityBadge({
  priority,
  className,
}: {
  priority: Priority;
  className?: string;
}) {
  const meta = PRIORITY_META[priority];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        meta.chip,
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", meta.dot)} />
      {meta.label}
    </span>
  );
}

const STATUS_CHIP: Record<TaskStatus, string> = {
  backlog: "bg-violet-50 text-violet-700 ring-violet-200",
  todo: "bg-slate-100 text-slate-600 ring-slate-200",
  "in-progress": "bg-blue-50 text-blue-700 ring-blue-200",
  review: "bg-amber-50 text-amber-700 ring-amber-200",
  done: "bg-emerald-50 text-emerald-700 ring-emerald-200",
};

const STATUS_SHORT: Record<TaskStatus, string> = {
  backlog: "Backlog",
  todo: "To Do",
  "in-progress": "In Progress",
  review: "Review",
  done: "Done",
};

export function StatusBadge({
  status,
  className,
}: {
  status: TaskStatus;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        STATUS_CHIP[status],
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", COLUMN_BY_ID[status].dot)} />
      {STATUS_SHORT[status]}
    </span>
  );
}

export function TagChip({ tag, className }: { tag: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center truncate rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600",
        className,
      )}
    >
      #{tag}
    </span>
  );
}

export function TypeBadge({ type }: { type: ItemType }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ring-inset",
        type === "idea"
          ? "bg-violet-50 text-violet-700 ring-violet-200"
          : "bg-slate-100 text-slate-600 ring-slate-200",
      )}
    >
      {type === "idea" ? "Idea" : "Task"}
    </span>
  );
}

export { STATUS_SHORT };
