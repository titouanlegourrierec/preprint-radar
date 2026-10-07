/** Offer `content` to the user as a file download named `filename`. */
export function download(filename: string, content: string, type: string): void {
  downloadBlob(filename, new Blob([content], { type }));
}

/** Offer a blob (an image) to the user as a file download named `filename`. */
export function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  link.click();
  URL.revokeObjectURL(url);
}
