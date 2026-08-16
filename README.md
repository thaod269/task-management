# Atlas Board — Task Management SPA

A responsive, single-page task board built with **Next.js (App Router)**, **TypeScript**, **Tailwind CSS v4** and **lucide-react**. All state lives in the browser via `useReducer` over pre-populated mock data — there is no backend to run.

```bash
npm install
npm run dev      # http://localhost:3000
```

`npm run build` writes a fully static site to `out/`; `npm run typecheck` runs `tsc --noEmit`.

## Deploying to Firebase Hosting

The app is entirely client-side — no server components fetching data, no route handlers, no middleware — so `next.config.mjs` sets `output: "export"` and the build emits plain HTML/JS that any static host can serve. Firebase Hosting (your `*.web.app` domain) is the cheapest and simplest fit on Google Cloud; its free tier covers a board like this comfortably.

```bash
npm install -g firebase-tools     # once
firebase login                    # once
firebase use --add                # pick your project; writes .firebaserc

npm run deploy                    # next build && firebase deploy --only hosting
```

That publishes to `https://<project-id>.web.app`. `npm run preview` serves the built site through the Firebase emulator first, so you can check the real `firebase.json` rules (clean URLs, cache headers) before going live.

`firebase.json` is already configured: it serves `out/`, caches the content-hashed `/_next/static/**` bundles for a year as `immutable`, and keeps HTML on `must-revalidate` so a deploy shows up immediately.

**If you later add a backend** — API routes, server-side rendering, or real data instead of the mock store — static export no longer applies. At that point switch to **Firebase App Hosting** or **Cloud Run**, both of which run the Next.js server; remove `output: "export"` from `next.config.mjs` when you do.

## Features

### Dashboard header
- Project title, sprint line and a live card/overdue count.
- Team avatar stack — click it to open the team drawer.
- Global search across **titles and tags** (press <kbd>/</kbd> to focus it).
- Filter dropdowns for **member**, **priority** and **status**, plus a one-click *Clear* that shows how many cards survived the filters.
- **New Task** and **Quick Brainstorm Idea** actions.

### Multi-view board
Toggle between **Board** and **Table**.

| Column | Purpose |
| --- | --- |
| 💡 Brainstorm / Backlog | Raw ideas — voting, author, tags |
| 📋 To Do | Scoped and ready to pick up |
| ⚙️ In Progress | Actively being worked on |
| 🧪 Code Review / Testing | Awaiting review or QA |
| 🚀 Deployed / Done | Shipped to production |

**Drag and drop** is implemented with native HTML5 drag events — no DnD library. Cards move between columns *and* reorder within a column, with a drop indicator showing the exact insertion point (drop on a card's top half to go before it, bottom half to go after). Every card also carries a **⋯ → Move to** menu, and the table view has an inline status dropdown, so touch and keyboard users get the same reach as a mouse.

Filtering by status collapses the board to just that column.

### Cards
- **Idea cards** — upvote counter (toggles your vote), author badge, tag chips and a one-click **Promote to task**. Dragging an idea out of the backlog promotes it automatically, since ideas live only in the Brainstorm column.
- **Task cards** — priority chip, assignee avatar + name, due-date indicator that turns amber today and rose when overdue, a subtask progress bar (`3/5 done`) that turns green at 100%, and tag chips.

### Create / edit modal
Title, Markdown description with a live **Preview** toggle, Idea/Task switch, assignee picker (avatar + role), status, priority, due date, tag editor and a dynamic checklist. <kbd>Esc</kbd> closes, <kbd>⌘</kbd>/<kbd>Ctrl</kbd> + <kbd>↵</kbd> saves, focus is trapped inside the dialog and returned to the invoking element on close. On phones it becomes a bottom sheet.

### Team drawer
Every member with their role, **active task count**, completed count, an overdue badge, and a workload bar broken down by status. Clicking a member filters the board (ideas match on their author, so a teammate's brainstorms stay visible).

## Architecture

```
app/
  layout.tsx          Root layout + metadata
  page.tsx            Server component; renders <Board />
  globals.css         Tailwind v4 theme, keyframes, reduced-motion guard
components/
  board.tsx           State container: useReducer + filters + modal wiring
  board-header.tsx    Title, search, filters, view toggle, actions
  kanban-view.tsx     Drag state and drop-target resolution
  kanban-column.tsx   One column + its drop indicator
  task-card.tsx       Active task card
  idea-card.tsx       Lightweight brainstorm card
  table-view.tsx      Sortable table with inline status changes
  task-modal.tsx      Create/edit dialog
  team-drawer.tsx     Team panel with per-member workload
  card-menu.tsx       Shared ⋯ menu (move / edit / promote / delete)
  ui/                 avatar, badge, dropdown, popover-menu, markdown
lib/
  types.ts            Domain types + column/priority metadata
  mock-data.ts        5 team members, 15 seeded cards
  reducer.ts          All board mutations
  utils.ts            cn(), UTC date helpers, progress, markdown stripping
```

### Notes on a few decisions

**No date drift between server and client.** Dates are `yyyy-mm-dd` strings and every calculation goes through `Date.UTC`, never local getters. Mock due dates are anchored to today, so the board never looks stale and the server render matches hydration exactly — the app produces no hydration warnings.

**Popovers are portalled.** The board scrolls horizontally and columns scroll vertically, which would clip an absolutely positioned menu. Every dropdown and card menu renders into `document.body` at a fixed position derived from its trigger, flipping upward near the bottom of the viewport and clamping to the edges. They follow their trigger while the page scrolls and close only once it leaves the viewport — closing on any scroll would dismiss a menu the moment the browser scrolled its trigger into view.

**Escape closes one layer at a time.** Popovers listen in the capture phase and stop propagation, so pressing <kbd>Esc</kbd> with a dropdown open inside the modal closes the dropdown, not the dialog.

**Markdown is rendered, not injected.** `components/ui/markdown.tsx` is a small parser that builds React elements directly — no `dangerouslySetInnerHTML` — and only allows `http(s)`, `mailto`, `/` and `#` link targets.

**Accessibility.** Icon-only controls carry `aria-label`s (including the header buttons whose text collapses on small screens), the progress bars expose `role="progressbar"` values, sortable table headers set `aria-sort`, cards use a stretched-link pattern so each has exactly one tab stop, and `prefers-reduced-motion` disables the animations.
