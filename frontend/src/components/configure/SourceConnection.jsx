import { useState } from "react";
import DatabaseFields from "./DatabaseFields.jsx";
import { testConnection, sampleCsvUrl } from "../../api/api.js";

import { DB_FIELD_CONFIGS, DB_REQUIRED_FIELDS } from "../../constants/dbFields.js";
import {
  SOURCE_TYPES,
  SOURCE_LABELS,
  SOURCE_TYPE_OPTIONS,
  DATABASE_TYPE_OPTIONS,
} from "../../constants/sourceTypes.js";
import { openInNewTab } from "../../utils/helpers.js";
import { IconDatabase, IconInfo, IconDownload, IconCheck, IconError } from "../Icons.jsx";

export default function SourceConnection({
  config,
  onChange,
  onSourceTypeChange,
  onDbTypeChange,
  onConnDetailChange,
}) {
  const srcType = config.source_type || SOURCE_TYPES.FLAT_FILE;
  const isFlat = srcType === SOURCE_TYPES.FLAT_FILE;
  const dbType = config.databaseType || "";

  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);

  async function handleTest() {
    if (!dbType) {
      setResult({ ok: false, msg: "Select a database type first" });
      return;
    }
    const details = config.connectionDetails || {};
    const required = DB_REQUIRED_FIELDS[dbType] || [];
    const missing = required.filter((f) => !String(details[f] ?? "").trim());
    if (missing.length) {
      const labels = (DB_FIELD_CONFIGS[dbType] || [])
        .filter((f) => missing.includes(f.id))
        .map((f) => f.label);
      setResult({ ok: false, msg: `Missing: ${labels.join(", ")}` });
      return;
    }

    setTesting(true);
    setResult(null);
    const chunkSize = Number(config.chunk_size) || 50000;
    const { ok, data, error } = await testConnection(dbType, details, chunkSize);
    setResult({ ok, msg: ok ? data?.message || "Connected!" : error || "Failed" });
    setTesting(false);
  }

  return (
    <div className="card">
      <div className="card-title">
        <IconDatabase style={{ verticalAlign: "text-bottom" }} /> Source Connection <span className="badge">{SOURCE_LABELS[srcType] || srcType}</span>
      </div>

      <div className="form-group" style={{ marginBottom: "16px" }}>
        <label>Source Type</label>
        <div className="seg" role="group" aria-label="Source type">
          {SOURCE_TYPE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={`seg-opt${srcType === opt.value ? " on" : ""}`}
              onClick={() => onSourceTypeChange(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {isFlat ? (
        <div>
          <div className="alert alert-info">
            <span><IconInfo style={{ verticalAlign: "text-bottom" }} /></span>
            <span>
              Upload CSV files in <strong>File Uploads</strong> first, then select them below.
            </span>
          </div>
          <div className="csv-guidance">
            <p className="csv-guidance-title">📄 CSV Format Rules</p>
            <ul>
              <li>One CSV file must contain data for <strong>one table only</strong>.</li>
              <li>First row must contain <strong>column names</strong>.</li>
              <li>Remaining rows must contain <strong>data values</strong>.</li>
            </ul>
            <div className="csv-example">
              <code>column1,column2,column3</code>
              <code>value1,value2,value3</code>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ marginTop: "10px" }}
              onClick={() => openInNewTab(sampleCsvUrl())}
            >
              <IconDownload style={{ verticalAlign: "text-bottom" }} /> Download Sample CSV
            </button>
          </div>
        </div>
      ) : (
        <div className="form-grid">
          <div className="form-group full">
            <label htmlFor="cfg-db-type">Database Type</label>
            <select
              id="cfg-db-type"
              value={dbType}
              onChange={(e) => onDbTypeChange(e.target.value)}
            >
              {DATABASE_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="full">
            <DatabaseFields dbType={dbType} details={config.connectionDetails} onChange={onConnDetailChange} />
          </div>

          <div className="form-group">
            <label htmlFor="cfg-chunk">Chunk Size (rows)</label>
            <input
              id="cfg-chunk"
              type="number"
              min="0"
              placeholder="50000"
              value={config.chunk_size ?? ""}
              onChange={(e) => onChange({ chunk_size: e.target.value === "" ? "" : Number(e.target.value) })}
            />
            <span className="hint">0 = load entire table at once</span>
          </div>

          <div className="form-group" style={{ justifyContent: "flex-end", paddingTop: "20px" }}>
            <button type="button" className="btn btn-ghost" disabled={testing} onClick={handleTest}>
              {testing ? <span className="spinner" aria-hidden="true" /> : "🔌"} {testing ? "Testing…" : "Test Connection"}
            </button>
            {result ? (
              <div style={{ marginTop: "8px" }}>
                <span className={`conn-status ${result.ok ? "conn-ok" : "conn-err"}`}>
                  {result.ok ? <IconCheck style={{ color: "var(--teal)", verticalAlign: "text-bottom" }} /> : <IconError style={{ color: "var(--red)", verticalAlign: "text-bottom" }} />} {result.msg}
                </span>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
