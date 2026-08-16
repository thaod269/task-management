"use client";

import {
  LayoutGrid,
  Plus,
  Search,
  Sparkles,
  Table2,
  Users,
  X,
} from "lucide-react";
import { useEffect, useRef } from "react";

import { PROJECT } from "@/lib/mock-data";
import { COLUMNS, PRIORITIES, PRIORITY_META } from "@/lib/types";
import type { Priority, TaskStatus, TeamMember } from "@/lib/types";
import { cn } from "@/lib/utils";

import { Avatar, AvatarStack, UnassignedAvatar } from "./ui/avatar";
import { Dropdown, type DropdownOption } from "./ui/dropdown";

export type BoardView = "kanban" | "table";
export const UNASSIGNED_FILTER = "__unassigned__";

export function BoardHeader({
  members,
  view,
  onViewChange,
  search,
  onSearchChange,
  memberFilter,
  onMemberFilterChange,
  priorityFilter,
  onPriorityFilterChange,
  statusFilter,
  onStatusFilterChange,
  hasActiveFilters,
  onClearFilters,
  onOpenTeam,
  onNewTask,
  onNewIdea,
  resultCount,
  totalCount,
  overdueCount,
}: {
  members: TeamMember[];
  view: BoardView;
  onViewChange: (view: BoardView) => void;
  search: string;
  onSearchChange: (search: string) => void;
  memberFilter: string;
  onMemberFilterChange: (value: string) => void;
  priorityFilter: Priority | "all";
  onPriorityFilterChange: (value: Priority | "all") => void;
  statusFilter: TaskStatus | "all";
  onStatusFilterChange: (value: TaskStatus | "all") => void;
  hasActiveFilters: boolean;
  onClearFilters: () => void;
  onOpenTeam: () => void;
  onNewTask: () => void;
  onNewIdea: () => void;
  resultCount: number;
  totalCount: number;
  overdueCount: number;
}) {
  const searchRef = useRef<HTMLInputElement>(null);

  // "/" focuses search, the way most boards behave.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      event.preventDefault();
      searchRef.current?.focus();
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const memberOptions: DropdownOption<string>[] = [
    { value: "all", label: "All members", icon: <Users className="h-4 w-4 text-slate-400" /> },
    ...members.map((member) => ({
      value: member.id,
      label: member.name,
      hint: member.role,
      icon: <Avatar member={member} size="xs" />,
    })),
    {
      value: UNASSIGNED_FILTER,
      label: "Unassigned",
      icon: <UnassignedAvatar size="xs" />,
    },
  ];

  const priorityOptions: DropdownOption<Priority | "all">[] = [
    { value: "all", label: "All priorities" },
    ...PRIORITIES.map((priority) => ({
      value: priority,
      label: PRIORITY_META[priority].label,
      icon: (
        <span className={cn("h-2 w-2 rounded-full", PRIORITY_META[priority].dot)} />
      ),
    })),
  ];

  const statusOptions: DropdownOption<TaskStatus | "all">[] = [
    { value: "all", label: "All statuses" },
    ...COLUMNS.map((column) => ({
      value: column.id,
      label: column.title,
      icon: <span aria-hidden>{column.emoji}</span>,
    })),
  ];

  return (
    <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
      {/* Title row */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-4 pb-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-xs font-bold text-white">
            {PROJECT.code}
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-slate-900 sm:text-lg">
              {PROJECT.name}
            </h1>
            <p className="truncate text-xs text-slate-400">
              {PROJECT.sprint} · {totalCount} cards
              {overdueCount > 0 && (
                <span className="text-rose-600"> · {overdueCount} overdue</span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <button
            type="button"
            onClick={onOpenTeam}
            aria-label="Open team panel"
            className="rounded-full p-0.5 transition-transform duration-150 hover:scale-[1.03]"
          >
            <AvatarStack members={members} max={4} />
          </button>

          <span className="hidden h-6 w-px bg-slate-200 sm:block" />

          <button
            type="button"
            onClick={onNewIdea}
            // The label collapses on small screens, so name the button explicitly.
            aria-label="Quick Brainstorm Idea"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm font-medium text-slate-700 shadow-xs transition-all duration-150 hover:border-slate-300 hover:bg-slate-50 active:scale-[0.98] sm:px-3"
          >
            <Sparkles className="h-4 w-4 text-violet-500" />
            <span className="hidden lg:inline">Quick Brainstorm Idea</span>
            <span className="hidden sm:inline lg:hidden">Idea</span>
          </button>

          <button
            type="button"
            onClick={onNewTask}
            aria-label="New Task"
            className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-2.5 py-2 text-sm font-semibold text-white shadow-sm transition-all duration-150 hover:bg-slate-700 active:scale-[0.98] sm:px-3"
          >
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline">New Task</span>
          </button>
        </div>
      </div>

      {/* Controls row — search gets its own line on phones, filters scroll below */}
      <div className="flex flex-col gap-2 px-4 pb-3 sm:flex-row sm:items-center sm:px-6">
        <div className="relative w-full shrink-0 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            ref={searchRef}
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search by title or tag…"
            aria-label="Search tasks by title or tag"
            className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-8 text-sm text-slate-700 shadow-xs transition-colors duration-150 outline-none placeholder:text-slate-400 focus:border-slate-400"
          />
          {search ? (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-700"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : (
            <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-medium text-slate-400 sm:block">
              /
            </kbd>
          )}
        </div>

        <div className="flex min-w-0 flex-1 items-center gap-2">
          {/* Filters scroll sideways on narrow screens… */}
          <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto pb-0.5 scrollbar-slim">
            <Dropdown
              label="Filter by member"
              prefix="Member:"
              value={memberFilter}
              options={memberOptions}
              onChange={onMemberFilterChange}
              active={memberFilter !== "all"}
              className="w-40 shrink-0"
            />
            <Dropdown
              label="Filter by priority"
              prefix="Priority:"
              value={priorityFilter}
              options={priorityOptions}
              onChange={onPriorityFilterChange}
              active={priorityFilter !== "all"}
              className="w-40 shrink-0"
            />
            <Dropdown
              label="Filter by status"
              prefix="Status:"
              value={statusFilter}
              options={statusOptions}
              onChange={onStatusFilterChange}
              active={statusFilter !== "all"}
              className="w-44 shrink-0"
            />

            {hasActiveFilters && (
              <button
                type="button"
                onClick={onClearFilters}
                className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-2 text-sm font-medium text-slate-500 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 animate-fade-in"
              >
                <X className="h-3.5 w-3.5" />
                Clear
                <span className="hidden tabular-nums text-slate-400 sm:inline">
                  ({resultCount}/{totalCount})
                </span>
              </button>
            )}
          </div>

          {/* …while the view toggle stays pinned to the right. */}
          <div className="flex shrink-0 items-center gap-1 rounded-lg bg-slate-100 p-1">
            <ViewButton
              active={view === "kanban"}
              onClick={() => onViewChange("kanban")}
              icon={<LayoutGrid className="h-4 w-4" />}
              label="Board"
            />
            <ViewButton
              active={view === "table"}
              onClick={() => onViewChange("table")}
              icon={<Table2 className="h-4 w-4" />}
              label="Table"
            />
          </div>
        </div>
      </div>
    </header>
  );
}

function ViewButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={`${label} view`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium transition-all duration-150",
        active
          ? "bg-white text-slate-900 shadow-xs"
          : "text-slate-500 hover:text-slate-900",
      )}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}
