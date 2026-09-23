/**
 * Tabs.jsx - generic underline tab bar: a row of clickable labels, one
 * marked active with an underline + accent color. Purely a controlled
 * selector (parent owns which tab is active and what that means).
 *
 * `tabs` is [{ id, label }, ...]; `active` is the selected id; `onChange`
 * fires with the clicked tab's id.
 */
export default function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          className={`tab${active === tab.id ? " on" : ""}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
