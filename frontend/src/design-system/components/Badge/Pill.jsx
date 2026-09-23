import { PILL_TONES } from "./Pill.variants.js";

export function Pill({ tone = "neutral", className = "", children }) {
  const classes = ["pill", PILL_TONES[tone], className].filter(Boolean).join(" ");
  return <span className={classes}>{children}</span>;
}

export default Pill;
