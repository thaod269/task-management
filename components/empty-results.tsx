import { SearchX } from "lucide-react";

export function EmptyResults({ onClearFilters }: { onClearFilters: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 pb-16 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
        <SearchX className="h-6 w-6" />
      </span>
      <div>
        <p className="text-sm font-semibold text-slate-900">No matching cards</p>
        <p className="mt-1 text-sm text-slate-500">
          Nothing on this board matches your search and filters.
        </p>
      </div>
      <button
        type="button"
        onClick={onClearFilters}
        className="rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-semibold text-white transition-colors duration-150 hover:bg-slate-700"
      >
        Clear all filters
      </button>
    </div>
  );
}
