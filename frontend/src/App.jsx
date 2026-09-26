import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import TopBar from "./layout/AppShell/TopBar.jsx";
import Login from "./pages/Login.jsx";
import NotFound from "./pages/NotFound.jsx";
import DashboardPage from "./pages/Dashboards/DashboardPage.jsx";
import DataSourcesPage from "./pages/Dashboards/DataSourcesPage.jsx";
import RuleEditorPage from "./pages/QualityRules/RuleEditorPage.jsx";
import RunResultsPage from "./pages/QualityRules/RunResultsPage.jsx";
import ConnectionsPage from "./pages/Connections/ConnectionsPage.jsx";
import IngestionConfigPage from "./pages/Connections/IngestionConfigPage.jsx";
import PostgresFormPage from "./pages/Connections/NewConnection/PostgresFormPage.jsx";
import RedshiftFormPage from "./pages/Connections/NewConnection/RedshiftFormPage.jsx";
import DbtCloudFormPage from "./pages/Connections/NewConnection/DbtCloudFormPage.jsx";
import MysqlFormPage from "./pages/Connections/NewConnection/MysqlFormPage.jsx";
import MssqlFormPage from "./pages/Connections/NewConnection/MssqlFormPage.jsx";
import OracleFormPage from "./pages/Connections/NewConnection/OracleFormPage.jsx";
import SnowflakeFormPage from "./pages/Connections/NewConnection/SnowflakeFormPage.jsx";
import AzureSqlFormPage from "./pages/Connections/NewConnection/AzureSqlFormPage.jsx";
import BigQueryFormPage from "./pages/Connections/NewConnection/BigQueryFormPage.jsx";
import DatabricksFormPage from "./pages/Connections/NewConnection/DatabricksFormPage.jsx";
import SalesforceFormPage from "./pages/Connections/NewConnection/SalesforceFormPage.jsx";
import { AuthProvider } from "./contexts/AuthContext.jsx";
import { NotificationsProvider } from "./contexts/NotificationsContext.jsx";
import { ToastProvider } from "./contexts/ToastContext.jsx";
import { useAuth } from "./hooks/useAuth.js";
import { useDisableContextMenu } from "./hooks/useDisableContextMenu.js";

/**
 * Dev-only: renders a page's real chrome without the auth gate, so it can be reviewed
 * without a live backend/login. Never registered in production builds (see the DEV guard
 * around its route below).
 */
function PreviewLayout({ children }) {
  return (
    <NotificationsProvider>
      <TopBar />
      {children}
    </NotificationsProvider>
  );
}

function AuthenticatedLayout({ children }) {
  const { status } = useAuth();

  if (status === "checking") {
    return <div className="auth-loading">Loading&hellip;</div>;
  }

  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }

  return (
    <NotificationsProvider>
      <TopBar />
      {children}
    </NotificationsProvider>
  );
}

export default function App() {
  useDisableContextMenu();

  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="/control-room" element={<Navigate to="/dashboards/dimensions" replace />} />
            <Route path="/dashboards" element={<Navigate to="/dashboards/dimensions" replace />} />
            <Route
              path="/dashboards/dimensions"
              element={
                <AuthenticatedLayout>
                  <DashboardPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/dashboards/data-sources"
              element={
                <AuthenticatedLayout>
                  <DataSourcesPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/quality-rules"
              element={
                <AuthenticatedLayout>
                  <RuleEditorPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/quality-rules/runs"
              element={
                <AuthenticatedLayout>
                  <RunResultsPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections"
              element={
                <AuthenticatedLayout>
                  <ConnectionsPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/:id/ingestion"
              element={
                <AuthenticatedLayout>
                  <IngestionConfigPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/new/postgres"
              element={
                <AuthenticatedLayout>
                  <PostgresFormPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/new/redshift"
              element={
                <AuthenticatedLayout>
                  <RedshiftFormPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/new/dbt-cloud"
              element={
                <AuthenticatedLayout>
                  <DbtCloudFormPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/new/mysql"
              element={
                <AuthenticatedLayout>
                  <MysqlFormPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/new/mssql"
              element={
                <AuthenticatedLayout>
                  <MssqlFormPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/new/oracle"
              element={
                <AuthenticatedLayout>
                  <OracleFormPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/new/snowflake"
              element={
                <AuthenticatedLayout>
                  <SnowflakeFormPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/new/azure-sql"
              element={
                <AuthenticatedLayout>
                  <AzureSqlFormPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/new/bigquery"
              element={
                <AuthenticatedLayout>
                  <BigQueryFormPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/new/databricks"
              element={
                <AuthenticatedLayout>
                  <DatabricksFormPage />
                </AuthenticatedLayout>
              }
            />
            <Route
              path="/connections/new/salesforce"
              element={
                <AuthenticatedLayout>
                  <SalesforceFormPage />
                </AuthenticatedLayout>
              }
            />
            {import.meta.env.DEV ? (
              <Route
                path="/dev/data-sources-preview"
                element={
                  <PreviewLayout>
                    <DataSourcesPage mock />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/dashboard-preview"
                element={
                  <PreviewLayout>
                    <DashboardPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/quality-rules-preview"
                element={
                  <PreviewLayout>
                    <RuleEditorPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/quality-run-results-preview"
                element={
                  <PreviewLayout>
                    <RunResultsPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/connections-preview"
                element={
                  <PreviewLayout>
                    <ConnectionsPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/postgres-form-preview"
                element={
                  <PreviewLayout>
                    <PostgresFormPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/redshift-form-preview"
                element={
                  <PreviewLayout>
                    <RedshiftFormPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/dbt-cloud-form-preview"
                element={
                  <PreviewLayout>
                    <DbtCloudFormPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/mysql-form-preview"
                element={
                  <PreviewLayout>
                    <MysqlFormPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/mssql-form-preview"
                element={
                  <PreviewLayout>
                    <MssqlFormPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/oracle-form-preview"
                element={
                  <PreviewLayout>
                    <OracleFormPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/snowflake-form-preview"
                element={
                  <PreviewLayout>
                    <SnowflakeFormPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/azure-sql-form-preview"
                element={
                  <PreviewLayout>
                    <AzureSqlFormPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/bigquery-form-preview"
                element={
                  <PreviewLayout>
                    <BigQueryFormPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/databricks-form-preview"
                element={
                  <PreviewLayout>
                    <DatabricksFormPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            {import.meta.env.DEV ? (
              <Route
                path="/dev/salesforce-form-preview"
                element={
                  <PreviewLayout>
                    <SalesforceFormPage />
                  </PreviewLayout>
                }
              />
            ) : null}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  );
}
