import type { Task, TeamMember } from "./types";
import { addDays, todayISO } from "./utils";

export const PROJECT = {
  name: "Atlas Design System",
  code: "ATL",
  sprint: "Sprint 24 · Q3 Delivery",
};

export const TEAM: TeamMember[] = [
  {
    id: "m1",
    name: "Maya Chen",
    role: "Product Designer",
    initials: "MC",
    accent: "bg-violet-100 text-violet-700 ring-violet-200",
  },
  {
    id: "m2",
    name: "Diego Ramos",
    role: "Frontend Engineer",
    initials: "DR",
    accent: "bg-sky-100 text-sky-700 ring-sky-200",
  },
  {
    id: "m3",
    name: "Priya Nair",
    role: "Backend Engineer",
    initials: "PN",
    accent: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  },
  {
    id: "m4",
    name: "Sam Okafor",
    role: "QA & Release",
    initials: "SO",
    accent: "bg-amber-100 text-amber-700 ring-amber-200",
  },
  {
    id: "m5",
    name: "Lena Fischer",
    role: "Product Manager",
    initials: "LF",
    accent: "bg-rose-100 text-rose-700 ring-rose-200",
  },
];

/** The signed-in user — used for authoring new ideas and vote attribution. */
export const CURRENT_USER_ID = "m5";

// Anchor every mock date to "today" in UTC so the board never looks stale and
// both renders (server + client) agree on the exact same strings.
const TODAY = todayISO();
const day = (offset: number) => addDays(TODAY, offset);

export const INITIAL_TASKS: Task[] = [
  /* ------------------------------ Backlog ------------------------------- */
  {
    id: "t1",
    type: "idea",
    title: "Command palette for the whole app",
    description:
      "What if `⌘K` opened a **global command palette**?\n\nJump to any board, task or teammate without touching the mouse. Linear and Raycast set the bar here — we could ship a v1 with just navigation and task creation.",
    status: "backlog",
    priority: "medium",
    assigneeId: null,
    authorId: "m2",
    dueDate: null,
    tags: ["dx", "navigation"],
    subtasks: [],
    votes: 12,
    votedByMe: true,
    createdAt: day(-14),
  },
  {
    id: "t2",
    type: "idea",
    title: "Auto-generate release notes from merged PRs",
    description:
      "Scrape merged pull requests each Friday and draft the changelog automatically.\n\n- Groups by label (`feat`, `fix`, `chore`)\n- Leaves a draft in the release channel for a human to approve",
    status: "backlog",
    priority: "low",
    assigneeId: null,
    authorId: "m4",
    dueDate: null,
    tags: ["automation", "release"],
    subtasks: [],
    votes: 8,
    votedByMe: false,
    createdAt: day(-11),
  },
  {
    id: "t3",
    type: "idea",
    title: "Offline-first mode with background sync",
    description:
      "Field teams keep losing edits on flaky connections. A service worker plus an outbox queue would let the board keep working offline and replay writes once the connection returns.",
    status: "backlog",
    priority: "high",
    assigneeId: null,
    authorId: "m3",
    dueDate: null,
    tags: ["reliability", "mobile"],
    subtasks: [],
    votes: 5,
    votedByMe: false,
    createdAt: day(-6),
  },
  {
    id: "t4",
    type: "idea",
    title: "Weekly digest email for stakeholders",
    description:
      "A Monday-morning summary of everything that shipped, what slipped, and what is blocked — so leadership stops asking in Slack.",
    status: "backlog",
    priority: "low",
    assigneeId: null,
    authorId: "m5",
    dueDate: null,
    tags: ["growth", "email"],
    subtasks: [],
    votes: 3,
    votedByMe: false,
    createdAt: day(-3),
  },

  /* -------------------------------- To Do -------------------------------- */
  {
    id: "t5",
    type: "task",
    title: "Design tokens for dark mode",
    description:
      "Extend the palette with a **dark surface ramp** and audit every component for contrast.\n\n> Target: WCAG AA on all text and interactive states.",
    status: "todo",
    priority: "high",
    assigneeId: "m1",
    authorId: "m1",
    dueDate: day(4),
    tags: ["design-system", "accessibility"],
    subtasks: [
      { id: "s1", title: "Audit current colour usage", done: true },
      { id: "s2", title: "Draft dark surface ramp", done: false },
      { id: "s3", title: "Contrast-check interactive states", done: false },
      { id: "s4", title: "Publish tokens to Figma", done: false },
    ],
    votes: 0,
    votedByMe: false,
    createdAt: day(-9),
  },
  {
    id: "t6",
    type: "task",
    title: "Rate limiting on the public API",
    description:
      "Add a sliding-window limiter in front of `/v1/*`.\n\n- `429` with `Retry-After` on breach\n- Per-token buckets, 1000 req/min default\n- Metrics exported to Grafana",
    status: "todo",
    priority: "urgent",
    assigneeId: "m3",
    authorId: "m5",
    dueDate: day(-1),
    tags: ["api", "security"],
    subtasks: [
      { id: "s5", title: "Pick limiter algorithm", done: true },
      { id: "s6", title: "Implement Redis buckets", done: false },
      { id: "s7", title: "Load-test at 5k rps", done: false },
    ],
    votes: 0,
    votedByMe: false,
    createdAt: day(-8),
  },
  {
    id: "t7",
    type: "task",
    title: "Empty states for every board view",
    description:
      "Kanban, table and the team drawer all render blank rectangles when filtered to nothing. Add illustrated empty states with a clear next action.",
    status: "todo",
    priority: "medium",
    assigneeId: "m1",
    authorId: "m2",
    dueDate: day(9),
    tags: ["ui", "polish"],
    subtasks: [
      { id: "s8", title: "Write copy for each state", done: false },
      { id: "s9", title: "Build shared EmptyState component", done: false },
    ],
    votes: 0,
    votedByMe: false,
    createdAt: day(-5),
  },

  /* ----------------------------- In progress ----------------------------- */
  {
    id: "t8",
    type: "task",
    title: "Drag-and-drop reordering on the Kanban board",
    description:
      "Cards should move **between columns and within a column**, with a visible drop indicator.\n\nKeyboard and touch users get an equivalent status dropdown on every card.",
    status: "in-progress",
    priority: "high",
    assigneeId: "m2",
    authorId: "m1",
    dueDate: day(2),
    tags: ["kanban", "interaction"],
    subtasks: [
      { id: "s10", title: "Drag source + drop targets", done: true },
      { id: "s11", title: "Insertion indicator", done: true },
      { id: "s12", title: "Status dropdown fallback", done: true },
      { id: "s13", title: "Touch support", done: false },
      { id: "s14", title: "Announce moves to screen readers", done: false },
    ],
    votes: 0,
    votedByMe: false,
    createdAt: day(-7),
  },
  {
    id: "t9",
    type: "task",
    title: "Migrate search to Postgres full-text",
    description:
      "The `ILIKE` scan is timing out past 50k rows. Move to `tsvector` with a GIN index and rank results by recency.",
    status: "in-progress",
    priority: "urgent",
    assigneeId: "m3",
    authorId: "m3",
    dueDate: day(-3),
    tags: ["performance", "database"],
    subtasks: [
      { id: "s15", title: "Add tsvector column + trigger", done: true },
      { id: "s16", title: "Backfill existing rows", done: true },
      { id: "s17", title: "Swap query layer", done: false },
      { id: "s18", title: "Benchmark against prod snapshot", done: false },
    ],
    votes: 0,
    votedByMe: false,
    createdAt: day(-12),
  },
  {
    id: "t10",
    type: "task",
    title: "Onboarding checklist for new workspaces",
    description:
      "Guide a brand-new workspace through inviting a teammate, creating a board and shipping a first task.",
    status: "in-progress",
    priority: "medium",
    assigneeId: "m5",
    authorId: "m5",
    dueDate: day(6),
    tags: ["onboarding", "growth"],
    subtasks: [
      { id: "s19", title: "Define the 4 checklist steps", done: true },
      { id: "s20", title: "Persist completion per workspace", done: false },
    ],
    votes: 0,
    votedByMe: false,
    createdAt: day(-4),
  },

  /* -------------------------------- Review ------------------------------- */
  {
    id: "t11",
    type: "task",
    title: "Keyboard navigation for the task modal",
    description:
      "Focus trap, `Esc` to dismiss, and `⌘↵` to save. Verified with VoiceOver and NVDA.",
    status: "review",
    priority: "medium",
    assigneeId: "m4",
    authorId: "m2",
    dueDate: day(1),
    tags: ["accessibility", "ui"],
    subtasks: [
      { id: "s21", title: "Trap focus inside the dialog", done: true },
      { id: "s22", title: "Restore focus on close", done: true },
      { id: "s23", title: "Screen-reader pass", done: false },
    ],
    votes: 0,
    votedByMe: false,
    createdAt: day(-10),
  },
  {
    id: "t12",
    type: "task",
    title: "Fix avatar stack overflow on narrow screens",
    description:
      "Above six members the stack pushes the search bar off-screen at 360px. Collapse to `+N` past four avatars.",
    status: "review",
    priority: "low",
    assigneeId: "m2",
    authorId: "m4",
    dueDate: day(-2),
    tags: ["bug", "responsive"],
    subtasks: [
      { id: "s24", title: "Reproduce at 360px", done: true },
      { id: "s25", title: "Add overflow counter", done: true },
    ],
    votes: 0,
    votedByMe: false,
    createdAt: day(-13),
  },

  /* --------------------------------- Done -------------------------------- */
  {
    id: "t13",
    type: "task",
    title: "Ship board filters (member, priority, status)",
    description:
      "Filters compose with the global search and reset in a single click.",
    status: "done",
    priority: "high",
    assigneeId: "m2",
    authorId: "m5",
    dueDate: day(-5),
    tags: ["filters", "ui"],
    subtasks: [
      { id: "s26", title: "Filter dropdown primitive", done: true },
      { id: "s27", title: "Wire to board state", done: true },
      { id: "s28", title: "Clear-all affordance", done: true },
    ],
    votes: 0,
    votedByMe: false,
    createdAt: day(-18),
  },
  {
    id: "t14",
    type: "task",
    title: "Subtask checklists with progress bars",
    description:
      "Every task card now shows an `x/y done` progress bar that updates as items are ticked off.",
    status: "done",
    priority: "medium",
    assigneeId: "m1",
    authorId: "m1",
    dueDate: day(-8),
    tags: ["checklist", "ui"],
    subtasks: [
      { id: "s29", title: "Dynamic add/remove rows", done: true },
      { id: "s30", title: "Progress bar on cards", done: true },
    ],
    votes: 0,
    votedByMe: false,
    createdAt: day(-21),
  },
  {
    id: "t15",
    type: "task",
    title: "Nightly database backups to cold storage",
    description:
      "Encrypted `pg_dump` at 02:00 UTC, 30-day retention, restore drill documented in the runbook.",
    status: "done",
    priority: "urgent",
    assigneeId: "m3",
    authorId: "m3",
    dueDate: day(-11),
    tags: ["infra", "security"],
    subtasks: [
      { id: "s31", title: "Automate dump + upload", done: true },
      { id: "s32", title: "Verify restore from snapshot", done: true },
      { id: "s33", title: "Document the runbook", done: true },
    ],
    votes: 0,
    votedByMe: false,
    createdAt: day(-24),
  },
];
