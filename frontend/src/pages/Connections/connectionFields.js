/**
 * Editable field groups per connector db_type, mirroring the field names/labels/options each
 * dedicated NewConnection/*FormPage.jsx already uses (which mirror each backend connector's
 * `required_fields` — see backend/services/connectors/*.py). Each entry is a list of "rows";
 * a row with two fields renders as a `.sheet-field-row` pair, a row with one field renders
 * full-width — same layout the create-connection forms use. Used by EditConnectionSheet to
 * build a generic edit form without a bespoke screen per connector.
 */
export const CONNECTION_FIELD_GROUPS = {
  postgresql: [
    [{ name: "host", label: "Host" }, { name: "port", label: "Port" }],
    [{ name: "database", label: "Database" }],
    [{ name: "username", label: "Username" }, { name: "password", label: "Password", type: "password" }],
    [{ name: "ssl_mode", label: "SSL mode", options: ["require", "verify-full", "disable"] }],
  ],
  mysql: [
    [{ name: "host", label: "Host" }, { name: "port", label: "Port" }],
    [{ name: "database", label: "Database" }],
    [{ name: "username", label: "Username" }, { name: "password", label: "Password", type: "password" }],
    [{ name: "ssl_enabled", label: "SSL", options: ["Enabled (recommended)", "Disabled"] }],
  ],
  mssql: [
    [{ name: "host", label: "Host" }, { name: "port", label: "Port" }],
    [{ name: "database", label: "Database" }],
    [{ name: "username", label: "Username" }, { name: "password", label: "Password", type: "password" }],
    [
      { name: "encrypt", label: "Encrypt", options: ["yes", "no"] },
      { name: "trust_server_certificate", label: "Trust server certificate", options: ["no", "yes"] },
    ],
  ],
  oracle: [
    [{ name: "host", label: "Host" }, { name: "port", label: "Port" }],
    [
      { name: "connection_mode", label: "Connect using", options: ["service_name", "sid"] },
      { name: "identifier", label: "Service name / SID" },
    ],
    [{ name: "username", label: "Username" }, { name: "password", label: "Password", type: "password" }],
  ],
  azure_sql: [
    [{ name: "host", label: "Server" }, { name: "port", label: "Port" }],
    [{ name: "database", label: "Database" }],
    [{ name: "username", label: "Username" }, { name: "password", label: "Password", type: "password" }],
    [
      { name: "encrypt", label: "Encrypt", options: ["yes", "no"] },
      { name: "trust_server_certificate", label: "Trust server certificate", options: ["no", "yes"] },
    ],
  ],
  snowflake: [
    [{ name: "account", label: "Account identifier" }, { name: "warehouse", label: "Warehouse" }],
    [{ name: "database", label: "Database" }, { name: "schema", label: "Schema" }],
    [{ name: "username", label: "Username" }, { name: "password", label: "Password", type: "password" }],
    [{ name: "role", label: "Role (optional)" }],
  ],
  bigquery: [
    [{ name: "project_id", label: "Project ID" }, { name: "dataset_id", label: "Dataset ID" }],
    [{ name: "service_account_json", label: "Service account JSON key", type: "textarea" }],
  ],
  redshift: [
    [{ name: "host", label: "Host (cluster endpoint)" }, { name: "port", label: "Port" }],
    [{ name: "database", label: "Database" }],
    [{ name: "username", label: "Username" }, { name: "password", label: "Password", type: "password" }],
    [{ name: "ssl", label: "SSL", options: ["Enabled (recommended)", "Disabled"] }],
  ],
  databricks: [
    [{ name: "server_hostname", label: "Server hostname" }],
    [{ name: "http_path", label: "HTTP path" }],
    [{ name: "access_token", label: "Access token", type: "password" }],
    [{ name: "catalog", label: "Catalog (optional)" }, { name: "schema", label: "Schema (optional)" }],
  ],
  salesforce: [
    [{ name: "username", label: "Username" }],
    [{ name: "password", label: "Password", type: "password" }, { name: "security_token", label: "Security token", type: "password" }],
    [{ name: "domain", label: "Login domain", options: ["login", "test"] }],
  ],
};

export function fieldsForDbType(dbType) {
  return CONNECTION_FIELD_GROUPS[dbType] || [];
}
