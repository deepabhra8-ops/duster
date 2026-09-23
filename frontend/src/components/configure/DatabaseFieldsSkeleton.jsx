/**
 * DatabaseFieldsSkeleton.jsx - shimmer placeholder for DatabaseFields, shown
 * while a connection's decrypted details are being fetched (GET
 * .../reveal). Matches the real grid's field count per db type so the
 * layout doesn't jump when the fields swap in.
 */
import { DB_FIELD_CONFIGS } from "../../constants/dbFields.js";

export default function DatabaseFieldsSkeleton({ dbType }) {
  const count = DB_FIELD_CONFIGS[dbType]?.length || 6;

  return (
    <div className="njm-db-grid">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="form-group">
          <div className="skeleton skeleton-text sm" />
          <div className="skeleton skeleton-tile" />
        </div>
      ))}
    </div>
  );
}
