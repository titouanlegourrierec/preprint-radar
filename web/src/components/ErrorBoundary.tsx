import { Component, type ComponentChildren } from "preact";
import { CONTACT_EMAIL, reportLink } from "../report";

interface Props {
  children: ComponentChildren;
  /** What failed, as the fallback says it: "the page", "this view". */
  what: string;
}

interface State {
  error: Error | null;
}

/**
 * Catches an error thrown while rendering (TEST-10): a record the app cannot draw, or a
 * bug, then shows what failed and a way back instead of a blank page. Errors in event
 * handlers do not reach it; they leave the page as it was.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static override getDerivedStateFromError(error: unknown): State {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  override componentDidCatch(error: unknown): void {
    console.error(error);
  }

  override render() {
    const { error } = this.state;
    if (error === null) return this.props.children;
    return (
      <p class="notice notice--error" role="alert">
        Sorry, {this.props.what} could not be displayed: {error.message}.{" "}
        <button type="button" class="link-button" onClick={() => window.location.reload()}>
          Reload
        </button>{" "}
        or tell <a href={reportLink()}>{CONTACT_EMAIL}</a>.
      </p>
    );
  }
}
