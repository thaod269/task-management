import type { TeamMember } from "@/lib/types";
import { cn } from "@/lib/utils";

const SIZES = {
  xs: "h-5 w-5 text-[10px]",
  sm: "h-6 w-6 text-[10px]",
  md: "h-8 w-8 text-xs",
  lg: "h-10 w-10 text-sm",
} as const;

export type AvatarSize = keyof typeof SIZES;

export function Avatar({
  member,
  size = "md",
  className,
}: {
  member: TeamMember;
  size?: AvatarSize;
  className?: string;
}) {
  return (
    <span
      title={`${member.name} · ${member.role}`}
      className={cn(
        "inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold ring-1 ring-inset",
        SIZES[size],
        member.accent,
        className,
      )}
    >
      {member.initials}
    </span>
  );
}

/** Placeholder avatar for tasks with nobody assigned. */
export function UnassignedAvatar({
  size = "md",
  className,
}: {
  size?: AvatarSize;
  className?: string;
}) {
  return (
    <span
      title="Unassigned"
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full border border-dashed border-slate-300 bg-white font-semibold text-slate-400",
        SIZES[size],
        className,
      )}
    >
      ?
    </span>
  );
}

export function AvatarStack({
  members,
  max = 4,
  size = "md",
}: {
  members: TeamMember[];
  max?: number;
  size?: AvatarSize;
}) {
  const shown = members.slice(0, max);
  const overflow = members.length - shown.length;

  return (
    <div className="flex items-center -space-x-2">
      {shown.map((member) => (
        <Avatar
          key={member.id}
          member={member}
          size={size}
          className="ring-2 ring-white transition-transform duration-150 hover:z-10 hover:-translate-y-0.5"
        />
      ))}
      {overflow > 0 && (
        <span
          className={cn(
            "inline-flex shrink-0 items-center justify-center rounded-full bg-slate-200 font-semibold text-slate-600 ring-2 ring-white",
            SIZES[size],
          )}
        >
          +{overflow}
        </span>
      )}
    </div>
  );
}
