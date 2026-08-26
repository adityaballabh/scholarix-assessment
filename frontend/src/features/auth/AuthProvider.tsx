import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  getCurrentUser,
  setUnauthorizedHandler,
  signOut as endSession,
} from "../../api/client";
import type { User } from "../../api/types";
import { SignInDialog } from "./SignInDialog";

interface Session {
  user: User | null;
  ready: boolean;
  setUser: (user: User) => void;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (session === null) {
    throw new Error("useSession must be used inside AuthProvider");
  }
  return session;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [prompting, setPrompting] = useState(false);
  // Every refused write waiting on the reviewer to sign in or dismiss. A list rather than a
  // single resolver: two writes can be refused before either settles — a decision and a
  // header fetch, say — and holding only the newest would strand the older request forever,
  // leaving its caller's busy flag stuck on.
  const waiting = useRef<((signedIn: boolean) => void)[]>([]);

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(
      () =>
        new Promise<boolean>((resolve) => {
          waiting.current.push(resolve);
          setPrompting(true);
        }),
    );
    return () => setUnauthorizedHandler(null);
  }, []);

  const settle = useCallback((signedIn: boolean) => {
    setPrompting(false);
    const pending = waiting.current;
    waiting.current = [];
    for (const resolve of pending) resolve(signedIn);
  }, []);

  const value = useMemo<Session>(
    () => ({
      user,
      ready,
      setUser,
      signOut: async () => {
        await endSession();
        setUser(null);
      },
    }),
    [user, ready],
  );

  return (
    <SessionContext.Provider value={value}>
      {children}
      <SignInDialog
        open={prompting}
        onDismiss={() => settle(false)}
        onSignedIn={(signedIn) => {
          setUser(signedIn);
          settle(true);
        }}
      />
    </SessionContext.Provider>
  );
}
