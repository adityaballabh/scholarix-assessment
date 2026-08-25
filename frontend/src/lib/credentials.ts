/**
 * Tell the browser's password manager that a sign-in succeeded, rather than
 * leaving it to infer one from an SPA submit that never navigates.
 *
 * Chromium only. Safari and Firefox do not implement PasswordCredential and
 * fall back to their own heuristics, so this is best-effort by design.
 */
interface PasswordCredentialData {
  id: string;
  password: string;
  name?: string;
}

type PasswordCredentialConstructor = new (
  data: PasswordCredentialData,
) => Credential;

export async function rememberCredentials(
  data: PasswordCredentialData,
): Promise<void> {
  const constructor = (
    window as unknown as {
      PasswordCredential?: PasswordCredentialConstructor;
    }
  ).PasswordCredential;
  if (!constructor || !navigator.credentials?.store) return;

  try {
    await navigator.credentials.store(new constructor(data));
  } catch {
    // A declined or unavailable password manager must not fail the sign-in.
  }
}
