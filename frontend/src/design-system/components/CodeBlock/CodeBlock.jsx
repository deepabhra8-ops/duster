import { useState } from "react";
import { Copy } from "lucide-react";

/** A dark, monospace snippet block with a copy-to-clipboard button — used for the
 * least-privilege SQL each connector's setup instructions show. */
export function CodeBlock({ sql }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API unavailable (e.g. insecure context) — nothing to fall back to here.
    }
  }

  return (
    <div className="code-block">
      {sql}
      <button type="button" className="code-copy-btn" aria-label="Copy SQL" onClick={handleCopy} title={copied ? "Copied!" : "Copy SQL"}>
        <Copy aria-hidden="true" />
      </button>
    </div>
  );
}

export default CodeBlock;
