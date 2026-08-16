import type { Task, TaskStatus } from "./types";

export interface BoardState {
  /** Array order *is* the board order — drag-and-drop reorders this list. */
  tasks: Task[];
}

export type BoardAction =
  | { type: "create"; task: Task }
  | { type: "update"; id: string; patch: Partial<Task> }
  | { type: "delete"; id: string }
  /** Move to a status, optionally inserting before `beforeId` for reordering. */
  | { type: "move"; id: string; status: TaskStatus; beforeId?: string | null }
  | { type: "toggleSubtask"; taskId: string; subtaskId: string }
  | { type: "toggleVote"; id: string }
  | { type: "promote"; id: string };

export function boardReducer(state: BoardState, action: BoardAction): BoardState {
  switch (action.type) {
    case "create":
      return { ...state, tasks: [action.task, ...state.tasks] };

    case "update":
      return {
        ...state,
        tasks: state.tasks.map((task) =>
          task.id === action.id ? { ...task, ...action.patch } : task,
        ),
      };

    case "delete":
      return { ...state, tasks: state.tasks.filter((task) => task.id !== action.id) };

    case "move": {
      const moving = state.tasks.find((task) => task.id === action.id);
      if (!moving) return state;
      // No-op when dropping a card onto itself.
      if (moving.status === action.status && action.beforeId === action.id) return state;

      const next = withStatus(moving, action.status);
      const rest = state.tasks.filter((task) => task.id !== action.id);
      const index = action.beforeId
        ? rest.findIndex((task) => task.id === action.beforeId)
        : -1;

      if (index === -1) rest.push(next);
      else rest.splice(index, 0, next);

      return { ...state, tasks: rest };
    }

    case "toggleSubtask":
      return {
        ...state,
        tasks: state.tasks.map((task) =>
          task.id === action.taskId
            ? {
                ...task,
                subtasks: task.subtasks.map((subtask) =>
                  subtask.id === action.subtaskId
                    ? { ...subtask, done: !subtask.done }
                    : subtask,
                ),
              }
            : task,
        ),
      };

    case "toggleVote":
      return {
        ...state,
        tasks: state.tasks.map((task) =>
          task.id === action.id
            ? {
                ...task,
                votes: task.votes + (task.votedByMe ? -1 : 1),
                votedByMe: !task.votedByMe,
              }
            : task,
        ),
      };

    case "promote":
      return {
        ...state,
        tasks: state.tasks.map((task) =>
          task.id === action.id ? { ...task, type: "task", status: "todo" } : task,
        ),
      };

    default:
      return state;
  }
}

/**
 * An idea that leaves the backlog graduates into a real task — dragging it out
 * of `💡 Brainstorm` is the same gesture as pressing "Promote to task".
 */
function withStatus(task: Task, status: TaskStatus): Task {
  if (task.type === "idea" && status !== "backlog") {
    return { ...task, status, type: "task" };
  }
  return { ...task, status };
}
