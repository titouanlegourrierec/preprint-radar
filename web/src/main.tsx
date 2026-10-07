import { render } from "preact";
import { App } from "./app";
import { ErrorBoundary } from "./components/ErrorBoundary";
import "./styles.css";

const root = document.getElementById("app");
if (!root) {
  throw new Error("Missing #app element");
}
render(
  <ErrorBoundary what="the page">
    <App />
  </ErrorBoundary>,
  root,
);
