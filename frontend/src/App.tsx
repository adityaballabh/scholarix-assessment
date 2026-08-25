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
import AuditConfirmDialog from "./features/audit/AuditConfirmDialog";
import AuditPage from "./features/audit/AuditPage";
import AuditSetupPage from "./features/audit/AuditSetupPage";
import OverviewPage from "./features/overview/OverviewPage";
import CasePage from "./features/reviews/CasePage";
import ClustersPage from "./features/reviews/ClustersPage";
import QueuePage from "./features/reviews/QueuePage";
import ScoreSettingsPage from "./features/settings/ScoreSettingsPage";
import { ToastProvider } from "./components/Toast";
import { abandonAudit, getAudit, startAudit } from "./api/client";
import type { AuditRun } from "./api/types";
import { recallSearch, rememberSearch, sectionOf } from "./lib/lastSearch";
import styles from "./App.module.css";

const navigationItems = [
  { path: "/", label: "Overview", exact: true },
  { path: "/reviews", label: "Reviews", exact: false },
  { path: "/activity", label: "Activity", exact: false },
];

const FILTERED_SECTIONS = ["reviews", "activity"];
const FORCE_INITIAL_AUDIT = import.meta.env.VITE_FORCE_INITIAL_AUDIT === "true";

export default function App() {
  const location = useLocation();
  const [audit, setAudit] = useState<AuditRun | null>();
  const [auditError, setAuditError] = useState(false);
  const [auditActionPending, setAuditActionPending] = useState(false);
  const [auditActionError, setAuditActionError] = useState<string | null>(null);
  const [confirmingAudit, setConfirmingAudit] = useState(false);
  const auditActionRef = useRef(false);
  const auditRequest = useRef(0);

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
    let active = true;
    let timer: number | undefined;

    function loadAudit() {
      if (auditActionRef.current) {
        timer = window.setTimeout(loadAudit, 2000);
        return;
      }
      const request = ++auditRequest.current;
      getAudit()
        .then((current) => {
          if (!active || request !== auditRequest.current) return;
          setAudit(current);
          setAuditError(false);
          if (
            current &&
            ["queued", "running", "failed"].includes(current.status)
          ) {
            setConfirmingAudit(false);
          }
        })
        .catch(() => {
          if (active && request === auditRequest.current) setAuditError(true);
        })
        .finally(() => {
          if (active) timer = window.setTimeout(loadAudit, 2000);
        });
    }

    loadAudit();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  function runAudit() {
    if (auditActionPending) return;
    auditActionRef.current = true;
    auditRequest.current += 1;
    setAuditActionPending(true);
    setAuditActionError(null);
    startAudit()
      .then((started) => {
        setAudit(started);
        setConfirmingAudit(false);
      })
      .catch(() => setAuditActionError("The audit could not be started."))
      .finally(() => {
        auditActionRef.current = false;
        setAuditActionPending(false);
      });
  }

  function leaveFailedAudit() {
    if (!audit || auditActionPending) return;
    auditActionRef.current = true;
    auditRequest.current += 1;
    setAuditActionPending(true);
    setAuditActionError(null);
    abandonAudit(audit.id)
      .then(setAudit)
      .catch(() => setAuditActionError("The audit could not be abandoned."))
      .finally(() => {
        auditActionRef.current = false;
        setAuditActionPending(false);
      });
  }

  if (auditError) {
    return (
      <p className={styles.auditState}>Audit status could not be loaded.</p>
    );
  }

  if (audit === undefined) {
    return <p className={styles.auditState}>Loading audit status…</p>;
  }

  if (audit && ["queued", "running", "failed"].includes(audit.status)) {
    return (
      <AuditPage
        audit={audit}
        busy={auditActionPending}
        actionError={auditActionError}
        onRetry={runAudit}
        onAbandon={leaveFailedAudit}
      />
    );
  }

  const confirmation = (
    <AuditConfirmDialog
      open={confirmingAudit}
      busy={auditActionPending}
      error={auditActionError}
      lastCompletedAt={
        FORCE_INITIAL_AUDIT ? null : (audit?.last_completed_at ?? null)
      }
      onCancel={() => {
        if (!auditActionPending) setConfirmingAudit(false);
      }}
      onConfirm={runAudit}
    />
  );

  if (FORCE_INITIAL_AUDIT || !audit || !audit.last_completed_at) {
    return (
      <>
        <AuditSetupPage
          busy={auditActionPending}
          onRun={() => {
            setAuditActionError(null);
            setConfirmingAudit(true);
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
            className={styles.auditButton}
            disabled={auditActionPending}
            onClick={() => {
              setAuditActionError(null);
              setConfirmingAudit(true);
            }}
          >
            fetch data
          </button>
          <span className={styles.session}>aditya</span>
        </header>

        <main className={styles.main}>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/reviews" element={<QueuePage />} />
            <Route path="/reviews/settings" element={<ScoreSettingsPage />} />
            <Route path="/reviews/:caseId" element={<CasePage />} />
            <Route path="/reviews/:caseId/ids" element={<ClustersPage />} />
            <Route path="/activity" element={<ActivityPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
      {confirmation}
    </ToastProvider>
  );
}
