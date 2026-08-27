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
  // Every concurrent 401 must settle when the sign-in prompt closes
  const unauthorizedWaiters = useRef<((signedIn: boolean) => void)[]>([]);

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then((currentUser) => {
        if (active) setUser(currentUser);
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(
      () =>
        new Promise<boolean>((resolve) => {
          unauthorizedWaiters.current.push(resolve);
          setPrompting(true);
        }),
    );
    return () => {
      setUnauthorizedHandler(null);
      for (const resolve of unauthorizedWaiters.current) resolve(false);
      unauthorizedWaiters.current = [];
    };
  }, []);

  const settleWaiters = useCallback((signedIn: boolean) => {
    setPrompting(false);
    const pending = unauthorizedWaiters.current;
    unauthorizedWaiters.current = [];
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
        onDismiss={() => settleWaiters(false)}
        onSignedIn={(signedIn) => {
          setUser(signedIn);
          settleWaiters(true);
        }}
      />
    </SessionContext.Provider>
  );
}
