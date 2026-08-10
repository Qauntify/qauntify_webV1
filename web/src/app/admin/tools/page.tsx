import type { Metadata } from "next";

import {
  createTool,
  removeTool,
  toggleToolPublished,
} from "@/app/admin/actions";
import { Notice } from "@/components/shared/Notice";
import { requireAdminPage } from "@/lib/admin-guard";
import { listAllTools } from "@/lib/supabase/admin";
import {
  formatToolFileSize,
  parseToolRow,
  TOOL_CATEGORIES,
  toolCategoryLabelKm,
  toolDownloadHref,
  toolIsExternal,
} from "@/lib/tools";

export const metadata: Metadata = {
  title: "Admin · Tools — Qauntify",
};

export const revalidate = 30;

export default async function AdminToolsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; saved?: string; deleted?: string }>;
}) {
  await requireAdminPage();
  const { error, saved, deleted } = await searchParams;
  const rows = await listAllTools();
  const tools = rows.map(parseToolRow).filter((t): t is NonNullable<typeof t> => t != null);

  return (
    <div className="flex w-full max-w-5xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-ink">Tools</h1>
        <p className="mt-1 text-sm text-slate">
          Upload free MT5 EAs, indicators, or link TradingView scripts for the
          public tools page.
        </p>
      </div>

      {error ? <Notice tone="error">{error}</Notice> : null}
      {saved ? <Notice tone="success">Tools updated.</Notice> : null}
      {deleted ? <Notice tone="success">Tool deleted.</Notice> : null}

      <section className="card-surface p-5">
        <h2 className="text-lg font-semibold">Add tool</h2>
        <p className="mt-1 text-sm text-slate">
          Khmer title and description appear on the public page. Upload a file
          (.mq5, .ex5, .zip) or paste a TradingView / external link — not both.
        </p>
        <form action={createTool} className="mt-5 flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Title (Khmer)
              <input
                type="text"
                name="title_km"
                required
                placeholder="Qauntify BBMA EA"
                className="input-field w-full"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Category
              <select name="category" defaultValue="mt5_ea" className="input-field w-full">
                {TOOL_CATEGORIES.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.labelEn}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Description (Khmer)
            <textarea
              name="description_km"
              rows={3}
              placeholder="EA BBMA ឥតគិតថ្លៃសម្រាប់ XAUUSD..."
              className="input-field w-full resize-y"
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              File upload
              <input
                type="file"
                name="file"
                accept=".mq5,.ex5,.zip,.pdf,.txt,.set,.tpl,.png,.jpg"
                className="text-sm text-slate file:mr-3 file:rounded-md file:border-0 file:bg-paper file:px-3 file:py-2 file:text-sm file:font-medium file:text-ink"
              />
              <span className="text-xs font-normal text-slate">Max 25 MB</span>
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              External URL (TradingView, etc.)
              <input
                type="url"
                name="external_url"
                placeholder="https://www.tradingview.com/script/..."
                className="input-field w-full font-mono text-sm"
              />
            </label>
          </div>
          <label className="flex max-w-[8rem] flex-col gap-1.5 text-sm font-medium">
            Sort order
            <input
              type="number"
              name="sort_order"
              defaultValue={0}
              step={1}
              className="input-field w-full"
            />
            <span className="text-xs font-normal text-slate">Lower = first</span>
          </label>
          <div className="border-t border-line pt-4">
            <button type="submit" className="btn-primary">
              Publish tool
            </button>
          </div>
        </form>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">
          Published tools ({tools.length})
        </h2>
        {tools.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line bg-card px-6 py-10 text-center text-sm text-slate">
            No tools yet. Add your first EA or indicator above.
          </div>
        ) : (
          tools.map((tool) => {
            const href = toolDownloadHref(tool);
            const size = formatToolFileSize(tool.fileSize);
            return (
              <article
                key={tool.id}
                className="card-surface flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold text-ink">{tool.titleKm}</h3>
                    <span className="rounded-md bg-paper px-2 py-0.5 text-xs font-medium text-slate">
                      {toolCategoryLabelKm(tool.category)}
                    </span>
                    {!tool.published ? (
                      <span className="rounded-md bg-short-soft px-2 py-0.5 text-xs font-medium text-short">
                        Hidden
                      </span>
                    ) : null}
                  </div>
                  {tool.descriptionKm ? (
                    <p className="mt-1 text-sm text-slate">{tool.descriptionKm}</p>
                  ) : null}
                  <p className="mt-2 font-mono text-xs text-slate">
                    {toolIsExternal(tool)
                      ? tool.externalUrl
                      : tool.fileName
                        ? `${tool.fileName}${size ? ` · ${size}` : ""}`
                        : "—"}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-secondary py-2! px-3! text-xs!"
                    >
                      Open
                    </a>
                  ) : null}
                  <form action={toggleToolPublished}>
                    <input type="hidden" name="id" value={tool.id} />
                    <input
                      type="hidden"
                      name="published"
                      value={tool.published ? "false" : "true"}
                    />
                    <button type="submit" className="btn-ghost text-xs">
                      {tool.published ? "Hide" : "Show"}
                    </button>
                  </form>
                  <form action={removeTool}>
                    <input type="hidden" name="id" value={tool.id} />
                    <button
                      type="submit"
                      className="btn-ghost text-xs text-short hover:text-short"
                    >
                      Delete
                    </button>
                  </form>
                </div>
              </article>
            );
          })
        )}
      </section>
    </div>
  );
}
