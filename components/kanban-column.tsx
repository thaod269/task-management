"use client";

import { Plus } from "lucide-react";
import { Fragment, type DragEvent } from "react";

import type { ColumnMeta, Task, TeamMember } from "@/lib/types";
import { cn } from "@/lib/utils";

import type { BoardActions } from "./board-actions";
import { IdeaCard } from "./idea-card";
import { TaskCard } from "./task-card";

export interface DropTarget {
  status: ColumnMeta["id"];
  /** Insert before this card, or append when `null`. */
  beforeId: string | null;
}

export function KanbanColumn({
  column,
  tasks,
  membersById,
  today,
  actions,
  draggingId,
  dropTarget,
  onDragStartCard,
  onDragEndCard,
  onDragOverColumn,
  onDragOverCard,
  onDropColumn,
  onDragLeaveColumn,
}: {
  column: ColumnMeta;
  tasks: Task[];
  membersById: Map<string, TeamMember>;
  today: string;
  actions: BoardActions;
  draggingId: string | null;
  dropTarget: DropTarget | null;
  onDragStartCard: (task: Task, event: DragEvent<HTMLElement>) => void;
  onDragEndCard: () => void;
  onDragOverColumn: (event: DragEvent<HTMLElement>) => void;
  onDragOverCard: (
    event: DragEvent<HTMLElement>,
    task: Task,
    nextTaskId: string | null,
  ) => void;
  onDropColumn: (event: DragEvent<HTMLElement>) => void;
  onDragLeaveColumn: (event: DragEvent<HTMLElement>) => void;
}) {
  const isTarget = dropTarget?.status === column.id;
  const isBrainstorm = column.id === "backlog";

  return (
    <section
      aria-label={column.title}
      className="flex h-full w-[85vw] shrink-0 snap-center flex-col sm:w-[19.5rem]"
    >
      <header className="flex items-start justify-between gap-2 px-1 pb-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <span aria-hidden className="text-base leading-none">
              {column.emoji}
            </span>
            <span className="truncate">{column.title}</span>
            <span
              className={cn(
                "rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums",
                column.pill,
              )}
            >
              {tasks.length}
            </span>
          </h2>
          <p className="mt-0.5 truncate text-xs text-slate-400">{column.description}</p>
        </div>

        <button
          type="button"
          onClick={() => actions.onCreate(column.id)}
          aria-label={`Add to ${column.title}`}
          className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors duration-150 hover:bg-white hover:text-slate-900 hover:shadow-xs"
        >
          <Plus className="h-4 w-4" />
        </button>
      </header>

      <div
        onDragOver={onDragOverColumn}
        onDrop={onDropColumn}
        onDragLeave={onDragLeaveColumn}
        className={cn(
          "flex-1 space-y-2.5 overflow-y-auto rounded-xl p-2 transition-colors duration-200 scrollbar-slim",
          isTarget ? "bg-slate-200/60 ring-1 ring-slate-300 ring-inset" : "bg-slate-100/70",
        )}
      >
        {tasks.map((task, index) => {
          const nextTaskId = tasks[index + 1]?.id ?? null;
          const author = task.authorId ? membersById.get(task.authorId) ?? null : null;
          const assignee = task.assigneeId
            ? membersById.get(task.assigneeId) ?? null
            : null;

          return (
            <Fragment key={task.id}>
              {isTarget && dropTarget?.beforeId === task.id && <DropIndicator />}
              <div onDragOver={(event) => onDragOverCard(event, task, nextTaskId)}>
                {task.type === "idea" ? (
                  <IdeaCard
                    task={task}
                    author={author}
                    isDragging={draggingId === task.id}
                    onEdit={() => actions.onEdit(task)}
                    onMove={(status) => actions.onMove(task.id, status)}
                    onDelete={() => actions.onDelete(task.id)}
                    onPromote={() => actions.onPromote(task.id)}
                    onToggleVote={() => actions.onToggleVote(task.id)}
                    onDragStart={(event) => onDragStartCard(task, event)}
                    onDragEnd={onDragEndCard}
                  />
                ) : (
                  <TaskCard
                    task={task}
                    assignee={assignee}
                    today={today}
                    isDragging={draggingId === task.id}
                    onEdit={() => actions.onEdit(task)}
                    onMove={(status) => actions.onMove(task.id, status)}
                    onDelete={() => actions.onDelete(task.id)}
                    onDragStart={(event) => onDragStartCard(task, event)}
                    onDragEnd={onDragEndCard}
                  />
                )}
              </div>
            </Fragment>
          );
        })}

        {isTarget && dropTarget?.beforeId === null && <DropIndicator />}

        {tasks.length === 0 && !isTarget && (
          <button
            type="button"
            onClick={() => actions.onCreate(column.id)}
            className="flex w-full flex-col items-center gap-1 rounded-xl border border-dashed border-slate-300 px-3 py-8 text-center transition-colors duration-150 hover:border-slate-400 hover:bg-white/60"
          >
            <span className="text-sm font-medium text-slate-500">
              {isBrainstorm ? "No ideas yet" : "Nothing here"}
            </span>
            <span className="text-xs text-slate-400">
              {isBrainstorm ? "Capture a raw idea" : "Drop a card or add one"}
            </span>
          </button>
        )}
      </div>
    </section>
  );
}

function DropIndicator() {
  return (
    <div className="h-1 rounded-full bg-slate-900 animate-fade-in" aria-hidden />
  );
}
