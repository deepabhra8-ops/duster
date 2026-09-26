import { Lock } from "lucide-react";

/** The static-IP allowlist reminder shown at the bottom of every connector's setup form. */
export function SecurityNote({ children }) {
  return (
    <div className="security-note">
      <Lock aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export default SecurityNote;
