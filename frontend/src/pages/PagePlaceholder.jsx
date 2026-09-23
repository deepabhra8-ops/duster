/**
 * PagePlaceholder.jsx - A deliberately empty page.
 *
 * Stands in for a destination whose content has not been designed yet, so the
 * navigation that leads to it can be built and judged first. It renders no
 * visible content. `label` names the region for screen readers only.
 *
 * Swap the route in App.jsx for the real page when it exists.
 */
export default function PagePlaceholder({ label }) {
  return <section aria-label={label} />;
}
