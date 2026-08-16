import { Fragment, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * A dependency-free Markdown renderer covering the subset a task description
 * realistically needs: headings, lists, blockquotes, fenced code, bold, italic,
 * inline code and links.
 *
 * It builds React elements directly — never `dangerouslySetInnerHTML` — so
 * user-authored descriptions can't inject markup, and link protocols are
 * allow-listed on top of that.
 */
export function Markdown({
  source,
  className,
}: {
  source: string;
  className?: string;
}) {
  const blocks = parseBlocks(source.trim());

  if (blocks.length === 0) return null;

  return (
    <div className={cn("space-y-3 text-sm leading-relaxed text-slate-600", className)}>
      {blocks}
    </div>
  );
}

const INLINE_PATTERN =
  /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`|\[[^\]\n]+\]\([^)\s]+\))/g;

const SAFE_PROTOCOL = /^(https?:|mailto:|\/|#)/i;

/** Splits a line into bold / italic / code / link segments. */
function renderInline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(INLINE_PATTERN).map((token, index) => {
    const key = `${keyPrefix}-${index}`;
    if (!token) return null;

    if (token.startsWith("**") && token.endsWith("**")) {
      return (
        <strong key={key} className="font-semibold text-slate-900">
          {token.slice(2, -2)}
        </strong>
      );
    }
    if (
      (token.startsWith("*") && token.endsWith("*")) ||
      (token.startsWith("_") && token.endsWith("_"))
    ) {
      return (
        <em key={key} className="italic">
          {token.slice(1, -1)}
        </em>
      );
    }
    if (token.startsWith("`") && token.endsWith("`")) {
      return (
        <code
          key={key}
          className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.85em] text-slate-800"
        >
          {token.slice(1, -1)}
        </code>
      );
    }

    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(token);
    if (link) {
      const [, label, href] = link;
      if (!SAFE_PROTOCOL.test(href)) return <Fragment key={key}>{label}</Fragment>;
      return (
        <a
          key={key}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-slate-900 underline decoration-slate-300 underline-offset-2 transition-colors hover:decoration-slate-900"
        >
          {label}
        </a>
      );
    }

    return <Fragment key={key}>{token}</Fragment>;
  });
}

function parseBlocks(source: string): ReactNode[] {
  const lines = source.split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  const key = () => `block-${blocks.length}`;

  while (index < lines.length) {
    const line = lines[index];

    // Blank line — nothing to emit.
    if (!line.trim()) {
      index += 1;
      continue;
    }

    // Fenced code block.
    if (line.trimStart().startsWith("```")) {
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trimStart().startsWith("```")) {
        body.push(lines[index]);
        index += 1;
      }
      index += 1; // closing fence
      blocks.push(
        <pre
          key={key()}
          className="overflow-x-auto rounded-lg bg-slate-900 p-3 font-mono text-xs leading-relaxed text-slate-100 scrollbar-slim"
        >
          <code>{body.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    // Horizontal rule.
    if (/^(-{3,}|\*{3,})$/.test(line.trim())) {
      blocks.push(<hr key={key()} className="border-slate-200" />);
      index += 1;
      continue;
    }

    // Heading.
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const size =
        level === 1 ? "text-base" : level === 2 ? "text-sm" : "text-[13px]";
      blocks.push(
        <p key={key()} className={cn("font-semibold text-slate-900", size)}>
          {renderInline(heading[2], key())}
        </p>,
      );
      index += 1;
      continue;
    }

    // Blockquote (consecutive `>` lines).
    if (line.trimStart().startsWith(">")) {
      const body: string[] = [];
      while (index < lines.length && lines[index].trimStart().startsWith(">")) {
        body.push(lines[index].trimStart().replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push(
        <blockquote
          key={key()}
          className="border-l-2 border-slate-300 pl-3 text-slate-500 italic"
        >
          {renderInline(body.join(" "), key())}
        </blockquote>,
      );
      continue;
    }

    // Unordered list.
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ul key={key()} className="list-disc space-y-1 pl-5 marker:text-slate-400">
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{renderInline(item, `${key()}-${itemIndex}`)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    // Ordered list.
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ol key={key()} className="list-decimal space-y-1 pl-5 marker:text-slate-400">
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{renderInline(item, `${key()}-${itemIndex}`)}</li>
          ))}
        </ol>,
      );
      continue;
    }

    // Paragraph — soft-wrapped until a blank line or another block starts.
    const paragraph: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^\s*([-*]\s+|\d+\.\s+|#{1,3}\s+|>|```)/.test(lines[index])
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={key()}>{renderInline(paragraph.join(" "), key())}</p>);
  }

  return blocks;
}
