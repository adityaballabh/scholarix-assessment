import { useNavigate } from "react-router-dom";

import { useSession } from "./AuthProvider";
import { SignInForm } from "./SignInForm";
import styles from "./SignInPage.module.css";

export default function SignInPage() {
  const navigate = useNavigate();
  const { user, setUser } = useSession();

  return (
    <div className={styles.page}>
      {user ? (
        <p className={styles.signedIn}>Signed in as {user.display_name}.</p>
      ) : (
        <>
          <SignInForm
            autoFocus
            onSignedIn={(signedIn) => {
              setUser(signedIn);
              navigate("/reviews");
            }}
          />
        </>
      )}
    </div>
  );
}
