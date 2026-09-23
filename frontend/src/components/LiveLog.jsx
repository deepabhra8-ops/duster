import { useEffect, useRef } from "react";
import { humanizeLogLine, isErrorLine } from "../utils/humanizeLog.js";

function lineClass(rawLine) {
  if (isErrorLine(rawLine)) return "log-err";
  if (rawLine.includes("✅")) return "log-ok";
  if (rawLine.includes("[WARN]")) return "log-warn";
  if (rawLine.includes("[DB]")) return "log-info";
  return "";
}

export default function LiveLog({ lines = [], idleMessage = "Waiting for job to start…" }) {
  const boxRef = useRef(null);

  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <div className="log-box" id="log-output" role="log" aria-live="polite" ref={boxRef}>
      {lines.length === 0 ? (
        <span className="log-idle">{idleMessage}</span>
      ) : (
        lines.map((line, i) => (
          <div key={i} className={lineClass(line) || undefined}>
            {humanizeLogLine(line)}
          </div>
        ))
      )}
    </div>
  );
}
