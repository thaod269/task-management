"use client";

import { Check, ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import { MenuItem, PopoverMenu } from "./popover-menu";

export interface DropdownOption<T extends string> {
  value: T;
  label: string;
  /** Rendered before the label in both the trigger and the list. */
  icon?: ReactNode;
  /** Muted secondary line, e.g. a team member's role. */
  hint?: string;
}

/**
 * Select-style dropdown. Built on `PopoverMenu` so the list is portalled and
 * never clipped by the modal body or the horizontally scrolling board.
 */
export function Dropdown<T extends string>({
  value,
  options,
  onChange,
  label,
  prefix,
  align = "start",
  className,
  triggerClassName,
  active = false,
}: {
  value: T;
  options: DropdownOption<T>[];
  onChange: (value: T) => void;
  label: string;
  /** Shown before the selected label, e.g. "Priority:". */
  prefix?: string;
  align?: "start" | "end";
  className?: string;
  triggerClassName?: string;
  /** Highlights the trigger when a non-default value is selected. */
  active?: boolean;
}) {
  const selected = options.find((option) => option.value === value);

  return (
    <div className={cn("min-w-0", className)}>
      <PopoverMenu
        label={label}
        role="listbox"
        align={align}
        matchTriggerWidth
        minWidth={208}
        anchorClassName="w-full"
        trigger={({ open, toggle }) => (
          <button
            type="button"
            onClick={toggle}
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-label={label}
            className={cn(
              "flex w-full items-center gap-2 rounded-lg border bg-white px-3 py-2 text-sm font-medium shadow-xs transition-colors duration-150 hover:bg-slate-50",
              active
                ? "border-slate-300 bg-slate-50 text-slate-900"
                : "border-slate-200 text-slate-700",
              triggerClassName,
            )}
          >
            {selected?.icon}
            <span className="min-w-0 flex-1 truncate text-left">
              {prefix && <span className="font-normal text-slate-400">{prefix} </span>}
              {selected?.label ?? label}
            </span>
            <ChevronDown
              className={cn(
                "h-4 w-4 shrink-0 text-slate-400 transition-transform duration-200",
                open && "rotate-180",
              )}
            />
          </button>
        )}
      >
        {(close) =>
          options.map((option) => (
            <MenuItem
              key={option.value}
              role="option"
              selected={option.value === value}
              icon={option.icon}
              hint={option.hint}
              trailing={
                option.value === value ? (
                  <Check className="h-4 w-4 shrink-0 text-slate-900" />
                ) : undefined
              }
              onClick={() => {
                onChange(option.value);
                close();
              }}
            >
              {option.label}
            </MenuItem>
          ))
        }
      </PopoverMenu>
    </div>
  );
}
