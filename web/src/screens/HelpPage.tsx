import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import { ApiError, getText } from "../api";
import { ScreenHelp } from "../components/Help";

type Guide = "scientist" | "admin";

/** The two role guides, read from the API (docs/ of this installation) and rendered as
 * Markdown with no raw HTML. */
export default function HelpPage() {
  const [guide, setGuide] = useState<Guide>("scientist");
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setText(null);
    setError(null);
    getText(`/help/${guide}`)
      .then(setText)
      .catch((e) => setError(String(e instanceof ApiError ? e.detail : e)));
  }, [guide]);
  return (
    <div className="page">
      <h1>Help</h1>
      <ScreenHelp screen="help" />
      <div className="tabs">
        <button className={guide === "scientist" ? "active" : ""} onClick={() => setGuide("scientist")}>Scientist guide</button>
        <button className={guide === "admin" ? "active" : ""} onClick={() => setGuide("admin")}>Admin guide</button>
      </div>
      {error && (
        <div className="panel bad">
          The guide could not be loaded: {error}. Check that the API is running; the same text is in the repository under docs/.
        </div>
      )}
      {text === null && !error && <p className="muted">Loading…</p>}
      {text !== null && (
        <article className="panel guide" data-testid="guide">
          <Markdown>{text}</Markdown>
        </article>
      )}
    </div>
  );
}
