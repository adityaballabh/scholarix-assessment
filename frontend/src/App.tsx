import { useEffect, useRef, useState } from "react";
import {
  Link,
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import ActivityPage from "./features/activity/ActivityPage";
import { useSession } from "./features/auth/AuthProvider";
import { SessionMenu } from "./features/auth/SessionMenu";
import SignInPage from "./features/auth/SignInPage";
import FetchConfirmDialog from "./features/fetch/FetchConfirmDialog";
import FetchPage from "./features/fetch/FetchPage";
import FetchSetupPage from "./features/fetch/FetchSetupPage";
import UnreachablePage from "./features/fetch/UnreachablePage";
import OverviewPage from "./features/overview/OverviewPage";
import CasePage from "./features/reviews/CasePage";
import ClustersPage from "./features/reviews/ClustersPage";
import QueuePage from "./features/reviews/QueuePage";
import ScoreSettingsPage from "./features/settings/ScoreSettingsPage";
import ErrorBoundary from "./components/ErrorBoundary";
import { ToastProvider } from "./components/Toast";
import { ApiError, abandonFetch, getFetch, startFetch } from "./api/client";
import type { FetchRun } from "./api/types";
import { recallSearch, rememberSearch, sectionOf } from "./lib/lastSearch";
import styles from "./App.module.css";

const navigationItems = [
  { path: "/", label: "Overview", exact: true },
  { path: "/reviews", label: "Reviews", exact: false },
  { path: "/activity", label: "Activity", exact: false },
];

const FILTERED_SECTIONS = ["reviews", "activity"];
const FORCE_INITIAL_FETCH = import.meta.env.VITE_FORCE_INITIAL_FETCH === "true";
const ACTIVE_POLL_MS = 3000;
// Idle polling exists only to notice a fetch started in another tab
const IDLE_POLL_MS = 30000;

// The API's own wording stays server-side; these are the two failures a reviewer can act on.
function startFetchError(cause: unknown): string {
  if (cause instanceof ApiError && cause.status === 423) {
    return "A fetch is already running";
  }
  if (cause instanceof ApiError && cause.status === 404) {
    return "No dataset to fetch";
  }
  return "The fetch could not be started";
}

export default function App() {
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const { user, ready, signOut } = useSession();
  const [fetch, setFetch] = useState<FetchRun | null>();
  const [fetchError, setFetchError] = useState(false);
  const [fetchActionPending, setFetchActionPending] = useState(false);
  const [fetchActionError, setFetchActionError] = useState<string | null>(null);
  const [confirmingFetch, setConfirmingFetch] = useState(false);
  const fetchActionRef = useRef(false);
  const fetchRequest = useRef(0);
  const fetchLoaded = fetch !== undefined;
  const fetchRunning =
    !!fetch && ["queued", "running", "failed"].includes(fetch.status);

  useEffect(() => {
    const section = sectionOf(location.pathname);
    if (
      FILTERED_SECTIONS.includes(section) &&
      location.pathname !== "/reviews/settings"
    ) {
      rememberSearch(section, location.search);
    }
  }, [location]);

  useEffect(() => {
    // .main is the scroll container, so router scroll restoration does not reach it.
    mainRef.current?.scrollTo({ top: 0 });
  }, [location.pathname]);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    const delay = fetchRunning || fetchError ? ACTIVE_POLL_MS : IDLE_POLL_MS;

    function schedule() {
      timer = window.setTimeout(loadFetch, delay);
    }

    function loadFetch() {
      if (fetchActionRef.current) {
        schedule();
        return;
      }
      const request = ++fetchRequest.current;
      getFetch()
        .then((current) => {
          if (!active || request !== fetchRequest.current) return;
          setFetch(current);
          setFetchError(false);
          if (
            current &&
            ["queued", "running", "failed"].includes(current.status)
          ) {
            setConfirmingFetch(false);
          }
        })
        .catch(() => {
          if (active && request === fetchRequest.current) setFetchError(true);
        })
        .finally(() => {
          if (active) schedule();
        });
    }

    // Reruns when a fetch starts, cancelling the pending idle timer
    if (fetchLoaded) schedule();
    else loadFetch();

    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [fetchRunning, fetchLoaded, fetchError]);

  function beginFetch() {
    if (fetchActionPending) return;
    fetchActionRef.current = true;
    fetchRequest.current += 1;
    setFetchActionPending(true);
    setFetchActionError(null);
    startFetch()
      .then((started) => {
        setFetch(started);
        setConfirmingFetch(false);
      })
      .catch((cause: unknown) => setFetchActionError(startFetchError(cause)))
      .finally(() => {
        fetchActionRef.current = false;
        setFetchActionPending(false);
      });
  }

  function leaveFailedFetch() {
    if (!fetch || fetchActionPending) return;
    fetchActionRef.current = true;
    fetchRequest.current += 1;
    setFetchActionPending(true);
    setFetchActionError(null);
    abandonFetch(fetch.id)
      .then(setFetch)
      .catch(() => setFetchActionError("The fetch could not be abandoned"))
      .finally(() => {
        fetchActionRef.current = false;
        setFetchActionPending(false);
      });
  }

  if (fetchError) {
    return <UnreachablePage />;
  }

  if (fetch === undefined) {
    return <p className={styles.fetchState}>Loading fetch status…</p>;
  }

  if (fetch && ["queued", "running", "failed"].includes(fetch.status)) {
    return (
      <FetchPage
        fetch={fetch}
        busy={fetchActionPending}
        actionError={fetchActionError}
        onRetry={beginFetch}
        onAbandon={leaveFailedFetch}
      />
    );
  }

  const confirmation = (
    <FetchConfirmDialog
      open={confirmingFetch}
      busy={fetchActionPending}
      error={fetchActionError}
      lastCompletedAt={
        FORCE_INITIAL_FETCH ? null : (fetch?.last_completed_at ?? null)
      }
      onCancel={() => {
        if (!fetchActionPending) setConfirmingFetch(false);
      }}
      onConfirm={beginFetch}
    />
  );

  if (FORCE_INITIAL_FETCH || !fetch || !fetch.last_completed_at) {
    return (
      <>
        <FetchSetupPage
          busy={fetchActionPending}
          onRun={() => {
            setFetchActionError(null);
            setConfirmingFetch(true);
          }}
        />
        {confirmation}
      </>
    );
  }

  return (
    <ToastProvider>
      <div className={styles.shell}>
        <header className={styles.header}>
          <Link to="/" className={styles.wordmark}>
            Merge Review
          </Link>
          <nav className={styles.navigation} aria-label="Primary navigation">
            {navigationItems.map((item) => (
              <NavLink
                key={item.path}
                to={{
                  pathname: item.path,
                  search: recallSearch(sectionOf(item.path)),
                }}
                end={item.exact}
                className={({ isActive }) =>
                  isActive
                    ? `${styles.navigationLink} ${styles.activeNavigationLink}`
                    : styles.navigationLink
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <button
            type="button"
            className={styles.fetchButton}
            disabled={fetchActionPending}
            onClick={() => {
              setFetchActionError(null);
              setConfirmingFetch(true);
            }}
          >
            fetch data
          </button>
          <span className={styles.session}>
            {!ready ? null : user ? (
              <SessionMenu user={user} onSignOut={() => void signOut()} />
            ) : (
              <Link to="/login" className={styles.sessionAction}>
                sign in
              </Link>
            )}
          </span>
        </header>

        <main className={styles.main} ref={mainRef}>
          <ErrorBoundary resetKey={location.pathname}>
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/reviews" element={<QueuePage />} />
              <Route path="/reviews/settings" element={<ScoreSettingsPage />} />
              <Route path="/reviews/:caseId" element={<CasePage />} />
              <Route path="/reviews/:caseId/ids" element={<ClustersPage />} />
              <Route path="/activity" element={<ActivityPage />} />
              <Route path="/login" element={<SignInPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </ErrorBoundary>
        </main>
      </div>
      {confirmation}
    </ToastProvider>
  );
}
