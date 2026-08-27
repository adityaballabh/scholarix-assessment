import { type FormEvent, useId, useState } from "react";

import { ApiError, createAccount, signIn } from "../../api/client";
import type { User } from "../../api/types";
import { rememberCredentials } from "../../lib/credentials";
import styles from "./SignInForm.module.css";

type Mode = "sign-in" | "register";

const USERNAME_PATTERN = /^[a-z0-9._-]+$/;

function validationError(
  registering: boolean,
  username: string,
  displayName: string,
  password: string,
): string | null {
  if (registering && username.length < 3) {
    return "Username must be at least 3 characters";
  }
  if (!registering && username.length < 1) return "Username is required";
  if (username.length > 64) return "Username must be 64 characters or fewer";
  if (registering && !USERNAME_PATTERN.test(username)) {
    return "Use letters, numbers, periods, underscores, or hyphens for the username";
  }
  if (registering && displayName.length < 1) return "Display name is required";
  if (registering && displayName.length > 64) {
    return "Display name must be 64 characters or fewer";
  }
  if (registering && password.length < 8) {
    return "Password must be at least 8 characters";
  }
  if (!registering && password.length < 1) return "Password is required";
  if (password.length > 1024) return "Password is too long";
  return null;
}

export function SignInForm({
  autoFocus = false,
  initialMode = "sign-in",
  onSignedIn,
}: {
  autoFocus?: boolean;
  initialMode?: Mode;
  onSignedIn: (user: User) => void;
}) {
  const fieldId = useId();
  const [mode, setMode] = useState<Mode>(initialMode);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const registering = mode === "register";

  async function submit(event: FormEvent) {
    event.preventDefault();
    const normalizedUsername = username.trim().toLowerCase();
    const normalizedDisplayName = displayName.trim();
    const invalid = validationError(
      registering,
      normalizedUsername,
      normalizedDisplayName,
      password,
    );
    if (invalid) {
      setError(invalid);
      return;
    }

    setPending(true);
    setError(null);
    try {
      const user = registering
        ? await createAccount({
            username: normalizedUsername,
            password,
            display_name: normalizedDisplayName,
          })
        : await signIn({ username: normalizedUsername, password });
      await rememberCredentials({
        id: user.username,
        password,
        name: user.display_name,
      });
      onSignedIn(user);
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status < 500
          ? cause.message
          : "Could not reach the server",
      );
      setPending(false);
    }
  }

  return (
    <form className={styles.form} noValidate onSubmit={submit}>
      <p className={styles.heading}>
        {registering ? "Create account" : "Sign in"}
      </p>
      <div className={styles.field}>
        <label className={styles.label} htmlFor={`${fieldId}-username`}>
          username
        </label>
        <input
          id={`${fieldId}-username`}
          name="username"
          className={styles.input}
          value={username}
          required
          minLength={registering ? 3 : 1}
          pattern={registering ? "[a-z0-9._-]+" : undefined}
          autoFocus={autoFocus}
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          disabled={pending}
          onChange={(event) => setUsername(event.target.value)}
        />
      </div>

      {registering ? (
        <div className={styles.field}>
          <label className={styles.label} htmlFor={`${fieldId}-display-name`}>
            display name
          </label>
          <input
            id={`${fieldId}-display-name`}
            name="display_name"
            className={styles.input}
            value={displayName}
            required
            autoComplete="name"
            disabled={pending}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </div>
      ) : null}

      <div className={styles.field}>
        <label className={styles.label} htmlFor={`${fieldId}-password`}>
          password
        </label>
        <input
          id={`${fieldId}-password`}
          name="password"
          className={styles.input}
          type="password"
          value={password}
          required
          minLength={registering ? 8 : 1}
          maxLength={1024}
          autoComplete={registering ? "new-password" : "current-password"}
          disabled={pending}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>

      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.switch}
          disabled={pending}
          onClick={() => {
            setMode(registering ? "sign-in" : "register");
            setError(null);
          }}
        >
          {registering ? "already have an account" : "create an account"}
        </button>
        <button type="submit" className={styles.submit} disabled={pending}>
          {registering ? "create account" : "sign in"}
        </button>
      </div>
    </form>
  );
}
