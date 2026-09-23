import { Outlet } from "react-router-dom";

export default function PageShell({ banner }) {
  return (
    <main className="main" id="main-content" tabIndex={-1}>
      {banner}
      <Outlet />
    </main>
  );
}
