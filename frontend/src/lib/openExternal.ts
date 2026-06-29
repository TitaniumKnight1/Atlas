const KEYMASTER_URL = "https://keymaster.fivem.net/";

export { KEYMASTER_URL };

/** Open a URL in the user's default browser (Tauri opener in desktop; fallback for Vite dev). */
export async function openExternalUrl(url: string): Promise<void> {
  const tauriInternals = (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  if (tauriInternals) {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}
