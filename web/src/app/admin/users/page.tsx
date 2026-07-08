import type { Metadata } from "next";

import { removeUser } from "@/app/admin/actions";
import { Notice } from "@/components/shared/Notice";
import { requireAdminPage } from "@/lib/admin-guard";
import { formatDateTime } from "@/lib/format";
import { isAdminEmail, listUsers } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · Users — FinhubKH",
};

export const dynamic = "force-dynamic";

export default async function AdminUsers({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; deleted?: string }>;
}) {
  await requireAdminPage();
  const { error, deleted } = await searchParams;
  const users = await listUsers();

  return (
    <>
      <h1 className="font-display text-3xl tracking-tight">
        Users{users ? ` (${users.length})` : ""}
      </h1>
      <p className="mt-2 text-sm text-slate">
        Everyone with an account. Deleting a user signs them out and removes
        their login for good.
      </p>

      {error ? (
        <Notice tone="error" className="mt-6 max-w-3xl">
          {error}
        </Notice>
      ) : null}
      {deleted ? (
        <Notice tone="success" className="mt-6 max-w-3xl">
          User deleted.
        </Notice>
      ) : null}

      {users && users.length > 0 ? (
        <div className="mt-8 overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wider text-slate">
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Signed up</th>
                <th className="px-4 py-3 font-medium">Last sign-in</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-3">{u.email}</td>
                  <td className="px-4 py-3 text-slate">
                    {formatDateTime(u.createdAt)}
                  </td>
                  <td className="px-4 py-3 text-slate">
                    {formatDateTime(u.lastSignInAt)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {isAdminEmail(u.email) ? (
                      <span className="text-xs text-slate">admin</span>
                    ) : (
                      <form action={removeUser}>
                        <input type="hidden" name="id" value={u.id} />
                        <button className="text-sm text-short hover:underline">
                          Delete
                        </button>
                      </form>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-8 text-sm text-slate">
          {users ? "No users have signed up yet." : "Could not load users."}
        </p>
      )}
    </>
  );
}
