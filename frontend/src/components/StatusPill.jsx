/**
 * StatusPill.jsx - the status badge in every jobs list.
 *
 * Both jobs tables (ProfileMapper.jsx, Validator.jsx) rendered this inline as
 * `<span className={`pill ${STATUS_PILL[status]}`}>` - a bare coloured chip. Two
 * problems with that, which is why it is a component now:
 *
 *   - Colour was the only signal. "Completed" green and "Error" red read as
 *     identical shapes to anyone who cannot separate those hues, and they are
 *     the two statuses a user most needs to tell apart at a glance. Each status
 *     now carries an icon as well, so the meaning survives without colour.
 *
 *   - Two copies meant two places to change. The status vocabulary already
 *     lives in constants/jobStatus.js and the label in jobStatusLabel(); the
 *     rendering is the last piece that was still duplicated.
 *
 * The colour classes are still STATUS_PILL's, so the palette stays where the
 * rest of the status vocabulary is rather than moving in here.
 */
import { AlertCircle, CheckCircle2, Circle, CircleSlash, Clock, Loader2 } from "lucide-react";

import { STATUS_PILL } from "../constants/jobStatus.js";
import { jobStatusLabel } from "../utils/helpers.js";

/* Icon per status. A filled dot for the resting states (draft, cancelled) and a
   meaningful glyph for the rest - a spinner only where something really is in
   flight, so a spinning icon always means "still working". */
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
