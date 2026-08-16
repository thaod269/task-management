"use client";

import { ArrowUpRight, MoreHorizontal, Pencil, Trash2 } from "lucide-react";

import { COLUMNS } from "@/lib/types";
import type { Task, TaskStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

import {
  MenuItem,
  MenuLabel,
  MenuSeparator,
  PopoverMenu,
} from "./ui/popover-menu";

/**
 * Per-card actions. Doubles as the touch/keyboard accessible alternative to
 * drag-and-drop: every column is reachable from the "Move to" list.
 */
export function CardMenu({
  task,
  onEdit,
  onMove,
  onDelete,
  onPromote,
}: {
  task: Task;
  onEdit: () => void;
  onMove: (status: TaskStatus) => void;
  onDelete: () => void;
  onPromote?: () => void;
}) {
  return (
    <PopoverMenu
      label={`Actions for ${task.title}`}
      trigger={({ open, toggle }) => (
        <button
          type="button"
          onClick={toggle}
          aria-label={`Actions for ${task.title}`}
          className={cn(
            "relative z-10 flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 transition-all duration-150",
            "hover:bg-slate-100 hover:text-slate-700",
            // Revealed on hover, but always visible while focused or open.
            open
              ? "bg-slate-100 text-slate-700 opacity-100"
              : "opacity-0 focus-visible:opacity-100 group-hover:opacity-100",
          )}
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      )}
    >
      {(close) => (
        <>
          <MenuLabel>Move to</MenuLabel>
          {COLUMNS.map((column) => (
            <MenuItem
              key={column.id}
              selected={column.id === task.status}
              icon={<span aria-hidden>{column.emoji}</span>}
              onClick={() => {
                onMove(column.id);
                close();
              }}
            >
              {column.title}
            </MenuItem>
          ))}

          <MenuSeparator />

          {onPromote && (
            <MenuItem
              icon={<ArrowUpRight className="h-4 w-4 text-slate-400" />}
              onClick={() => {
                onPromote();
                close();
              }}
            >
              Promote to task
            </MenuItem>
          )}
          <MenuItem
            icon={<Pencil className="h-4 w-4 text-slate-400" />}
            onClick={() => {
              onEdit();
              close();
            }}
          >
            Edit details
          </MenuItem>
          <MenuItem
            tone="danger"
            icon={<Trash2 className="h-4 w-4" />}
            onClick={() => {
              onDelete();
              close();
            }}
          >
            Delete
          </MenuItem>
        </>
      )}
    </PopoverMenu>
  );
}
