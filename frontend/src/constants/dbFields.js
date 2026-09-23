export const DB_FIELD_CONFIGS = {
  postgresql: [
    { id: "host", label: "Host", type: "text", placeholder: "db.example.com", required: true },
    { id: "port", label: "Port", type: "number", default: 5432, required: true },
    { id: "username", label: "Username", type: "text", placeholder: "postgres", required: true },
    { id: "password", label: "Password", type: "password", placeholder: "••••••••", required: true },
    {
      id: "database",
      label: "Database Name",
      type: "text",
      placeholder: "mydb (optional)",
      required: false,
      hint: "Optional - leave blank to connect to default database",
    },
    {
      id: "ssl_mode",
      label: "SSL Mode",
      type: "select",
      required: false,
      options: [
        { value: "require", label: "require" },
        { value: "disable", label: "disable" },
        { value: "verify-full", label: "verify-full" },
      ],
    },
  ],

  mssql: [
    { id: "host", label: "Server Host", type: "text", placeholder: "server.database.windows.net", required: true },
    { id: "port", label: "Port", type: "number", default: 1433, required: true },
    { id: "username", label: "Username", type: "text", required: true },
    { id: "password", label: "Password", type: "password", required: true },
    { id: "database", label: "Database Name", type: "text", required: true, hint: "Required for SQL Server" },
    {
      id: "encrypt",
      label: "Encrypt",
      type: "select",
      options: [
        { value: "yes", label: "yes" },
        { value: "no", label: "no" },
      ],
    },
    {
      id: "trust_server_certificate",
      label: "Trust Server Certificate",
      type: "select",
      options: [
        { value: "no", label: "no" },
        { value: "yes", label: "yes" },
      ],
    },
  ],

  azure_sql: [
    { id: "host", label: "Server Host", type: "text", placeholder: "myserver.database.windows.net", required: true },
    { id: "port", label: "Port", type: "number", default: 1433, required: true },
    { id: "username", label: "Username", type: "text", required: true },
    { id: "password", label: "Password", type: "password", required: true },
    { id: "database", label: "Database Name", type: "text", required: true },
    {
      id: "encrypt",
      label: "Encrypt",
      type: "select",
      options: [
        { value: "yes", label: "yes" },
        { value: "no", label: "no" },
      ],
    },
    {
      id: "trust_server_certificate",
      label: "Trust Server Certificate",
      type: "select",
      options: [
        { value: "no", label: "no" },
        { value: "yes", label: "yes" },
      ],
    },
  ],

  mysql: [
    { id: "host", label: "Host", type: "text", placeholder: "localhost", required: true },
    { id: "port", label: "Port", type: "number", default: 3306, required: true },
    { id: "username", label: "Username", type: "text", required: true },
    { id: "password", label: "Password", type: "password", required: true },
    { id: "database", label: "Database Name", type: "text", placeholder: "mydb (optional)", required: false },
    { id: "ssl_enabled", label: "SSL Enabled", type: "checkbox" },
  ],

  oracle: [
    { id: "host", label: "Host", type: "text", required: true },
    { id: "port", label: "Port", type: "number", default: 1521, required: true },
    { id: "username", label: "Username", type: "text", required: true },
    { id: "password", label: "Password", type: "password", required: true },
    { id: "service_name", label: "Service Name / SID", type: "text", required: true },
    {
      id: "connection_mode",
      label: "Connection Mode",
      type: "select",
      options: [
        { value: "service_name", label: "Service Name" },
        { value: "sid", label: "SID" },
      ],
    },
  ],

  snowflake: [
    { id: "account", label: "Account Identifier", type: "text", placeholder: "myorg-myaccount", required: true },
    { id: "username", label: "Username", type: "text", required: true },
    { id: "password", label: "Password", type: "password", required: true },
    { id: "warehouse", label: "Warehouse", type: "text", required: true },
    { id: "database", label: "Database", type: "text", required: true },
    { id: "schema", label: "Schema", type: "text", required: true },
    { id: "role", label: "Role", type: "text", placeholder: "optional", required: false },
  ],

  databricks: [
    { id: "server_hostname", label: "Server Hostname", type: "text", placeholder: "abc.azuredatabricks.net", required: true, full: true },
    { id: "http_path", label: "HTTP Path", type: "text", placeholder: "/sql/1.0/warehouses/...", required: true, full: true },
    { id: "access_token", label: "Access Token", type: "password", required: true, full: true },
    { id: "catalog", label: "Catalog", type: "text", placeholder: "optional", required: false },
    { id: "schema", label: "Schema", type: "text", placeholder: "optional", required: false },
  ],

  redshift: [
    { id: "host", label: "Host", type: "text", required: true },
    { id: "port", label: "Port", type: "number", default: 5439, required: true },
    { id: "username", label: "Username", type: "text", required: true },
    { id: "password", label: "Password", type: "password", required: true },
    { id: "database", label: "Database Name", type: "text", required: true },
    { id: "ssl_enabled", label: "SSL Enabled", type: "checkbox" },
  ],

  bigquery: [
    { id: "project_id", label: "Project ID", type: "text", required: true },
    { id: "dataset_id", label: "Dataset ID", type: "text", required: true },
    {
      id: "service_account_json",
      label: "Service Account JSON",
      type: "textarea",
      required: true,
      full: true,
      placeholder: '{\n  "type": "service_account",\n  "project_id": "...",\n  ...\n}',
      hint: "Paste the full service account JSON credentials",
    },
  ],

  salesforce: [
    { id: "username", label: "Username", type: "text", placeholder: "user@company.com", required: true },
    { id: "password", label: "Password", type: "password", placeholder: "••••••••", required: true },
    {
      id: "security_token",
      label: "Security Token",
      type: "password",
      placeholder: "••••••••",
      required: true,
      hint: "Salesforce → Settings → Reset My Security Token",
    },
    {
      id: "domain",
      label: "Login URL",
      type: "text",
      placeholder: "login.salesforce.com",
      required: true,
      hint: "Use test.salesforce.com for a sandbox org",
    },
  ],
};

export const DB_REQUIRED_FIELDS = {
  postgresql: ["host", "username", "password"],
  mssql: ["host", "username", "password", "database"],
  azure_sql: ["host", "username", "password", "database"],
  mysql: ["host", "username", "password"],
  oracle: ["host", "username", "password", "service_name"],
  snowflake: ["account", "username", "password", "warehouse", "database", "schema"],
  databricks: ["server_hostname", "http_path", "access_token"],
  redshift: ["host", "username", "password", "database"],
  bigquery: ["project_id", "dataset_id", "service_account_json"],
  salesforce: ["username", "password", "security_token", "domain"],
};
