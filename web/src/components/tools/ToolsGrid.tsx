import Link from "next/link";

import {
  formatToolFileSize,
  getPublishedTools,
  toolCategoryLabelKm,
  toolDownloadHref,
  toolIsExternal,
  type Tool,
} from "@/lib/tools";

function ToolCard({ tool }: { tool: Tool }) {
  const href = toolDownloadHref(tool);
  const external = toolIsExternal(tool);
  const size = formatToolFileSize(tool.fileSize);

  return (
    <article className="card-surface flex h-full flex-col p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-paper px-2 py-0.5 text-xs font-medium text-slate">
          {toolCategoryLabelKm(tool.category)}
        </span>
        {tool.fileName && size ? (
          <span className="text-xs text-slate">{size}</span>
        ) : null}
      </div>
      <h2 className="mt-3 text-lg font-semibold text-ink">{tool.titleKm}</h2>
      {tool.descriptionKm ? (
        <p className="mt-2 flex-1 text-sm leading-relaxed text-slate">
          {tool.descriptionKm}
        </p>
      ) : (
        <div className="flex-1" />
      )}
      <div className="mt-5 border-t border-line pt-4">
        {href ? (
          <a
            href={href}
            target={external ? "_blank" : undefined}
            rel={external ? "noopener noreferrer" : undefined}
            download={external ? undefined : tool.fileName ?? true}
            className="btn-primary inline-flex w-full justify-center sm:w-auto"
          >
            {external ? "បើក TradingView" : "ទាញយកឥតគិតថ្លៃ"}
          </a>
        ) : (
          <span className="text-sm text-slate">មិនទាន់មានឯកសារទេ</span>
        )}
        {tool.fileName && !external ? (
          <p className="mt-2 font-mono text-xs text-slate">{tool.fileName}</p>
        ) : null}
      </div>
    </article>
  );
}

export function ToolsGrid({ tools }: { tools: Tool[] }) {
  if (tools.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-line bg-card px-6 py-14 text-center">
        <p className="text-sm font-semibold text-ink">មិនទាន់មានឧបករណ៍ទេ</p>
        <p className="mx-auto mt-1.5 max-w-sm text-sm text-slate">
          EA និង indicator ឥតគិតថ្លៃនឹងបង្ហាញនៅទីនេះឆាប់ៗ។
        </p>
        <Link href="/signals" className="btn-secondary mt-5 inline-flex">
          ទៅ Signals
        </Link>
      </div>
    );
  }

  return (
    <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
      {tools.map((tool) => (
        <ToolCard key={tool.id} tool={tool} />
      ))}
    </div>
  );
}
