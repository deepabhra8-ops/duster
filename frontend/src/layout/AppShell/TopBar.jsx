import { LogOut } from "lucide-react";
import { Button } from "../../design-system/components/index.js";
import { useAuth } from "../../hooks/useAuth.js";
import "./TopBar.css";

export function TopBar() {
  const { username, logout } = useAuth();

  return (
    <header className="app-topbar">
      <div className="app-topbar-brand">
        <img src="/icons/dq-brand.svg" width={24} height={24} alt="" aria-hidden="true" />
        <span className="app-topbar-title">Control Room</span>
      </div>

      <div className="app-topbar-user">
        {username ? <span className="app-topbar-username">{username}</span> : null}
        <Button register="ghost" size="xs" onClick={logout}>
          <LogOut size={14} aria-hidden="true" />
          Log out
        </Button>
      </div>
    </header>
  );
}

export default TopBar;
