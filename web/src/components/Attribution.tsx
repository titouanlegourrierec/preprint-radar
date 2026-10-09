/**
 * Where the data comes from, with links (REL-10): the footer says it, and the graph's
 * settings, since the full-screen graph has no footer.
 */
export function Attribution() {
  return (
    <>
      Data from <a href="https://arxiv.org">arXiv</a>. Thank you to arXiv for use of its open access
      interoperability. Citation counts from{" "}
      <a href="https://www.semanticscholar.org">Semantic Scholar</a>, institutions from the{" "}
      <a href="https://ror.org">Research Organization Registry</a> and{" "}
      <a href="https://openalex.org">OpenAlex</a>, stars from{" "}
      <a href="https://github.com">GitHub</a> and likes from{" "}
      <a href="https://huggingface.co">Hugging Face</a>.
    </>
  );
}
