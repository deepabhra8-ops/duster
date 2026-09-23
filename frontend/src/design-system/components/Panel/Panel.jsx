export function Panel({ title, headerAction, flush = false, children }) {
  return (
    <div className="panel">
      {title ? (
        <div className="panel-header">
          <span className="panel-title">{title}</span>
          {headerAction || null}
        </div>
      ) : null}
      <div className={flush ? "panel-body-flush" : "panel-body"}>{children}</div>
    </div>
  );
}

export default Panel;
