/**
 * RuleExampleCards.jsx - static list of the DQ rule "Examples and expected
 * results" cards. Lives in the Rules page's second placeholder box, alongside
 * the rule table in the first.
 */
export default function RuleExampleCards({ examples }) {
  if (examples.length === 0) {
    return <p className="hint">No rule examples match your search.</p>;
  }

  return (
    <div className="rule-example-list">
      {examples.map((rule) => (
        <article className="rule-example" key={rule.id}>
          <div className="rule-example-heading">
            <span className={`pill ${rule.pill}`}>{rule.id}</span>
            <strong>{rule.cat}</strong>
          </div>
          <dl>
            <div>
              <dt>Description</dt>
              <dd>{rule.desc}</dd>
            </div>
            <div className="rule-example-row">
              <div>
                <dt>Dimension</dt>
                <dd>{rule.dim}</dd>
              </div>
              <div>
                <dt>Category</dt>
                <dd>{rule.cat}</dd>
              </div>
            </div>
            <div className="rule-example-row">
              <div>
                <dt>Parameter</dt>
                <dd><code>{rule.params}</code></dd>
              </div>
              <div>
                <dt>Example value</dt>
                <dd>{rule.example.input}</dd>
              </div>
            </div>
            <div>
              <dt>Expected result</dt>
              <dd>{rule.example.output}</dd>
            </div>
          </dl>
          <p className="rule-example-note">{rule.example.note}</p>
        </article>
      ))}
    </div>
  );
}
