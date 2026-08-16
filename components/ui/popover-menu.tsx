"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

const VIEWPORT_PADDING = 8;
const TRIGGER_GAP = 6;

/**
 * A floating panel rendered into `document.body` so it escapes the board's
 * scroll containers instead of being clipped by them. Positioned from the
 * trigger's bounding rect, flipped upwards when it would overflow the viewport,
 * and closed on outside click, Escape, resize or any ancestor scroll.
 */
export function PopoverMenu({
  trigger,
  children,
  label,
  width = 208,
  matchTriggerWidth = false,
  minWidth = 0,
  align = "end",
  role = "menu",
  className,
  anchorClassName,
}: {
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode;
  children: (close: () => void) => ReactNode;
  label: string;
  width?: number;
  /** Grow the panel to the trigger's width — used by select-style dropdowns. */
  matchTriggerWidth?: boolean;
  minWidth?: number;
  align?: "start" | "end";
  role?: "menu" | "listbox";
  className?: string;
  anchorClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0, width });
  const anchorRef = useRef<HTMLSpanElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const updatePosition = useCallback(() => {
    const anchor = anchorRef.current?.getBoundingClientRect();
    if (!anchor) return;

    const panelWidth = matchTriggerWidth
      ? Math.max(anchor.width, minWidth)
      : Math.max(width, minWidth);
    const panelHeight = panelRef.current?.offsetHeight ?? 0;

    const spaceBelow = window.innerHeight - anchor.bottom;
    const flip = spaceBelow < panelHeight + TRIGGER_GAP && anchor.top > panelHeight;

    const preferredLeft = align === "end" ? anchor.right - panelWidth : anchor.left;
    const maxLeft = Math.max(
      VIEWPORT_PADDING,
      window.innerWidth - panelWidth - VIEWPORT_PADDING,
    );

    setPosition({
      top: flip
        ? Math.max(VIEWPORT_PADDING, anchor.top - panelHeight - TRIGGER_GAP)
        : anchor.bottom + TRIGGER_GAP,
      left: Math.min(Math.max(VIEWPORT_PADDING, preferredLeft), maxLeft),
      width: panelWidth,
    });
  }, [width, matchTriggerWidth, minWidth, align]);

  useLayoutEffect(() => {
    if (open) updatePosition();
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return;

    const close = () => setOpen(false);

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || anchorRef.current?.contains(target)) {
        return;
      }
      close();
    };

    // Capture phase: Escape closes this panel *before* React's root listener
    // hands the event to an enclosing dialog, so one press closes one layer.
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      close();
    };

    /*
     * Follow the trigger rather than closing on every scroll: clicking a
     * trigger near the viewport edge makes the browser scroll it into view,
     * and closing on that would dismiss the panel the instant it opened.
     * Only bail out once the trigger has actually scrolled out of sight.
     */
    const onReflow = () => {
      const anchor = anchorRef.current?.getBoundingClientRect();
      if (!anchor) return;
      if (anchor.bottom < 0 || anchor.top > window.innerHeight) {
        close();
        return;
      }
      updatePosition();
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("resize", onReflow);
    window.addEventListener("scroll", onReflow, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("resize", onReflow);
      window.removeEventListener("scroll", onReflow, true);
    };
  }, [open, updatePosition]);

  return (
    <>
      <span ref={anchorRef} className={cn("inline-flex max-w-full", anchorClassName)}>
        {trigger({ open, toggle: () => setOpen((previous) => !previous) })}
      </span>

      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={panelRef}
            role={role}
            aria-label={label}
            style={{
              top: position.top,
              left: position.left,
              width: position.width,
            }}
            className={cn(
              "fixed z-[60] max-h-[min(20rem,60vh)] overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-xl shadow-slate-900/10 animate-scale-in scrollbar-slim",
              className,
            )}
          >
            {children(() => setOpen(false))}
          </div>,
          document.body,
        )}
    </>
  );
}

export function MenuItem({
  onClick,
  icon,
  children,
  hint,
  tone = "default",
  selected = false,
  role = "menuitem",
  trailing,
}: {
  onClick: () => void;
  icon?: ReactNode;
  children: ReactNode;
  hint?: string;
  tone?: "default" | "danger";
  selected?: boolean;
  role?: "menuitem" | "option";
  trailing?: ReactNode;
}) {
  return (
    <button
      type="button"
      role={role}
      aria-selected={role === "option" ? selected : undefined}
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors duration-100",
        tone === "danger"
          ? "text-rose-600 hover:bg-rose-50"
          : "text-slate-700 hover:bg-slate-50",
        selected && tone === "default" && "bg-slate-100 font-medium text-slate-900",
      )}
    >
      {icon}
      <span className="min-w-0 flex-1">
        <span className="block truncate">{children}</span>
        {hint && <span className="block truncate text-xs text-slate-400">{hint}</span>}
      </span>
      {trailing}
    </button>
  );
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return (
    <p className="px-2.5 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
      {children}
    </p>
  );
}

export function MenuSeparator() {
  return <div className="my-1 h-px bg-slate-100" />;
}
