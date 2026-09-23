import { AlertCircle, CheckCircle2, Circle, CircleSlash, Clock, Loader2 } from "lucide-react";

import { STATUS_PILL } from "../constants/jobStatus.js";
import { jobStatusLabel } from "../utils/helpers.js";

const STATUS_ICON = {
  draft: Circle,
  queued: Clock,
  running: Loader2,
  cancelling: Loader2,
  done: CheckCircle2,
  error: AlertCircle,
  cancelled: CircleSlash,
};

const SPINNING = ["running", "cancelling"];

export default function StatusPill({ status }) {
  const Icon = STATUS_ICON[status] || Circle;
  const tone = STATUS_PILL[status] || "pill-gray";

  return (
    <span className={`status-pill ${tone}`}>
      <Icon
        size={13}
        className={`status-pill-icon${SPINNING.includes(status) ? " is-spinning" : ""}`}
        aria-hidden="true"
      />
      {jobStatusLabel(status)}
    </span>
  );
}
