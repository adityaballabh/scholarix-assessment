// SPA sign-ins can bypass password-manager detection
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
    // Keep sign-in successful if the password manager rejects the request
  }
}
