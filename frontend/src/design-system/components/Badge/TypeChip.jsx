export function TypeChip({ className = "", children }) {
  const classes = ["type-chip", className].filter(Boolean).join(" ");
  return <span className={classes}>{children}</span>;
}

export default TypeChip;
