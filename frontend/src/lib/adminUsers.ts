/** Types and pure helpers for the admin Users page (kept out of the page
 *  module so React Fast Refresh sees a components-only file there). */

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  subscription_plan: string;
  subscription_active: boolean;
  created_at: string;
}

/** Receipt returned by `DELETE /admin/users/{id}` — nothing in it identifies
 *  the erased person; `audit_pseudonym` is the key an auditor uses to find
 *  the pseudonymised trail. */
export interface DeleteReceipt {
  id: string;
  audit_pseudonym: string;
  email_pseudonym: string;
  audit_rows_pseudonymised: number;
  redis_keys_purged: number | null;
}

/** Text of the native confirm shown before an account is erased. The unit
 *  test asserts the exact wording the administrator agrees to. */
export function deleteConfirmMessage(u: Pick<AdminUser, "email">): string {
  return (
    `Permanently delete ${u.email}?\n\n` +
    "Everything the account owns is erased (quizzes, moodboards, projects, share links, " +
    "subscription and payments) and its security trail is pseudonymised. " +
    "This cannot be undone and is recorded in the audit log under your name."
  );
}

/** Case-insensitive filter on e-mail or display name. */
export function filterUsers<T extends Pick<AdminUser, "email" | "full_name">>(
  users: readonly T[],
  query: string,
): T[] {
  const q = query.trim().toLowerCase();
  if (!q) return [...users];
  return users.filter(
    (u) => u.email.toLowerCase().includes(q) || (u.full_name ?? "").toLowerCase().includes(q),
  );
}
