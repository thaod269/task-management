"use client";

import { ArrowDown, ArrowUp, CalendarDays, ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";

import { COLUMNS, COLUMN_BY_ID, PRIORITY_META } from "@/lib/types";
import type { Task, TaskStatus, TeamMember } from "@/lib/types";
import {
  DUE_TONE_CLASS,
  cn,
  dueMeta,
  subtaskProgress,
} from "@/lib/utils";

import type { BoardActions } from "./board-actions";
import { CardMenu } from "./card-menu";
import { EmptyResults } from "./empty-results";
import { Avatar, UnassignedAvatar } from "./ui/avatar";
import { PriorityBadge, StatusBadge, TagChip, TypeBadge } from "./ui/badge";
import { MenuItem, PopoverMenu } from "./ui/popover-menu";

type SortKey = "title" | "status" | "priority" | "due";

export function TableView({
  tasks,
  membersById,
  today,
  actions,
  hasActiveFilters,
  onClearFilters,
}: {
  tasks: Task[];
  membersById: Map<string, TeamMember>;
  today: string;
  actions: BoardActions;
  hasActiveFilters: boolean;
  onClearFilters: () => void;
}) {
  const [sort, setSort] = useState<{ key: SortKey; asc: boolean }>({
    key: "status",
    asc: true,
  });

  const statusRank = useMemo(
    () => new Map(COLUMNS.map((column, index) => [column.id, index])),
    [],
  );

  const sorted = useMemo(() => {
    const direction = sort.asc ? 1 : -1;
    return [...tasks].sort((a, b) => {
      switch (sort.key) {
        case "title":
          return a.title.localeCompare(b.title) * direction;
        case "priority":
          return (
            (PRIORITY_META[a.priority].rank - PRIORITY_META[b.priority].rank) *
            direction
          );
        case "due":
          // Cards without a due date always sort last.
          if (!a.dueDate && !b.dueDate) return 0;
          if (!a.dueDate) return 1;
          if (!b.dueDate) return -1;
          return a.dueDate.localeCompare(b.dueDate) * direction;
        case "status":
        default:
          return (
            ((statusRank.get(a.status) ?? 0) - (statusRank.get(b.status) ?? 0)) *
            direction
          );
      }
    });
  }, [tasks, sort, statusRank]);

  const toggleSort = (key: SortKey) =>
    setSort((current) =>
      current.key === key ? { key, asc: !current.asc } : { key, asc: true },
    );

  if (tasks.length === 0) {
    return hasActiveFilters ? (
      <EmptyResults onClearFilters={onClearFilters} />
    ) : (
      <div className="flex h-full items-center justify-center px-6 pb-16 text-sm text-slate-500">
        This board is empty — create your first task to get going.
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto px-4 pb-6 sm:px-6 scrollbar-slim">
      <div className="min-w-[52rem] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="sticky top-0 z-10 bg-slate-50/95 backdrop-blur">
            <tr className="border-b border-slate-200">
              <SortableHeader
                label="Task"
                sortKey="title"
                sort={sort}
                onSort={toggleSort}
                className="w-[38%]"
              />
              <SortableHeader
                label="Status"
                sortKey="status"
                sort={sort}
                onSort={toggleSort}
              />
              <HeaderCell>Assignee</HeaderCell>
              <SortableHeader
                label="Priority"
                sortKey="priority"
                sort={sort}
                onSort={toggleSort}
              />
              <SortableHeader
                label="Due"
                sortKey="due"
                sort={sort}
                onSort={toggleSort}
              />
              <HeaderCell className="hidden lg:table-cell">Checklist</HeaderCell>
              <HeaderCell className="w-12">
                <span className="sr-only">Actions</span>
              </HeaderCell>
            </tr>
          </thead>

          <tbody>
            {sorted.map((task) => {
              const assignee = task.assigneeId
                ? membersById.get(task.assigneeId) ?? null
                : null;
              const progress = subtaskProgress(task.subtasks);
              const due = task.dueDate ? dueMeta(task.dueDate, today) : null;
              const isDone = task.status === "done";

              return (
                <tr
                  key={task.id}
                  className="group border-b border-slate-100 transition-colors duration-150 last:border-0 hover:bg-slate-50/70"
                >
                  <td className="px-4 py-3 align-middle">
                    <div className="flex items-start gap-2">
                      <TypeBadge type={task.type} />
                      <div className="min-w-0">
                        <button
                          type="button"
                          onClick={() => actions.onEdit(task)}
                          className="block max-w-full truncate text-left text-sm font-medium text-slate-900 transition-colors hover:text-slate-600"
                        >
                          {task.title}
                        </button>
                        {task.tags.length > 0 && (
                          <div className="mt-1 hidden flex-wrap gap-1 lg:flex">
                            {task.tags.map((tag) => (
                              <TagChip key={tag} tag={tag} />
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>

                  <td className="px-4 py-3 align-middle">
                    <StatusPicker
                      task={task}
                      onChange={(status) => actions.onMove(task.id, status)}
                    />
                  </td>

                  <td className="px-4 py-3 align-middle">
                    <span className="flex items-center gap-2">
                      {assignee ? (
                        <>
                          <Avatar member={assignee} size="sm" />
                          <span className="truncate text-xs font-medium text-slate-600">
                            {assignee.name}
                          </span>
                        </>
                      ) : (
                        <>
                          <UnassignedAvatar size="sm" />
                          <span className="text-xs text-slate-400">Unassigned</span>
                        </>
                      )}
                    </span>
                  </td>

                  <td className="px-4 py-3 align-middle">
                    <PriorityBadge priority={task.priority} />
                  </td>

                  <td className="px-4 py-3 align-middle">
                    {due ? (
                      <span
                        title={due.absolute}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset",
                          isDone ? DUE_TONE_CLASS.normal : DUE_TONE_CLASS[due.tone],
                        )}
                      >
                        <CalendarDays className="h-3 w-3" />
                        {isDone ? due.absolute : due.label}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-300">—</span>
                    )}
                  </td>

                  <td className="hidden px-4 py-3 align-middle lg:table-cell">
                    {progress.total > 0 ? (
                      <span className="flex items-center gap-2">
                        <span className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
                          <span
                            className={cn(
                              "block h-full rounded-full transition-[width] duration-300",
                              progress.done === progress.total
                                ? "bg-emerald-500"
                                : "bg-slate-900",
                            )}
                            style={{ width: `${progress.percent}%` }}
                          />
                        </span>
                        <span className="text-xs tabular-nums text-slate-500">
                          {progress.done}/{progress.total}
                        </span>
                      </span>
                    ) : (
                      <span className="text-xs text-slate-300">—</span>
                    )}
                  </td>

                  <td className="px-2 py-3 align-middle">
                    <CardMenu
                      task={task}
                      onEdit={() => actions.onEdit(task)}
                      onMove={(status) => actions.onMove(task.id, status)}
                      onDelete={() => actions.onDelete(task.id)}
                      onPromote={
                        task.type === "idea"
                          ? () => actions.onPromote(task.id)
                          : undefined
                      }
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Inline status change — the table's equivalent of dragging between columns. */
function StatusPicker({
  task,
  onChange,
}: {
  task: Task;
  onChange: (status: TaskStatus) => void;
}) {
  return (
    <PopoverMenu
      label={`Change status of ${task.title}`}
      trigger={({ open, toggle }) => (
        <button
          type="button"
          onClick={toggle}
          aria-label={`Change status of ${task.title}`}
          aria-haspopup="menu"
          aria-expanded={open}
          className="inline-flex items-center gap-1 rounded-md transition-opacity duration-150 hover:opacity-80"
        >
          <StatusBadge status={task.status} />
          <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
        </button>
      )}
    >
      {(close) => (
        <>
          {COLUMNS.map((column) => (
            <MenuItem
              key={column.id}
              selected={column.id === task.status}
              icon={<span aria-hidden>{column.emoji}</span>}
              onClick={() => {
                onChange(column.id);
                close();
              }}
            >
              {COLUMN_BY_ID[column.id].title}
            </MenuItem>
          ))}
        </>
      )}
    </PopoverMenu>
  );
}

function HeaderCell({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500",
        className,
      )}
    >
      {children}
    </th>
  );
}

function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
  className,
}: {
  label: string;
  sortKey: SortKey;
  sort: { key: SortKey; asc: boolean };
  onSort: (key: SortKey) => void;
  className?: string;
}) {
  const active = sort.key === sortKey;
  return (
    <th
      scope="col"
      aria-sort={active ? (sort.asc ? "ascending" : "descending") : "none"}
      className={cn("px-4 py-2.5", className)}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          "inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide transition-colors duration-150",
          active ? "text-slate-900" : "text-slate-500 hover:text-slate-900",
        )}
      >
        {label}
        {active ? (
          sort.asc ? (
            <ArrowUp className="h-3 w-3" />
          ) : (
            <ArrowDown className="h-3 w-3" />
          )
        ) : (
          <ArrowDown className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-40" />
        )}
      </button>
    </th>
  );
}
