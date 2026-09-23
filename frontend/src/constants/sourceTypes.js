export const SOURCE_TYPES = {
  FLAT_FILE: "flat_file",
  DATABASE: "database",
};

export const SOURCE_LABELS = {
  [SOURCE_TYPES.FLAT_FILE]: "Flat File",
  [SOURCE_TYPES.DATABASE]: "Database Connection",
};

export const SOURCE_TYPE_OPTIONS = [
  { value: SOURCE_TYPES.FLAT_FILE, label: SOURCE_LABELS[SOURCE_TYPES.FLAT_FILE] },
  { value: SOURCE_TYPES.DATABASE, label: SOURCE_LABELS[SOURCE_TYPES.DATABASE] },
];

export const DATABASE_TYPE_OPTIONS = [
  { value: "", label: "- Select database type -" },
  { value: "postgresql", label: "PostgreSQL" },
  { value: "mssql", label: "Microsoft SQL Server" },
  { value: "mysql", label: "MySQL" },
  { value: "oracle", label: "Oracle" },
  { value: "snowflake", label: "Snowflake" },
  { value: "databricks", label: "Databricks SQL Warehouse" },
  { value: "azure_sql", label: "Azure SQL Database" },
  { value: "redshift", label: "Redshift" },
  { value: "bigquery", label: "BigQuery" },
  { value: "salesforce", label: "Salesforce" },
];
