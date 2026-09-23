import { Link, useLocation } from "react-router-dom";

export default function NotFound() {
  const location = useLocation();

  return (
    <section>
      <header className="page-header">
        <h2>404 - Page Not Found</h2>
        <p>
          There's no page at <code>{location.pathname}</code>.
        </p>
      </header>
      <div className="card">
        <p>Check the URL, or head back to a known page:</p>
        <div className="btn-row" style={{ marginTop: "12px" }}>
          <Link to="/home" className="btn btn-primary">
            🏠 Go Home
          </Link>
        </div>
      </div>
    </section>
  );
}
