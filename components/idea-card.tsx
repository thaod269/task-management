"use client";

import { ArrowUpRight, ChevronUp } from "lucide-react";
import type { DragEvent } from "react";

import type { Task, TaskStatus, TeamMember } from "@/lib/types";
import { cn, stripMarkdown } from "@/lib/utils";

import { CardMenu } from "./card-menu";
import { Avatar } from "./ui/avatar";
import { TagChip } from "./ui/badge";

export function IdeaCard({
  task,
  author,
  isDragging,
  onEdit,
  onMove,
  onDelete,
  onPromote,
  onToggleVote,
  onDragStart,
  onDragEnd,
}: {
  task: Task;
  author: TeamMember | null;
  isDragging: boolean;
  onEdit: () => void;
  onMove: (status: TaskStatus) => void;
  onDelete: () => void;
  onPromote: () => void;
  onToggleVote: () => void;
  onDragStart: (event: DragEvent<HTMLElement>) => void;
  onDragEnd: (event: DragEvent<HTMLElement>) => void;
}) {
  const preview = stripMarkdown(task.description);

  return (
    <article
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className={cn(
        "group relative cursor-grab rounded-xl border border-violet-100 bg-white p-3.5 shadow-xs transition-all duration-200",
        "hover:-translate-y-0.5 hover:border-violet-200 hover:shadow-md hover:shadow-violet-900/5",
        "active:cursor-grabbing",
        isDragging && "rotate-1 opacity-40",
      )}
    >
      <div className="flex gap-3">
        {/* Upvote counter */}
        <button
          type="button"
          onClick={onToggleVote}
          aria-pressed={task.votedByMe}
          aria-label={`${task.votedByMe ? "Remove your upvote from" : "Upvote"} ${task.title}`}
          className={cn(
            "relative z-10 flex h-12 w-9 shrink-0 flex-col items-center justify-center gap-0.5 rounded-lg border transition-all duration-150",
            task.votedByMe
              ? "border-violet-200 bg-violet-50 text-violet-700"
              : "border-slate-200 bg-white text-slate-500 hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700",
          )}
        >
          <ChevronUp
            key={task.votes}
            className={cn("h-3.5 w-3.5", task.votedByMe && "animate-pop")}
            strokeWidth={2.5}
          />
          <span className="text-xs font-semibold tabular-nums">{task.votes}</span>
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <button
              type="button"
              onClick={onEdit}
              className="min-w-0 flex-1 text-left after:absolute after:inset-0 after:rounded-xl after:content-['']"
            >
              <h3 className="line-clamp-2 text-sm font-semibold text-slate-900">
                {task.title}
              </h3>
            </button>
            <CardMenu
              task={task}
              onEdit={onEdit}
              onMove={onMove}
              onDelete={onDelete}
              onPromote={onPromote}
            />
          </div>

          {preview && (
            <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-500">
              {preview}
            </p>
          )}

          {task.tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {task.tags.map((tag) => (
                <TagChip key={tag} tag={tag} />
              ))}
            </div>
          )}
        </div>
      </div>

      <footer className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-3">
        <span className="flex min-w-0 items-center gap-1.5">
          {author && <Avatar member={author} size="sm" />}
          <span className="truncate text-xs text-slate-500">
            {author ? author.name : "Unknown"}
          </span>
        </span>

        <button
          type="button"
          onClick={onPromote}
          className={cn(
            "relative z-10 inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold transition-all duration-150",
            "bg-slate-900 text-white hover:bg-slate-700 active:scale-[0.97]",
          )}
        >
          Promote to task
          <ArrowUpRight className="h-3 w-3" />
        </button>
      </footer>
    </article>
  );
}
