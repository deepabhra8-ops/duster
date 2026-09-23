export function Table({ children }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="dtable">{children}</table>
    </div>
  );
}

export function TableEmpty({ colSpan, children }) {
  return (
    <tbody>
      <tr>
        <td colSpan={colSpan} className="dtable-empty">
          {children}
        </td>
      </tr>
    </tbody>
  );
}

export default Table;
