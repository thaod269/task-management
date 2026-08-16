"use client";

import { useState, type DragEvent } from "react";

import { COLUMNS } from "@/lib/types";
import type { ColumnMeta, Task, TaskStatus, TeamMember } from "@/lib/types";

import type { BoardActions } from "./board-actions";
import { KanbanColumn, type DropTarget } from "./kanban-column";
import { EmptyResults } from "./empty-results";

export function KanbanView({
  tasks,
  membersById,
  today,
  actions,
  visibleStatuses,
  hasActiveFilters,
  onClearFilters,
}: {
  tasks: Task[];
  membersById: Map<string, TeamMember>;
  today: string;
  actions: BoardActions;
  visibleStatuses: TaskStatus[];
  hasActiveFilters: boolean;
  onClearFilters: () => void;
}) {
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null);

  const columns: ColumnMeta[] = COLUMNS.filter((column) =>
    visibleStatuses.includes(column.id),
  );

  const handleDragStartCard = (task: Task, event: DragEvent<HTMLElement>) => {
    setDraggingId(task.id);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", task.id);
  };

  const handleDragEndCard = () => {
    setDraggingId(null);
    setDropTarget(null);
  };

  /** Fires on the column background — append to the end of that column. */
  const handleDragOverColumn = (event: DragEvent<HTMLElement>, status: TaskStatus) => {
    if (!draggingId) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    setDropTarget({ status, beforeId: null });
  };

  /**
   * Fires on a card wrapper. Stops propagation so the column handler above
   * can't overwrite the precise insertion point with "append".
   */
  const handleDragOverCard = (
    event: DragEvent<HTMLElement>,
    task: Task,
    nextTaskId: string | null,
  ) => {
    if (!draggingId) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "move";

    const rect = event.currentTarget.getBoundingClientRect();
    const isTopHalf = event.clientY < rect.top + rect.height / 2;
    setDropTarget({ status: task.status, beforeId: isTopHalf ? task.id : nextTaskId });
  };

  const handleDragLeaveColumn = (event: DragEvent<HTMLElement>) => {
    const next = event.relatedTarget as Node | null;
    if (next && event.currentTarget.contains(next)) return;
    setDropTarget((current) => (current ? null : current));
  };

  const handleDropColumn = (event: DragEvent<HTMLElement>, status: TaskStatus) => {
    event.preventDefault();
    const id = draggingId ?? event.dataTransfer.getData("text/plain");
    if (id) {
      const beforeId = dropTarget?.status === status ? dropTarget.beforeId : null;
      actions.onMove(id, status, beforeId);
    }
    setDraggingId(null);
    setDropTarget(null);
  };

  if (tasks.length === 0 && hasActiveFilters) {
    return <EmptyResults onClearFilters={onClearFilters} />;
  }

  return (
    <div className="flex h-full snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-4 sm:snap-none sm:px-6 scrollbar-slim">
      {columns.map((column) => (
        <KanbanColumn
          key={column.id}
          column={column}
          tasks={tasks.filter((task) => task.status === column.id)}
          membersById={membersById}
          today={today}
          actions={actions}
          draggingId={draggingId}
          dropTarget={dropTarget}
          onDragStartCard={handleDragStartCard}
          onDragEndCard={handleDragEndCard}
          onDragOverColumn={(event) => handleDragOverColumn(event, column.id)}
          onDragOverCard={handleDragOverCard}
          onDropColumn={(event) => handleDropColumn(event, column.id)}
          onDragLeaveColumn={handleDragLeaveColumn}
        />
      ))}
    </div>
  );
}
