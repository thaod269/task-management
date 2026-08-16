/**
 * Domain types for the task board.
 *
 * Everything is intentionally serialisable (plain strings / numbers) so the
 * mock data can be rendered identically on the server and the client.
 */

export type TaskStatus = "backlog" | "todo" | "in-progress" | "review" | "done";

export type Priority = "low" | "medium" | "high" | "urgent";

/** A `idea` is a lightweight brainstorm card; a `task` is a tracked unit of work. */
export type ItemType = "idea" | "task";

export interface TeamMember {
  id: string;
  name: string;
  role: string;
  initials: string;
  /** Tailwind classes used for the member's avatar chip. */
  accent: string;
}

export interface Subtask {
  id: string;
  title: string;
  done: boolean;
}

export interface Task {
  id: string;
  type: ItemType;
  title: string;
  /** Markdown supported — rendered by `components/ui/markdown.tsx`. */
  description: string;
  status: TaskStatus;
  priority: Priority;
  assigneeId: string | null;
  /** Who raised the idea / created the task. */
  authorId: string;
  /** ISO date only (`yyyy-mm-dd`) so formatting is timezone independent. */
  dueDate: string | null;
  tags: string[];
  subtasks: Subtask[];
  votes: number;
  votedByMe: boolean;
  createdAt: string;
}

export interface ColumnMeta {
  id: TaskStatus;
  emoji: string;
  title: string;
  description: string;
  /** Small colour accent used for the column dot + count pill. */
  dot: string;
  pill: string;
}

export const COLUMNS: ColumnMeta[] = [
  {
    id: "backlog",
    emoji: "💡",
    title: "Brainstorm / Backlog",
    description: "Raw ideas waiting to be shaped",
    dot: "bg-violet-500",
    pill: "bg-violet-50 text-violet-700",
  },
  {
    id: "todo",
    emoji: "📋",
    title: "To Do",
    description: "Scoped and ready to pick up",
    dot: "bg-slate-400",
    pill: "bg-slate-100 text-slate-600",
  },
  {
    id: "in-progress",
    emoji: "⚙️",
    title: "In Progress",
    description: "Actively being worked on",
    dot: "bg-blue-500",
    pill: "bg-blue-50 text-blue-700",
  },
  {
    id: "review",
    emoji: "🧪",
    title: "Code Review / Testing",
    description: "Awaiting review or QA",
    dot: "bg-amber-500",
    pill: "bg-amber-50 text-amber-700",
  },
  {
    id: "done",
    emoji: "🚀",
    title: "Deployed / Done",
    description: "Shipped to production",
    dot: "bg-emerald-500",
    pill: "bg-emerald-50 text-emerald-700",
  },
];

export const COLUMN_BY_ID: Record<TaskStatus, ColumnMeta> = COLUMNS.reduce(
  (acc, column) => {
    acc[column.id] = column;
    return acc;
  },
  {} as Record<TaskStatus, ColumnMeta>,
);

export const PRIORITIES: Priority[] = ["low", "medium", "high", "urgent"];

export const PRIORITY_META: Record<
  Priority,
  { label: string; chip: string; dot: string; rank: number }
> = {
  low: {
    label: "Low",
    chip: "bg-slate-50 text-slate-600 ring-slate-200",
    dot: "bg-slate-400",
    rank: 0,
  },
  medium: {
    label: "Medium",
    chip: "bg-sky-50 text-sky-700 ring-sky-200",
    dot: "bg-sky-500",
    rank: 1,
  },
  high: {
    label: "High",
    chip: "bg-amber-50 text-amber-700 ring-amber-200",
    dot: "bg-amber-500",
    rank: 2,
  },
  urgent: {
    label: "Urgent",
    chip: "bg-rose-50 text-rose-700 ring-rose-200",
    dot: "bg-rose-500",
    rank: 3,
  },
};
