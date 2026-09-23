export function Tabs({ tabs, activeId, onChange }) {
  return (
    <div className="dtabs">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`dtab${tab.id === activeId ? " is-active" : ""}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export default Tabs;
