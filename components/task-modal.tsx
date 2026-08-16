"use client";

import {
  CalendarDays,
  Check,
  Eye,
  Lightbulb,
  ListChecks,
  Pencil,
  Plus,
  SquareCheck,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

import { COLUMNS, PRIORITIES, PRIORITY_META } from "@/lib/types";
import type {
  ItemType,
  Priority,
  Subtask,
  Task,
  TaskStatus,
  TeamMember,
} from "@/lib/types";
import { cn, createId, subtaskProgress } from "@/lib/utils";

import { Avatar, UnassignedAvatar } from "./ui/avatar";
import { Dropdown, type DropdownOption } from "./ui/dropdown";
import { Markdown } from "./ui/markdown";

export interface EditorTarget {
  /** `null` when creating. */
  task: Task | null;
  presetStatus: TaskStatus;
  presetType: ItemType;
}

export interface TaskDraft {
  title: string;
  description: string;
  type: ItemType;
  status: TaskStatus;
  priority: Priority;
  assigneeId: string | null;
  dueDate: string | null;
  tags: string[];
  subtasks: Subtask[];
}

const UNASSIGNED = "__unassigned__";

function initialDraft(target: EditorTarget): TaskDraft {
  const { task } = target;
  if (task) {
    return {
      title: task.title,
      description: task.description,
      type: task.type,
      status: task.status,
      priority: task.priority,
      assigneeId: task.assigneeId,
      dueDate: task.dueDate,
      tags: [...task.tags],
      subtasks: task.subtasks.map((subtask) => ({ ...subtask })),
    };
  }
  return {
    title: "",
    description: "",
    type: target.presetType,
    status: target.presetStatus,
    priority: target.presetType === "idea" ? "low" : "medium",
    assigneeId: null,
    dueDate: null,
    tags: [],
    subtasks: [],
  };
}

export function TaskModal({
  target,
  members,
  onClose,
  onSubmit,
  onDelete,
}: {
  target: EditorTarget;
  members: TeamMember[];
  onClose: () => void;
  onSubmit: (draft: TaskDraft) => void;
  onDelete: (id: string) => void;
}) {
  const [draft, setDraft] = useState<TaskDraft>(() => initialDraft(target));
  const [showPreview, setShowPreview] = useState(false);
  const [touched, setTouched] = useState(false);

  const dialogRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);

  const isEditing = target.task !== null;
  const titleError = touched && !draft.title.trim();

  const patch = (changes: Partial<TaskDraft>) =>
    setDraft((current) => ({ ...current, ...changes }));

  /*
   * Ideas live in the Brainstorm column by definition — keep the two fields in
   * sync in both directions so the board never ends up with a stray idea card.
   */
  const setType = (type: ItemType) =>
    patch(
      type === "idea"
        ? { type, status: "backlog" }
        : { type, status: draft.status === "backlog" ? "todo" : draft.status },
    );

  const setStatus = (status: TaskStatus) =>
    patch(
      status === "backlog" ? { status } : { status, type: "task" as ItemType },
    );

  // Focus the title on open, restore focus to the invoker on close, and stop
  // the page behind the dialog from scrolling.
  useEffect(() => {
    const invoker = document.activeElement as HTMLElement | null;
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    titleRef.current?.focus();
    titleRef.current?.select();

    return () => {
      document.body.style.overflow = overflow;
      invoker?.focus?.();
    };
  }, []);

  const submit = () => {
    if (!draft.title.trim()) {
      setTouched(true);
      titleRef.current?.focus();
      return;
    }
    onSubmit({ ...draft, title: draft.title.trim() });
  };

  /** Escape closes, ⌘/Ctrl + Enter saves, Tab stays inside the dialog. */
  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }

    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      submit();
      return;
    }

    if (event.key !== "Tab" || !dialogRef.current) return;

    const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const assigneeOptions: DropdownOption<string>[] = [
    {
      value: UNASSIGNED,
      label: "Unassigned",
      icon: <UnassignedAvatar size="xs" />,
    },
    ...members.map((member) => ({
      value: member.id,
      label: member.name,
      hint: member.role,
      icon: <Avatar member={member} size="xs" />,
    })),
  ];

  const statusOptions: DropdownOption<TaskStatus>[] = COLUMNS.map((column) => ({
    value: column.id,
    label: column.title,
    icon: <span aria-hidden>{column.emoji}</span>,
  }));

  const priorityOptions: DropdownOption<Priority>[] = PRIORITIES.map((priority) => ({
    value: priority,
    label: PRIORITY_META[priority].label,
    icon: (
      <span className={cn("h-2 w-2 rounded-full", PRIORITY_META[priority].dot)} />
    ),
  }));

  const progress = subtaskProgress(draft.subtasks);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center overflow-y-auto bg-slate-900/40 p-0 backdrop-blur-sm animate-fade-in sm:items-center sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={isEditing ? "Edit card" : "New card"}
        onKeyDown={onKeyDown}
        className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl shadow-slate-900/20 animate-scale-in sm:max-h-[88vh] sm:rounded-2xl"
      >
        {/* Header */}
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-slate-900">
              {isEditing ? "Edit card" : draft.type === "idea" ? "New idea" : "New task"}
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">
              {isEditing
                ? "Update the details and save your changes."
                : "Capture it now — you can refine it later."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-4.5 w-4.5" />
          </button>
        </header>

        {/* Body */}
        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 scrollbar-slim">
          <Field label="Type">
            <div className="inline-flex rounded-lg bg-slate-100 p-1">
              <SegmentButton
                active={draft.type === "idea"}
                onClick={() => setType("idea")}
                icon={<Lightbulb className="h-3.5 w-3.5" />}
              >
                Idea
              </SegmentButton>
              <SegmentButton
                active={draft.type === "task"}
                onClick={() => setType("task")}
                icon={<SquareCheck className="h-3.5 w-3.5" />}
              >
                Task
              </SegmentButton>
            </div>
          </Field>

          <Field label="Title" required error={titleError ? "A title is required" : undefined}>
            <input
              ref={titleRef}
              value={draft.title}
              onChange={(event) => patch({ title: event.target.value })}
              onBlur={() => setTouched(true)}
              placeholder={
                draft.type === "idea"
                  ? "What if we…"
                  : "e.g. Add rate limiting to the public API"
              }
              className={cn(
                "w-full rounded-lg border bg-white px-3 py-2.5 text-sm font-medium text-slate-900 shadow-xs transition-colors duration-150 outline-none placeholder:font-normal placeholder:text-slate-400",
                titleError
                  ? "border-rose-300 focus:border-rose-400"
                  : "border-slate-200 focus:border-slate-400",
              )}
            />
          </Field>

          <Field
            label="Description"
            hint="Markdown supported"
            action={
              <button
                type="button"
                onClick={() => setShowPreview((previous) => !previous)}
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium text-slate-500 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900"
              >
                {showPreview ? (
                  <>
                    <Pencil className="h-3 w-3" /> Write
                  </>
                ) : (
                  <>
                    <Eye className="h-3 w-3" /> Preview
                  </>
                )}
              </button>
            }
          >
            {showPreview ? (
              <div className="min-h-[7.5rem] rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2.5">
                {draft.description.trim() ? (
                  <Markdown source={draft.description} />
                ) : (
                  <p className="text-sm text-slate-400">Nothing to preview yet.</p>
                )}
              </div>
            ) : (
              <textarea
                value={draft.description}
                onChange={(event) => patch({ description: event.target.value })}
                rows={5}
                placeholder={"Add context…\n\n**Bold**, `code`, - bullet lists and [links](https://example.com) all work."}
                className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm leading-relaxed text-slate-700 shadow-xs transition-colors duration-150 outline-none placeholder:text-slate-400 focus:border-slate-400"
              />
            )}
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Assignee">
              <Dropdown
                label="Assignee"
                value={draft.assigneeId ?? UNASSIGNED}
                options={assigneeOptions}
                onChange={(value) =>
                  patch({ assigneeId: value === UNASSIGNED ? null : value })
                }
              />
            </Field>

            <Field label="Status">
              <Dropdown
                label="Status"
                value={draft.status}
                options={statusOptions}
                onChange={setStatus}
              />
            </Field>

            <Field label="Priority">
              <Dropdown
                label="Priority"
                value={draft.priority}
                options={priorityOptions}
                onChange={(priority) => patch({ priority })}
              />
            </Field>

            <Field label="Due date">
              <div className="relative">
                <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  type="date"
                  value={draft.dueDate ?? ""}
                  onChange={(event) => patch({ dueDate: event.target.value || null })}
                  className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-700 shadow-xs transition-colors duration-150 outline-none focus:border-slate-400"
                />
              </div>
            </Field>
          </div>

          <Field label="Tags" hint="Press Enter to add">
            <TagEditor tags={draft.tags} onChange={(tags) => patch({ tags })} />
          </Field>

          <Field
            label="Checklist"
            hint={
              progress.total > 0 ? `${progress.done}/${progress.total} done` : undefined
            }
          >
            <ChecklistEditor
              subtasks={draft.subtasks}
              onChange={(subtasks) => patch({ subtasks })}
            />
          </Field>
        </div>

        {/* Footer */}
        <footer className="flex items-center justify-between gap-3 border-t border-slate-200 bg-slate-50/70 px-5 py-3.5">
          {isEditing ? (
            <button
              type="button"
              onClick={() => onDelete(target.task!.id)}
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-medium text-rose-600 transition-colors duration-150 hover:bg-rose-50"
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </button>
          ) : (
            <span className="hidden text-xs text-slate-400 sm:block">
              Tip: press <Kbd>⌘</Kbd> + <Kbd>↵</Kbd> to save
            </span>
          )}

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-xs transition-colors duration-150 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={submit}
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-semibold text-white shadow-sm transition-all duration-150 hover:bg-slate-700 active:scale-[0.98]"
            >
              <Check className="h-4 w-4" />
              {isEditing ? "Save changes" : "Create"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Form pieces                                                                */
/* -------------------------------------------------------------------------- */

function Field({
  label,
  hint,
  required,
  error,
  action,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  error?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-slate-700">
          {label}
          {required && <span className="ml-0.5 text-rose-500">*</span>}
          {hint && <span className="ml-2 font-normal text-slate-400">{hint}</span>}
        </span>
        {action}
      </div>
      {children}
      {error && <p className="mt-1 text-xs font-medium text-rose-600">{error}</p>}
    </div>
  );
}

function SegmentButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-all duration-150",
        active
          ? "bg-white text-slate-900 shadow-xs"
          : "text-slate-500 hover:text-slate-900",
      )}
    >
      {icon}
      {children}
    </button>
  );
}

function TagEditor({
  tags,
  onChange,
}: {
  tags: string[];
  onChange: (tags: string[]) => void;
}) {
  const [value, setValue] = useState("");

  const add = () => {
    const tag = value.trim().replace(/^#/, "").toLowerCase();
    if (tag && !tags.includes(tag)) onChange([...tags, tag]);
    setValue("");
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-2 shadow-xs focus-within:border-slate-400">
      <Tag className="h-4 w-4 shrink-0 text-slate-400" />
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-md bg-slate-100 py-0.5 pl-2 pr-1 text-xs font-medium text-slate-700"
        >
          #{tag}
          <button
            type="button"
            onClick={() => onChange(tags.filter((item) => item !== tag))}
            aria-label={`Remove tag ${tag}`}
            className="rounded p-0.5 text-slate-400 transition-colors duration-150 hover:bg-slate-200 hover:text-slate-700"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onBlur={add}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === ",") {
            event.preventDefault();
            add();
          } else if (event.key === "Backspace" && !value && tags.length > 0) {
            onChange(tags.slice(0, -1));
          }
        }}
        placeholder={tags.length === 0 ? "design, api, bug…" : "Add another…"}
        className="min-w-[7rem] flex-1 bg-transparent px-1 py-0.5 text-sm text-slate-700 outline-none placeholder:text-slate-400"
      />
    </div>
  );
}

function ChecklistEditor({
  subtasks,
  onChange,
}: {
  subtasks: Subtask[];
  onChange: (subtasks: Subtask[]) => void;
}) {
  const [value, setValue] = useState("");
  const progress = subtaskProgress(subtasks);

  const add = () => {
    const title = value.trim();
    if (!title) return;
    onChange([...subtasks, { id: createId("s"), title, done: false }]);
    setValue("");
  };

  return (
    <div className="space-y-2">
      {subtasks.length > 0 && (
        <>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className={cn(
                "h-full rounded-full transition-[width] duration-300 ease-out",
                progress.done === progress.total ? "bg-emerald-500" : "bg-slate-900",
              )}
              style={{ width: `${progress.percent}%` }}
            />
          </div>

          <ul className="space-y-1">
            {subtasks.map((subtask, index) => (
              <li
                key={subtask.id}
                className="group flex items-center gap-2 rounded-lg border border-transparent px-1 py-0.5 transition-colors duration-150 hover:border-slate-200 hover:bg-slate-50"
              >
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={subtask.done}
                  aria-label={subtask.title}
                  onClick={() =>
                    onChange(
                      subtasks.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, done: !item.done } : item,
                      ),
                    )
                  }
                  className={cn(
                    "flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded border transition-all duration-150",
                    subtask.done
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-300 bg-white hover:border-slate-500",
                  )}
                >
                  {subtask.done && <Check className="h-3 w-3" strokeWidth={3} />}
                </button>

                <input
                  value={subtask.title}
                  onChange={(event) =>
                    onChange(
                      subtasks.map((item, itemIndex) =>
                        itemIndex === index
                          ? { ...item, title: event.target.value }
                          : item,
                      ),
                    )
                  }
                  className={cn(
                    "min-w-0 flex-1 bg-transparent py-1 text-sm outline-none",
                    subtask.done ? "text-slate-400 line-through" : "text-slate-700",
                  )}
                />

                <button
                  type="button"
                  onClick={() =>
                    onChange(subtasks.filter((_, itemIndex) => itemIndex !== index))
                  }
                  aria-label={`Remove ${subtask.title}`}
                  className="rounded p-1 text-slate-300 opacity-0 transition-all duration-150 hover:bg-slate-200 hover:text-slate-700 focus-visible:opacity-100 group-hover:opacity-100"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="flex items-center gap-2 rounded-lg border border-dashed border-slate-300 px-2 py-1.5 focus-within:border-slate-400">
        <ListChecks className="h-4 w-4 shrink-0 text-slate-400" />
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
          placeholder="Add a checklist item…"
          className="min-w-0 flex-1 bg-transparent py-0.5 text-sm text-slate-700 outline-none placeholder:text-slate-400"
        />
        <button
          type="button"
          onClick={add}
          disabled={!value.trim()}
          aria-label="Add checklist item"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-slate-400 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-slate-300 bg-white px-1 py-0.5 font-sans text-[10px] font-medium text-slate-500">
      {children}
    </kbd>
  );
}
