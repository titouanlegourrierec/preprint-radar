import { Component, type ComponentChildren } from "preact";
import { CONTACT_EMAIL, reportLink } from "../report";

interface Props {
  children: ComponentChildren;
  /** What failed, as the fallback says it: "the page", "this view". */
  what: string;
  /**
   * What the children draw from (the address's state, the papers loaded): once one of them
   * is another than when they failed (Back, another period or filter), they are drawn
   * again, which may well succeed.
   */
  resetKeys?: readonly unknown[];
}

interface State {
  error: Error | null;
}

/**
 * Catches an error thrown while rendering (TEST-10): a record the app cannot draw, or a
 * bug, then shows what failed instead of a blank page, with Reload, a link to start over
 * and whom to tell. Errors in event handlers do not reach it; they leave the page as it was.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };
  private failedOn: readonly unknown[] = [];

  static override getDerivedStateFromError(error: unknown): State {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  override componentDidCatch(error: unknown): void {
    console.error(error);
    this.failedOn = this.props.resetKeys ?? [];
  }

  override componentDidUpdate(): void {
    const keys = this.props.resetKeys ?? [];
    const failedOn = this.failedOn;
    if (
      this.state.error !== null &&
      (keys.length !== failedOn.length || keys.some((key, index) => key !== failedOn[index]))
    ) {
      this.setState({ error: null });
    }
  }

  override render() {
    const { error } = this.state;
    if (error === null) return this.props.children;
    return (
      <p class="notice notice--error" role="alert">
        Sorry, {this.props.what} could not be displayed: {error.message}.{" "}
        <button type="button" class="link-button" onClick={() => window.location.reload()}>
          Reload
        </button>
        , <a href="./">start over</a> or tell <a href={reportLink()}>{CONTACT_EMAIL}</a>.
      </p>
    );
  }
}
