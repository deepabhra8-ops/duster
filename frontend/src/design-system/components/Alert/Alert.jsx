const ICONS = {
  success: (
    <svg className="dalert-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12l3 3 5-6" />
    </svg>
  ),
  warning: (
    <svg className="dalert-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 3l10 18H2z" />
      <path d="M12 10v4M12 17h.01" />
    </svg>
  ),
  danger: (
    <svg className="dalert-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5M12 16h.01" />
    </svg>
  ),
};

export function Alert({ tone = "danger", title, children }) {
  return (
    <div className={`dalert dalert-${tone}`} role={tone === "danger" ? "alert" : "status"}>
      {ICONS[tone]}
      <div>
        <div className="dalert-title">{title}</div>
        <div className="dalert-body">{children}</div>
      </div>
    </div>
  );
}

export default Alert;
