/**
 * The "Add connection" catalog: every source Duster could eventually support, grouped the
 * same way the Connections list page groups existing connections. Every connector with a
 * real backend implementation (see backend/services/connectors/*.py) now has a dedicated
 * form page (per the "one screen per connector, not a shared template" design) and is
 * `status: "available"`; everything else is `status: "coming-soon"` and its catalog tile is
 * disabled rather than pointed at a mismatched form. dbt Cloud stays "available" pointing at
 * its existing sample-only form since it has UI but no backend connector yet.
 *
 * Entries that map to a real backend connector use that connector's actual db_type as `id`;
 * the rest (no backend connector exists yet) are illustrative catalog entries only.
 */
export const CONNECTOR_CATEGORIES = [
  "Warehouses & lakehouses",
  "Databases",
  "Lakes & query engines",
  "Transformation & orchestration",
  "BI & dashboards",
  "SaaS & data catalogs",
];

export const CONNECTOR_CATALOG = [
  // Warehouses & lakehouses
  { id: "snowflake", name: "Snowflake", icon: "SNOW", category: "Warehouses & lakehouses", caption: "Warehouse", status: "available", route: "/connections/new/snowflake" },
  { id: "bigquery", name: "BigQuery", icon: "BQ", category: "Warehouses & lakehouses", caption: "Warehouse", status: "available", route: "/connections/new/bigquery" },
  { id: "redshift", name: "Redshift", icon: "RS", category: "Warehouses & lakehouses", caption: "Warehouse", status: "available", route: "/connections/new/redshift" },
  { id: "databricks", name: "Databricks", icon: "DBX", category: "Warehouses & lakehouses", caption: "Lakehouse", status: "available", route: "/connections/new/databricks" },

  // Databases
  { id: "postgresql", name: "PostgreSQL", icon: "PG", category: "Databases", caption: "Database", status: "available", route: "/connections/new/postgres" },
  { id: "mysql", name: "MySQL", icon: "MY", category: "Databases", caption: "Database", status: "available", route: "/connections/new/mysql" },
  { id: "mssql", name: "SQL Server", icon: "MSS", category: "Databases", caption: "Database", status: "available", route: "/connections/new/mssql" },
  { id: "oracle", name: "Oracle", icon: "ORA", category: "Databases", caption: "Database", status: "available", route: "/connections/new/oracle" },
  { id: "azure_sql", name: "Azure SQL", icon: "AZ", category: "Databases", caption: "Database", status: "available", route: "/connections/new/azure-sql" },

  // Lakes & query engines
  { id: "s3", name: "Amazon S3", icon: "S3", category: "Lakes & query engines", caption: "Object storage", status: "coming-soon" },
  { id: "kafka", name: "Kafka", icon: "KFK", category: "Lakes & query engines", caption: "Streaming", status: "coming-soon" },
  { id: "athena", name: "Athena", icon: "ATH", category: "Lakes & query engines", caption: "Query engine", status: "coming-soon" },

  // Transformation & orchestration
  { id: "dbt-cloud", name: "dbt Cloud", icon: "DBT", category: "Transformation & orchestration", caption: "Orchestration", status: "available", route: "/connections/new/dbt-cloud" },
  { id: "airflow", name: "Airflow", icon: "AF", category: "Transformation & orchestration", caption: "Orchestration", status: "coming-soon" },
  { id: "fivetran", name: "Fivetran", icon: "FVT", category: "Transformation & orchestration", caption: "Ingestion", status: "coming-soon" },
  { id: "prefect", name: "Prefect", icon: "PFT", category: "Transformation & orchestration", caption: "Orchestration", status: "coming-soon" },

  // BI & dashboards
  { id: "tableau", name: "Tableau", icon: "TAB", category: "BI & dashboards", caption: "BI & dashboards", status: "coming-soon" },
  { id: "looker", name: "Looker", icon: "LKR", category: "BI & dashboards", caption: "BI & dashboards", status: "coming-soon" },
  { id: "powerbi", name: "Power BI", icon: "PBI", category: "BI & dashboards", caption: "BI & dashboards", status: "coming-soon" },
  { id: "metabase", name: "Metabase", icon: "MTB", category: "BI & dashboards", caption: "BI & dashboards", status: "coming-soon" },

  // SaaS & data catalogs
  { id: "salesforce", name: "Salesforce", icon: "SF", category: "SaaS & data catalogs", caption: "CRM", status: "available", route: "/connections/new/salesforce" },
];

export const POPULAR_CONNECTOR_IDS = ["postgresql", "snowflake", "bigquery", "mysql", "redshift", "dbt-cloud", "salesforce", "databricks"];

export function connectorsByCategory(category) {
  return CONNECTOR_CATALOG.filter((c) => c.category === category);
}

export function popularConnectors() {
  return POPULAR_CONNECTOR_IDS.map((id) => CONNECTOR_CATALOG.find((c) => c.id === id)).filter(Boolean);
}
