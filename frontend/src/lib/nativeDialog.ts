const FIVEM_SERVER_ARTIFACTS_URL = "https://runtime.fivem.net/artifacts/fivem/build_server_windows/master/";

export { FIVEM_SERVER_ARTIFACTS_URL };

function isTauriDesktop(): boolean {
  return Boolean((window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__);
}

function pickWithHiddenInput(kind: "file" | "directory", accept?: string): Promise<string | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    if (kind === "directory") {
      input.setAttribute("webkitdirectory", "");
      input.setAttribute("directory", "");
    } else if (accept) {
      input.accept = accept;
    }
    input.style.display = "none";
    input.addEventListener("change", () => {
      const selected = input.files?.[0] as (File & { path?: string; webkitRelativePath?: string }) | undefined;
      document.body.removeChild(input);
      if (!selected) {
        resolve(null);
        return;
      }
      if (selected.path) {
        if (kind === "directory") {
          const relative = selected.webkitRelativePath ?? "";
          const root = relative.split(/[\\/]/)[0];
          resolve(root ? selected.path.replace(/[\\/][^\\/]+$/, "") : selected.path);
          return;
        }
        resolve(selected.path);
        return;
      }
      resolve(null);
    });
    input.addEventListener("cancel", () => {
      document.body.removeChild(input);
      resolve(null);
    });
    document.body.appendChild(input);
    input.click();
  });
}

export async function pickExecutableFile(title = "Locate FXServer.exe"): Promise<string | null> {
  if (isTauriDesktop()) {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({
      title,
      multiple: false,
      directory: false,
      filters: [{ name: "FXServer", extensions: ["exe"] }]
    });
    return typeof selected === "string" ? selected : null;
  }
  return pickWithHiddenInput("file", ".exe");
}

export async function pickFolder(title = "Choose folder"): Promise<string | null> {
  if (isTauriDesktop()) {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({
      title,
      multiple: false,
      directory: true
    });
    return typeof selected === "string" ? selected : null;
  }
  return pickWithHiddenInput("directory");
}
