import { useState } from "react";
import {
  Database,
  Eye,
  EyeOff,
  Hash,
  KeyRound,
  Lock,
  Server,
  Shield,
  User,
} from "lucide-react";

import { DB_FIELD_CONFIGS } from "../../constants/dbFields.js";

const FIELD_ICONS = {
  host: Server,
  server_hostname: Server,
  port: Hash,
  username: User,
  password: Lock,
  access_token: KeyRound,
  security_token: KeyRound,
  database: Database,
  dataset_id: Database,
  catalog: Database,
  schema: Database,
  warehouse: Database,
  ssl_mode: Shield,
  ssl_enabled: Shield,
  encrypt: Shield,
};

export default function DatabaseFields({ dbType, details = {}, onChange, enhanced = false, readOnly = false }) {
  const [revealed, setRevealed] = useState({});

  if (!dbType) return null;
  const fields = DB_FIELD_CONFIGS[dbType] || [];

  return (
    <div className={`form-grid${enhanced ? " njm-db-grid" : ""}`}>
      {fields.map((field) => {
        const id = `db-field-${field.id}`;
        const saved = details[field.id];
        const Icon = enhanced ? FIELD_ICONS[field.id] : null;
        const isPassword = field.type === "password";
        const isRevealed = Boolean(revealed[field.id]);

        const label = enhanced ? (
          <>
            {field.label}
            {field.required ? null : <span className="njm-optional"> (Optional)</span>}
          </>
        ) : (
          field.label + (field.required ? "" : " (optional)")
        );

        const control =
          field.type === "select" ? (
            <select
              id={id}
              value={saved ?? (field.options?.[0]?.value ?? "")}
              onChange={(e) => onChange(field.id, e.target.value)}
              disabled={readOnly}
            >
              {(field.options || []).map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          ) : field.type === "checkbox" ? (
            <input
              id={id}
              type="checkbox"
              style={{ width: "18px" }}
              checked={Boolean(saved ?? field.default ?? false)}
              onChange={(e) => onChange(field.id, e.target.checked)}
              disabled={readOnly}
            />
          ) : field.type === "textarea" ? (
            <textarea
              id={id}
              rows={5}
              placeholder={field.placeholder || ""}
              style={{ fontFamily: "monospace", fontSize: "12px" }}
              value={saved ?? ""}
              onChange={(e) => onChange(field.id, e.target.value)}
              readOnly={readOnly}
            />
          ) : (
            <input
              id={id}
              type={
                isPassword
                  ? isRevealed
                    ? "text"
                    : "password"
                  : field.type === "number"
                    ? "number"
                    : "text"
              }
              placeholder={field.placeholder || (field.default != null ? String(field.default) : "")}
              value={saved ?? (field.type === "number" ? (field.default ?? "") : "")}
              onChange={(e) => onChange(field.id, e.target.value)}
              readOnly={readOnly}
            />
          );

        return (
          <div key={field.id} className={`form-group${field.full ? " full" : ""}`}>
            <label htmlFor={id} className={enhanced ? `njm-label${field.required ? " is-required" : ""}` : undefined}>
              {label}
            </label>

            {enhanced && (Icon || isPassword) && field.type !== "checkbox" && field.type !== "textarea" ? (
              <span className="njm-input-wrap">
                {Icon ? (
                  <span className="njm-input-icon" aria-hidden="true">
                    <Icon size={15} />
                  </span>
                ) : null}
                {control}
                {isPassword ? (
                  <button
                    type="button"
                    className="njm-reveal"
                    onClick={() => setRevealed((r) => ({ ...r, [field.id]: !r[field.id] }))}
                    aria-label={isRevealed ? "Hide password" : "Show password"}
                    title={isRevealed ? "Hide password" : "Show password"}
                  >
                    {isRevealed ? <Eye size={15} aria-hidden="true" /> : <EyeOff size={15} aria-hidden="true" />}
                  </button>
                ) : null}
              </span>
            ) : (
              control
            )}

            {field.hint ? (
              <span className={enhanced ? "njm-hint" : "hint"}>{field.hint}</span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
