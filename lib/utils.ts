import type { Subtask } from "./types";

/** Tiny `clsx` replacement so the project stays dependency-free. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/* -------------------------------------------------------------------------- */
/* Dates                                                                      */
/* -------------------------------------------------------------------------- */
/*
 * All dates are handled as `yyyy-mm-dd` strings in UTC. Doing the arithmetic
 * with `Date.UTC` (never local getters) keeps the server render and the client
 * hydration byte-identical, regardless of the viewer's timezone.
 */

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const DAY_MS = 86_400_000;

/** Today as `yyyy-mm-dd`, in UTC. */
export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Shift an ISO date by a number of days. */
export function addDays(iso: string, days: number): string {
  return new Date(toUTC(iso) + days * DAY_MS).toISOString().slice(0, 10);
}

function toUTC(iso: string): number {
  const [year, month, day] = iso.split("-").map(Number);
  return Date.UTC(year, month - 1, day);
}

/** Whole days from `from` to `to` (negative when `to` is in the past). */
export function daysBetween(from: string, to: string): number {
  return Math.round((toUTC(to) - toUTC(from)) / DAY_MS);
}

/** `2026-08-16` -> `Aug 16`. Adds the year when it differs from today's. */
export function formatDate(iso: string, today = ""): string {
  const [year, month, day] = iso.split("-").map(Number);
  const label = `${MONTHS[month - 1]} ${day}`;
  return today && !today.startsWith(String(year)) ? `${label}, ${year}` : label;
}

export type DueTone = "overdue" | "today" | "soon" | "normal";

export interface DueMeta {
  label: string;
  tone: DueTone;
  /** Screen-reader / tooltip friendly absolute date. */
  absolute: string;
}

/** Human-friendly due-date label plus a tone used for colouring. */
export function dueMeta(due: string, today: string): DueMeta {
  const absolute = formatDate(due, today);
  const diff = daysBetween(today, due);

  if (diff < 0) {
    const days = Math.abs(diff);
    return {
      label: days === 1 ? "1 day overdue" : `${days} days overdue`,
      tone: "overdue",
      absolute,
    };
  }
  if (diff === 0) return { label: "Due today", tone: "today", absolute };
  if (diff === 1) return { label: "Due tomorrow", tone: "soon", absolute };
  if (diff <= 3) return { label: `Due in ${diff} days`, tone: "soon", absolute };
  return { label: absolute, tone: "normal", absolute };
}

export const DUE_TONE_CLASS: Record<DueTone, string> = {
  overdue: "bg-rose-50 text-rose-700 ring-rose-200",
  today: "bg-amber-50 text-amber-700 ring-amber-200",
  soon: "bg-slate-100 text-slate-700 ring-slate-200",
  normal: "bg-slate-50 text-slate-500 ring-slate-200",
};

/* -------------------------------------------------------------------------- */
/* Misc                                                                       */
/* -------------------------------------------------------------------------- */

export interface Progress {
  done: number;
  total: number;
  percent: number;
}

export function subtaskProgress(subtasks: Subtask[]): Progress {
  const total = subtasks.length;
  const done = subtasks.filter((subtask) => subtask.done).length;
  return { done, total, percent: total === 0 ? 0 : Math.round((done / total) * 100) };
}

/** Flattens Markdown into a single line for card previews and search. */
export function stripMarkdown(source: string): string {
  return source
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^\s{0,3}(#{1,6}|>)\s*/gm, "")
    .replace(/^\s*([-*]|\d+\.)\s+/gm, "")
    .replace(/(\*\*|__|\*|_)/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

let idCounter = 0;

/**
 * Monotonic id generator. Only ever called from event handlers (never during
 * render), so it can't desynchronise the server and client markup.
 */
export function createId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-${idCounter.toString(36)}${Date.now().toString(36)}`;
}

/** Build initials from a display name, e.g. "Maya Chen" -> "MC". */
export function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
}
