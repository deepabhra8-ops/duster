import { useEffect, useState } from "react";
import { checkHealth } from "../services/healthService.js";

export function useHealthCheck() {
  const [healthy, setHealthy] = useState(true);

  useEffect(() => {
    let cancelled = false;
    checkHealth().then((ok) => {
      if (!cancelled) setHealthy(ok);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return healthy;
}

export default useHealthCheck;
