/**
 * DatabaseFields.jsx - Dynamic connection-detail form.
 *
 * Renders the field set for the selected database type (from
 * DB_FIELD_CONFIGS) and reports edits via `onChange(fieldId, value)`.
 * Values are read from `details` (config.connectionDetails).
 *
 * Two callers with different chrome, hence `enhanced`:
 *
 *   - SourceConnection.jsx (the Configure page) renders the plain form it
 *     always did. Default, so that page is untouched.
 *
 *   - ConnectionWizardModal.jsx passes `enhanced`, which adds a leading icon
 *     per field, a show/hide toggle on passwords, and "(Optional)" as a
 *     separate muted span so required fields can carry a red asterisk from
 *     CSS instead of the label text. That keeps the wizard's fields looking
 *     like the New Job wizards' without a second copy of this component - the
 *     field list, the value plumbing and the widget-per-type switch are the
 *     part worth sharing, and they are identical either way.
 */
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

/* Matched on field id, which is stable across database types in
   constants/dbFields.js - every type calls its host "host", its user
   "username", and so on. A field with no entry simply gets no icon rather
   than a generic one, which would add noise without adding meaning. */
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
  /* Which password fields are currently revealed, by field id. Local because
     it is pure presentation - nothing outside this form needs to know, and it
     must reset when the form unmounts rather than persist per connection. */
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

        /* Plain mode keeps the original single-string label. Enhanced mode
           splits it so "(Optional)" can be muted and the required marker can
           be CSS, matching the New Job wizards. */
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
