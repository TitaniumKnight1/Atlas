import { BackendApiError } from "../api/backend";

export function humanizeProcessStartError(error: unknown): { title: string; detail: string; raw?: string } {
  const message = error instanceof BackendApiError ? error.message : error instanceof Error ? error.message : String(error ?? "Unknown error");
  const lowered = message.toLowerCase();

  if (lowered.includes("set your fxserver executable first")) {
    return { title: "FXServer path required", detail: message };
  }
  if (lowered.includes("permission denied") || lowered.includes("winerror 5") || lowered.includes("access is denied")) {
    return {
      title: "Permission denied",
      detail:
        "Atlas couldn't run FXServer (permission denied) — try running as administrator or check the file isn't blocked by Windows.",
      raw: message
    };
  }
  if (lowered.includes("not found") || lowered.includes("cannot find the file")) {
    return { title: "FXServer not found", detail: message, raw: message };
  }
  if (lowered.includes("server-data") || lowered.includes("server.cfg") || lowered.includes("working folder")) {
    return { title: "Working folder required", detail: message, raw: message };
  }
  if (lowered.includes("directory name is invalid") || lowered.includes("winerror 267")) {
    return {
      title: "Working folder not found",
      detail:
        "That folder doesn't exist. Atlas runs FXServer from the directory containing your tracked server.cfg — for most team repos that's the project root.",
      raw: message
    };
  }

  return { title: "Could not start server", detail: message, raw: message };
}
