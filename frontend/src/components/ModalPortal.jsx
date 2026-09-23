/**
 * ModalPortal.jsx - renders a dialog into <body> instead of where it is written.
 *
 * Every modal in this app is authored inside the page that opens it, which for
 * a `position: fixed` overlay is a standing hazard rather than a detail. A
 * fixed element resolves `inset: 0` against the viewport ONLY while no ancestor
 * creates a containing block for it - and `transform`, `filter`, `perspective`,
 * `backdrop-filter`, `will-change` and `contain` all do, on any ancestor, at any
 * depth. So does a CSS animation of those properties while it runs.
 *
 * That is not hypothetical here. `.main` carried a decorative `fadeIn` whose
 * keyframes animated `transform: translateY`, with `animation-fill-mode:
 * forwards` pinning the final transform in place permanently. Every dialog in
 * the app then sized itself to `.main` rather than the window: indented by the
 * sidebar, pushed below the topbar, as tall as the page content - so the
 * backdrop dimmed only the content column while the topbar and sidebar stayed
 * bright, and `margin: auto` centred the box in a full-page-height box, putting
 * it well below the middle of the screen.
 *
 * Deleting that animation fixed it, but left the trap armed: the next person to
 * add a hover lift, a parallax, or a `will-change` hint anywhere above a page's
 * content would break every dialog again, in a way that looks like a modal bug
 * and is nothing of the kind. Portalling to <body> removes the class of bug
 * rather than the instance - there are no ancestors left to create a containing
 * block, and no stacking context to trap the overlay's z-index beneath the
 * topbar.
 *
 * Nothing else changes: React events still propagate through the portal to the
 * component that rendered it, so `onClose` handlers, form state and the
 * backdrop's own click-to-close all behave exactly as before.
 */
import { createPortal } from "react-dom";

export default function ModalPortal({ children }) {
  // `document` is absent during any server-side or test-time render without a
  // DOM; falling back to rendering in place keeps those environments working.
  if (typeof document === "undefined") return children;

  return createPortal(children, document.body);
}
