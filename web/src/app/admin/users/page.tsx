import type { Metadata } from "next";

import { removeUser } from "@/app/admin/actions";
import { requireAdminPage } from "@/lib/admin-guard";
import { isAdminEmail, listUsers } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · Users — FinhubKH",
};

export const dynamic = "force-dynamic";

function formatDate(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

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
        <p className="mt-6 max-w-3xl rounded-lg bg-short-soft px-4 py-3 text-sm text-short">
          {error}
        </p>
      ) : null}
      {deleted ? (
        <p className="mt-6 max-w-3xl rounded-lg bg-long-soft px-4 py-3 text-sm text-long">
          User deleted.
        </p>
      ) : null}

      {users && users.length > 0 ? (
        <div className="mt-8 max-w-3xl overflow-x-auto rounded-xl border border-line">
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
                    {formatDate(u.createdAt)}
                  </td>
                  <td className="px-4 py-3 text-slate">
                    {formatDate(u.lastSignInAt)}
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
