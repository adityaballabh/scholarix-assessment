import { Navigate, useNavigate } from "react-router-dom";

import { useSession } from "./AuthProvider";
import { SignInForm } from "./SignInForm";
import styles from "./SignInPage.module.css";

export default function SignInPage() {
  const navigate = useNavigate();
  const { user, setUser } = useSession();

  if (user) return <Navigate to="/" replace />;

  return (
    <div className={styles.page}>
      <SignInForm
        autoFocus
        onSignedIn={(signedIn) => {
          setUser(signedIn);
          navigate("/", { replace: true });
        }}
      />
    </div>
  );
}
