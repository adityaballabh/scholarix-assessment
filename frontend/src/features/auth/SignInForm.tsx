import { type FormEvent, useId, useState } from "react";

import { ApiError, createAccount, signIn } from "../../api/client";
import type { User } from "../../api/types";
import { rememberCredentials } from "../../lib/credentials";
import styles from "./SignInForm.module.css";

type Mode = "sign-in" | "register";

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
    setPending(true);
    setError(null);
    try {
      const user = registering
        ? await createAccount({
            username,
            password,
            display_name: displayName,
          })
        : await signIn({ username, password });
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
          : "Could not reach the review service",
      );
      setPending(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={submit}>
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
          autoFocus={autoFocus}
          autoComplete="username"
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
