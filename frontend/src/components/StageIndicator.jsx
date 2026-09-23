/**
 * StageIndicator.jsx - Generic stage-circle indicator.
 *
 * Purely presentational: renders whatever `steps`/`connectors` a page's
 * progress computation (see utils/runProgress.js) hands it. Reuses the
 * existing .steps / .step-item / .step-num / .step-conn styling verbatim.
 */
import { Fragment } from "react";

export default function StageIndicator({ steps = [], connectors = [] }) {
  return (
    <div className="steps" role="list" aria-label="Pipeline steps">
      {steps.map((step, i) => (
        <Fragment key={step.label}>
          <div className="step-item" role="listitem">
            <div className={`step-num ${step.state}`}>{step.num}</div>
            <div className="step-label">{step.label}</div>
          </div>
          {i < connectors.length && (
            <div className={`step-conn${connectors[i] ? " done" : ""}`} />
          )}
        </Fragment>
      ))}
    </div>
  );
}
