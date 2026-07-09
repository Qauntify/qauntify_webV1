"use client";

import { useTransition } from "react";
import { removeSignal } from "@/app/admin/actions";

export function DeleteSignalButton({
  id,
  triggerClassName = "text-short hover:underline font-semibold",
}: {
  id: string;
  triggerClassName?: string;
}) {
  // We use a hidden checkbox trick to avoid state — but a dialog element
  // is the cleanest approach. Using useTransition to track action pending.
  const [isPending, startTransition] = useTransition();

  // Use a separate state-free approach via a <dialog> ref would be ideal,
  // but let's keep it simple with a data-attribute driven approach.
  // Instead, use a label+checkbox pattern or just keep useState but fix the bug.

  function openDialog() {
    const dialog = document.getElementById(`delete-dialog-${id}`) as HTMLDialogElement | null;
    dialog?.showModal();
  }

  function closeDialog() {
    const dialog = document.getElementById(`delete-dialog-${id}`) as HTMLDialogElement | null;
    dialog?.close();
  }

  function handleConfirm() {
    startTransition(async () => {
      const formData = new FormData();
      formData.set("id", id);
      await removeSignal(formData);
      closeDialog();
    });
  }

  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          openDialog();
        }}
        className={triggerClassName}
      >
        Delete
      </button>

      {/* Native <dialog> — it renders in the top layer, escaping overflow/z-index issues */}
      <dialog
        id={`delete-dialog-${id}`}
        onClick={(e) => {
          // Close when clicking the backdrop (outside the dialog box)
          if (e.target === e.currentTarget) closeDialog();
        }}
        className={[
          "backdrop:bg-black/60 backdrop:backdrop-blur-sm",
          "w-full max-w-sm rounded-xl border border-line bg-card shadow-2xl p-0",
          "open:flex open:flex-col",
          "m-auto", // centre in viewport
        ].join(" ")}
      >
        <div className="p-6">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-short/10 mb-4">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-short"
            >
              <path d="M3 6h18" />
              <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
              <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
              <line x1="10" y1="11" x2="10" y2="17" />
              <line x1="14" y1="11" x2="14" y2="17" />
            </svg>
          </div>
          <h3 className="text-lg font-bold text-ink text-center">Delete Signal</h3>
          <p className="mt-2 text-sm text-slate text-center">
            Are you sure you want to delete this signal? This action is permanent and cannot be undone.
          </p>
        </div>

        <div className="bg-slate/5 border-t border-line/50 px-6 py-4 flex items-center gap-3">
          <button
            type="button"
            disabled={isPending}
            onClick={closeDialog}
            className="btn-ghost flex-1 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={isPending}
            onClick={handleConfirm}
            className="btn-primary-sm bg-short hover:bg-short/90 text-white flex-1 shadow-lg shadow-short/20 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isPending ? "Deleting…" : "Confirm"}
          </button>
        </div>
      </dialog>
    </>
  );
}
