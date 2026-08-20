import { useEffect } from "react";
import {
  Link,
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import ActivityPage from "./features/activity/ActivityPage";
import OverviewPage from "./features/overview/OverviewPage";
import CasePage from "./features/reviews/CasePage";
import ClustersPage from "./features/reviews/ClustersPage";
import QueuePage from "./features/reviews/QueuePage";
import { ToastProvider } from "./components/Toast";
import { recallSearch, rememberSearch, sectionOf } from "./lib/lastSearch";
import styles from "./App.module.css";

const navigationItems = [
  { path: "/", label: "Overview", exact: true },
  { path: "/reviews", label: "Reviews", exact: false },
  { path: "/activity", label: "Activity", exact: false },
];

const FILTERED_SECTIONS = ["reviews", "activity"];

export default function App() {
  const location = useLocation();

  useEffect(() => {
    const section = sectionOf(location.pathname);
    if (FILTERED_SECTIONS.includes(section)) {
      rememberSearch(section, location.search);
    }
  }, [location]);

  return (
    <ToastProvider>
      <div className={styles.shell}>
        <header className={styles.header}>
          <Link to="/" className={styles.wordmark}>
            MergeReview
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
          <span className={styles.session}>aditya</span>
        </header>

        <main className={styles.main}>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/reviews" element={<QueuePage />} />
            <Route path="/reviews/:caseId" element={<CasePage />} />
            <Route path="/reviews/:caseId/ids" element={<ClustersPage />} />
            <Route path="/activity" element={<ActivityPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </ToastProvider>
  );
}
