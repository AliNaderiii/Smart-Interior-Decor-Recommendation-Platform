/**
 * Disposable e2e users (Stage 1, T-1.4 close-out — full spec isolation).
 *
 * WHY THIS EXISTS
 * ---------------
 * Every spec used to authenticate as the same three seeded demo accounts
 * (demo@/designer@/admin@smartdecor.dev). That made the suite one big shared
 * fixture: the dead-key sweep clicked through the designer dashboard and
 * consumed the designer's project quota, the homeowner quiz left answers
 * behind, and all of it competed for the same per-IP login rate limit. Runs
 * 32988827678 / 33005106968 / 33008122154 each failed a DIFFERENT subset of
 * tests from nearly identical code — the signature of shared mutable state.
 *
 * So: each role in each context gets its OWN freshly registered account with a
 * unique email. Nothing a spec does can be observed by another spec.
 *
 * WHAT IS DELIBERATELY *NOT* DISPOSABLE
 * -------------------------------------
 * `admin`. `POST /api/v1/auth/register` accepts `role` matching
 * `^(homeowner|designer)$` (see backend/app/schemas/auth.py:26) — privilege
 * escalation via self-registration is correctly impossible. The admin journey
 * therefore keeps using the seeded admin account, which is also the right call
 * on the merits: it asserts against the seeded product catalogue it reviews.
 * That is the single documented exception the supervisor allowed ("except
 * where the product itself is under test").
 */

/** Seeded accounts. Only `admin` is still used (see the note above). */
export const DEMO_ACCOUNTS = {
  homeowner: { email: "demo@smartdecor.dev", password: "Demo1234!" },
  designer: { email: "designer@smartdecor.dev", password: "Design123!" },
  admin: { email: "admin@smartdecor.dev", password: "Admin123!" },
} as const;

export type Role = "homeowner" | "designer" | "admin";

/** Roles a disposable account can be registered with. */
export type DisposableRole = "homeowner" | "designer";

export interface TestUser {
  email: string;
  password: string;
  role: Role;
  fullName: string;
}

/**
 * Password for every disposable user.
 *
 * `RegisterIn.password` requires 12..72 bytes and rejects the common
 * credential-stuffing entries, so this is long and unremarkable on purpose.
 */
const PASSWORD = "E2eTempPass!2026";

let counter = 0;

/**
 * Build a unique, obviously-synthetic identity.
 *
 * `@example.com` is RFC 2606 reserved, so these can never reach a real
 * mailbox. Timestamp + counter + random suffix keeps them unique across
 * parallel shards and across re-runs against a database that was not reset.
 */
export function makeUser(role: DisposableRole, label = "e2e"): TestUser {
  counter += 1;
  const unique = `${Date.now().toString(36)}-${counter}-${Math.random().toString(36).slice(2, 8)}`;
  return {
    email: `${label}-${role}-${unique}@example.com`,
    password: PASSWORD,
    role,
    fullName: `E2E ${role} ${counter}`,
  };
}

/**
 * Register a user through the public API.
 *
 * Uses the API rather than the signup UI on purpose: this is fixture setup,
 * not the thing under test, and the registration UI has its own coverage. A
 * 409 means the email was already taken, which for a generated address means
 * the generator is broken — so it is surfaced, not swallowed.
 */
export async function registerUser(
  baseUrl: string,
  user: TestUser,
  { attempts = 4 }: { attempts?: number } = {},
): Promise<TestUser> {
  let lastDetail = "";

  for (let attempt = 1; attempt <= attempts; attempt++) {
    const response = await fetch(`${baseUrl}/api/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: user.email,
        password: user.password,
        full_name: user.fullName,
        role: user.role,
      }),
    });

    if (response.ok) return user;

    lastDetail = await response.text().catch(() => "<unreadable body>");

    // 429: the per-IP registration limit. The e2e job raises it, but the
    // ACTIVE workflow only gets that env once the human applies the hand-off
    // edit, and the shipped default is 3/min — fewer than the 4 accounts this
    // suite needs. Honour Retry-After so setup succeeds either way instead of
    // depending on a manual workflow change.
    if (response.status === 429 && attempt < attempts) {
      const retryAfter = Number(response.headers.get("Retry-After") ?? 0);
      const waitMs = (Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : 20) * 1000 + 1_000;
      console.log(
        `users: registration of ${user.email} was rate limited (429); ` +
          `waiting ${Math.round(waitMs / 1000)}s then retrying ` +
          `(attempt ${attempt + 1}/${attempts}).`,
      );
      await new Promise((resolve) => setTimeout(resolve, waitMs));
      continue;
    }

    break;
  }

  throw new Error(
    `Failed to register the disposable ${user.role} ${user.email} after ` +
      `${attempts} attempt(s).\n${lastDetail}\n` +
      `Check that the API is reachable at ${baseUrl} and that ` +
      `REGISTER_RATE_LIMIT_PER_MINUTE is high enough for the suite.`,
  );
}
