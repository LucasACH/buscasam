"use client";

// Returns a callback that downloads historical version `n` of `docId`.
// HEAD-preflights the endpoint (nginx still computes X-Accel-Redirect) so the
// rare revoke-mid-session race surfaces as a rejection instead of a navigation
// to a 404; on success it navigates the browser to the URL, letting the
// streamed Content-Disposition response trigger the native download.
export function useVersionDownload(docId: number) {
  return async (n: number): Promise<void> => {
    const url = `/api/docs/${docId}/versions/${n}/download`;
    const r = await fetch(url, { method: "HEAD", credentials: "same-origin" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    window.location.assign(url);
  };
}
