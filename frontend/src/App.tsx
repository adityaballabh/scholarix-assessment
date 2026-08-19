import { Link, Navigate, NavLink, Route, Routes } from "react-router-dom";
import OverviewPage from "./features/overview/OverviewPage";
import PlaceholderPage from "./features/placeholder/PlaceholderPage";
import QueuePage from "./features/reviews/QueuePage";
import styles from "./App.module.css";

const navigationItems = [
  { path: "/", label: "Overview", exact: true },
  { path: "/reviews", label: "Reviews", exact: false },
  { path: "/activity", label: "Activity", exact: false },
];

export default function App() {
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Link to="/" className={styles.wordmark}>
          MergeReview
        </Link>
        <nav className={styles.navigation} aria-label="Primary navigation">
          {navigationItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
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
          <Route
            path="/reviews/:caseId"
            element={<PlaceholderPage section="Review" />}
          />
          <Route
            path="/activity/*"
            element={<PlaceholderPage section="Activity" />}
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
