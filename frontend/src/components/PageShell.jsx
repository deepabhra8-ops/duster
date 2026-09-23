/**
 * PageShell.jsx - Main content region.
 *
 * Wraps content in <main class="main"> and renders whichever page matches
 * the current URL via an <Outlet/> - the route table itself lives in
 * App.jsx now, alongside the "/login" route this layout doesn't apply to
 * (see App.jsx's AuthenticatedLayout).
 *
 * The sidebar is a fixed width now (no collapse toggle), so `.main`'s
 * offset in global.css is a single static value - no per-state class needed
 * here anymore.
 */
import { Outlet } from "react-router-dom";

export default function PageShell({ banner }) {
  return (
    /* tabIndex={-1} so the skip link in App.jsx can move focus here - a bare
       id is a scroll target but not a focus target. */
    <main className="main" id="main-content" tabIndex={-1}>
      {banner}
      <Outlet />
    </main>
  );
}
