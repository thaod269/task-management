"use client";

import { useCallback, useMemo, useReducer, useState } from "react";

import { CURRENT_USER_ID, INITIAL_TASKS, TEAM } from "@/lib/mock-data";
import { boardReducer } from "@/lib/reducer";
import { COLUMNS } from "@/lib/types";
import type { ItemType, Priority, Task, TaskStatus } from "@/lib/types";
import { createId, daysBetween, todayISO } from "@/lib/utils";

import type { BoardActions } from "./board-actions";
import {
  BoardHeader,
  UNASSIGNED_FILTER,
  type BoardView,
} from "./board-header";
import { KanbanView } from "./kanban-view";
import { TableView } from "./table-view";
import { TeamDrawer } from "./team-drawer";
import { TaskModal, type EditorTarget, type TaskDraft } from "./task-modal";

export function Board() {
  const [state, dispatch] = useReducer(boardReducer, { tasks: INITIAL_TASKS });

  const [view, setView] = useState<BoardView>("kanban");
  const [search, setSearch] = useState("");
  const [memberFilter, setMemberFilter] = useState<string>("all");
  const [priorityFilter, setPriorityFilter] = useState<Priority | "all">("all");
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "all">("all");
  const [teamOpen, setTeamOpen] = useState(false);
  const [editor, setEditor] = useState<EditorTarget | null>(null);

  // UTC-based so the server render and client hydration agree exactly.
  const today = useMemo(() => todayISO(), []);

  const membersById = useMemo(
    () => new Map(TEAM.map((member) => [member.id, member])),
    [],
  );

  const hasActiveFilters =
    search.trim() !== "" ||
    memberFilter !== "all" ||
    priorityFilter !== "all" ||
    statusFilter !== "all";

  const visibleTasks = useMemo(() => {
    const query = search.trim().toLowerCase();

    return state.tasks.filter((task) => {
      if (
        query &&
        !task.title.toLowerCase().includes(query) &&
        !task.tags.some((tag) => tag.toLowerCase().includes(query))
      ) {
        return false;
      }

      if (memberFilter !== "all") {
        if (memberFilter === UNASSIGNED_FILTER) {
          if (task.assigneeId !== null) return false;
        } else {
          // Ideas have no assignee, so they match on their author instead —
          // filtering by a teammate still surfaces the ideas they raised.
          const owns =
            task.assigneeId === memberFilter ||
            (task.type === "idea" && task.authorId === memberFilter);
          if (!owns) return false;
        }
      }

      if (priorityFilter !== "all" && task.priority !== priorityFilter) return false;
      if (statusFilter !== "all" && task.status !== statusFilter) return false;

      return true;
    });
  }, [state.tasks, search, memberFilter, priorityFilter, statusFilter]);

  const overdueCount = useMemo(
    () =>
      state.tasks.filter(
        (task) =>
          task.type === "task" &&
          task.status !== "done" &&
          task.dueDate !== null &&
          daysBetween(today, task.dueDate) < 0,
      ).length,
    [state.tasks, today],
  );

  const clearFilters = useCallback(() => {
    setSearch("");
    setMemberFilter("all");
    setPriorityFilter("all");
    setStatusFilter("all");
  }, []);

  const openEditor = useCallback(
    (task: Task | null, presetStatus: TaskStatus, presetType: ItemType) =>
      setEditor({ task, presetStatus, presetType }),
    [],
  );

  const actions: BoardActions = useMemo(
    () => ({
      onEdit: (task) => openEditor(task, task.status, task.type),
      onCreate: (status) =>
        openEditor(null, status, status === "backlog" ? "idea" : "task"),
      onMove: (id, status, beforeId = null) =>
        dispatch({ type: "move", id, status, beforeId }),
      onDelete: (id) => dispatch({ type: "delete", id }),
      onPromote: (id) => dispatch({ type: "promote", id }),
      onToggleVote: (id) => dispatch({ type: "toggleVote", id }),
    }),
    [openEditor],
  );

  const handleSubmit = (draft: TaskDraft) => {
    if (editor?.task) {
      dispatch({ type: "update", id: editor.task.id, patch: draft });
    } else {
      const task: Task = {
        id: createId("t"),
        ...draft,
        authorId: CURRENT_USER_ID,
        votes: 0,
        votedByMe: false,
        createdAt: today,
      };
      dispatch({ type: "create", task });
    }
    setEditor(null);
  };

  const handleDeleteFromModal = (id: string) => {
    dispatch({ type: "delete", id });
    setEditor(null);
  };

  const visibleStatuses: TaskStatus[] =
    statusFilter === "all" ? COLUMNS.map((column) => column.id) : [statusFilter];

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-slate-50">
      <BoardHeader
        members={TEAM}
        view={view}
        onViewChange={setView}
        search={search}
        onSearchChange={setSearch}
        memberFilter={memberFilter}
        onMemberFilterChange={setMemberFilter}
        priorityFilter={priorityFilter}
        onPriorityFilterChange={setPriorityFilter}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearFilters}
        onOpenTeam={() => setTeamOpen(true)}
        onNewTask={() => openEditor(null, "todo", "task")}
        onNewIdea={() => openEditor(null, "backlog", "idea")}
        resultCount={visibleTasks.length}
        totalCount={state.tasks.length}
        overdueCount={overdueCount}
      />

      <main className="min-h-0 flex-1 pt-4">
        {view === "kanban" ? (
          <KanbanView
            tasks={visibleTasks}
            membersById={membersById}
            today={today}
            actions={actions}
            visibleStatuses={visibleStatuses}
            hasActiveFilters={hasActiveFilters}
            onClearFilters={clearFilters}
          />
        ) : (
          <TableView
            tasks={visibleTasks}
            membersById={membersById}
            today={today}
            actions={actions}
            hasActiveFilters={hasActiveFilters}
            onClearFilters={clearFilters}
          />
        )}
      </main>

      <TeamDrawer
        open={teamOpen}
        members={TEAM}
        tasks={state.tasks}
        today={today}
        activeMemberId={memberFilter === "all" ? null : memberFilter}
        onSelectMember={(memberId) => {
          setMemberFilter(memberId ?? "all");
          if (memberId) setTeamOpen(false);
        }}
        onClose={() => setTeamOpen(false)}
      />

      {editor && (
        <TaskModal
          target={editor}
          members={TEAM}
          onClose={() => setEditor(null)}
          onSubmit={handleSubmit}
          onDelete={handleDeleteFromModal}
        />
      )}
    </div>
  );
}
