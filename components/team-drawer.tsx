"use client";

import { AlertCircle, Check, Filter, Users, X } from "lucide-react";
import { useEffect, useMemo } from "react";

import { COLUMNS } from "@/lib/types";
import type { Task, TeamMember } from "@/lib/types";
import { cn, daysBetween } from "@/lib/utils";

import { Avatar, UnassignedAvatar } from "./ui/avatar";

interface MemberStats {
  active: number;
  done: number;
  overdue: number;
  byStatus: Record<string, number>;
}

/** Statuses shown in the per-member workload breakdown. */
const WORKLOAD_STATUSES = COLUMNS.filter((column) => column.id !== "done");

export function TeamDrawer({
  open,
  members,
  tasks,
  today,
  activeMemberId,
  onSelectMember,
  onClose,
}: {
  open: boolean;
  members: TeamMember[];
  tasks: Task[];
  today: string;
  activeMemberId: string | null;
  onSelectMember: (memberId: string | null) => void;
  onClose: () => void;
}) {
  const stats = useMemo(() => {
    const empty = (): MemberStats => ({
      active: 0,
      done: 0,
      overdue: 0,
      byStatus: {},
    });

    const map = new Map<string, MemberStats>();
    members.forEach((member) => map.set(member.id, empty()));
    map.set("unassigned", empty());

    for (const task of tasks) {
      if (task.type !== "task") continue;
      const entry = map.get(task.assigneeId ?? "unassigned");
      if (!entry) continue;

      if (task.status === "done") {
        entry.done += 1;
        continue;
      }

      entry.active += 1;
      entry.byStatus[task.status] = (entry.byStatus[task.status] ?? 0) + 1;
      if (task.dueDate && daysBetween(today, task.dueDate) < 0) entry.overdue += 1;
    }

    return map;
  }, [members, tasks, today]);

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const unassigned = stats.get("unassigned");
  const totalActive = tasks.filter(
    (task) => task.type === "task" && task.status !== "done",
  ).length;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close team panel"
        onClick={onClose}
        className="absolute inset-0 bg-slate-900/30 backdrop-blur-[2px] animate-fade-in"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Team"
        className="relative flex h-full w-full max-w-sm flex-col bg-white shadow-2xl shadow-slate-900/20 animate-slide-in-right"
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
              <Users className="h-4 w-4 text-slate-400" />
              Team
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">
              {members.length} members · {totalActive} active tasks
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close team panel"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-4.5 w-4.5" />
          </button>
        </header>

        <div className="flex-1 space-y-2 overflow-y-auto px-3 py-3 scrollbar-slim">
          <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Filter the board by member
          </p>

          {members.map((member) => {
            const entry = stats.get(member.id)!;
            const isActive = activeMemberId === member.id;

            return (
              <button
                key={member.id}
                type="button"
                aria-pressed={isActive}
                onClick={() => onSelectMember(isActive ? null : member.id)}
                className={cn(
                  "flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-all duration-150",
                  isActive
                    ? "border-slate-300 bg-slate-50 shadow-xs"
                    : "border-transparent hover:border-slate-200 hover:bg-slate-50",
                )}
              >
                <Avatar member={member} size="lg" />

                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-semibold text-slate-900">
                      {member.name}
                    </span>
                    {isActive && (
                      <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-slate-900 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                        <Check className="h-2.5 w-2.5" strokeWidth={3} />
                        Filtering
                      </span>
                    )}
                  </div>
                  <p className="truncate text-xs text-slate-500">{member.role}</p>

                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-700">
                      <span className="tabular-nums">{entry.active}</span> active
                    </span>
                    <span className="text-[11px] text-slate-400">
                      {entry.done} done
                    </span>
                    {entry.overdue > 0 && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-rose-50 px-1.5 py-0.5 text-[11px] font-medium text-rose-700 ring-1 ring-rose-200 ring-inset">
                        <AlertCircle className="h-3 w-3" />
                        {entry.overdue} overdue
                      </span>
                    )}
                  </div>

                  {entry.active > 0 && (
                    <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-slate-100">
                      {WORKLOAD_STATUSES.map((column) => {
                        const count = entry.byStatus[column.id] ?? 0;
                        if (count === 0) return null;
                        return (
                          <span
                            key={column.id}
                            title={`${count} in ${column.title}`}
                            style={{ width: `${(count / entry.active) * 100}%` }}
                            className={cn("h-full", column.dot)}
                          />
                        );
                      })}
                    </div>
                  )}
                </div>
              </button>
            );
          })}

          {unassigned && unassigned.active > 0 && (
            <div className="flex items-center gap-3 rounded-xl border border-dashed border-slate-200 p-3">
              <UnassignedAvatar size="lg" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-700">Unassigned</p>
                <p className="text-xs text-slate-400">
                  {unassigned.active} task{unassigned.active === 1 ? "" : "s"} with no
                  owner
                </p>
              </div>
            </div>
          )}
        </div>

        {activeMemberId && (
          <footer className="border-t border-slate-200 bg-slate-50/70 px-5 py-3">
            <button
              type="button"
              onClick={() => onSelectMember(null)}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-xs transition-colors duration-150 hover:bg-slate-50"
            >
              <Filter className="h-3.5 w-3.5" />
              Clear member filter
            </button>
          </footer>
        )}
      </aside>
    </div>
  );
}
