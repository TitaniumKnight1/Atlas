import { invoke } from "@tauri-apps/api/core";

const KEYMASTER_URL = "https://keymaster.fivem.net/";

export { KEYMASTER_URL };

function isTauriDesktop(): boolean {
  return Boolean((window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__);
}

/** Open a URL in the user's default browser (Tauri opener plugin in desktop; fallback for Vite dev). */
export async function openExternalUrl(url: string): Promise<void> {
  if (isTauriDesktop()) {
    await invoke("plugin:opener|open_url", { url });
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}
