import type { Task, TaskStatus } from "@/lib/types";

/** Callbacks every view (Kanban / table) needs from the board container. */
export interface BoardActions {
  /** Open the create/edit modal for an existing card. */
  onEdit: (task: Task) => void;
  /** Open the modal pre-filled for a new card in the given column. */
  onCreate: (status: TaskStatus) => void;
  onMove: (id: string, status: TaskStatus, beforeId?: string | null) => void;
  onDelete: (id: string) => void;
  onPromote: (id: string) => void;
  onToggleVote: (id: string) => void;
}
