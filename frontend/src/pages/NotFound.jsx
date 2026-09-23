import { Link, useLocation } from "react-router-dom";
import { Alert, Button, Panel } from "../design-system/components/index.js";
import { DEFAULT_ROUTE } from "../constants/appConfig.js";

export default function NotFound() {
  const location = useLocation();

  return (
    <div style={{ maxWidth: 480, margin: "80px auto", padding: "0 var(--space-6)" }}>
      <Panel title="Page not found">
        <Alert tone="warning" title="404">
          There&rsquo;s no page at <code className="ds-mono">{location.pathname}</code>.
        </Alert>
        <div style={{ marginTop: "var(--space-4)" }}>
          <Link to={DEFAULT_ROUTE}>
            <Button register="primary">Back to Control Room</Button>
          </Link>
        </div>
      </Panel>
    </div>
  );
}
