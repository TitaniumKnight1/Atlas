mod backend_lifecycle;

use backend_lifecycle::{terminate_sidecar_tree, SidecarJob};
use serde::{Deserialize, Serialize};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    mpsc, Arc, Mutex,
};
use tauri::{Manager, RunEvent, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

const READY_EVENT: &str = "atlas.backend.ready";
const READY_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(15);
const SIDECAR_NAME: &str = "binaries/atlas-backend";

struct BackendState {
    base_url: Mutex<Option<String>>,
    child: Mutex<Option<CommandChild>>,
    pid: Mutex<Option<u32>>,
    job: Mutex<Option<SidecarJob>>,
    terminated: Arc<AtomicBool>,
    shutdown_started: AtomicBool,
}

impl Default for BackendState {
    fn default() -> Self {
        Self {
            base_url: Mutex::new(None),
            child: Mutex::new(None),
            pid: Mutex::new(None),
            job: Mutex::new(None),
            terminated: Arc::new(AtomicBool::new(false)),
            shutdown_started: AtomicBool::new(false),
        }
    }
}

#[derive(Debug, Deserialize, Serialize)]
struct BackendReady {
    event: String,
    host: String,
    port: u16,
}

#[tauri::command]
fn backend_base_url(state: State<'_, BackendState>) -> Result<String, String> {
    state
        .inner()
        .base_url
        .lock()
        .map_err(|_| "Backend state lock is poisoned".to_string())?
        .clone()
        .ok_or_else(|| "Backend is not ready".to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState::default())
        .setup(|app| {
            spawn_backend(app).map_err(|error| {
                Box::<dyn std::error::Error>::from(std::io::Error::new(
                    std::io::ErrorKind::Other,
                    error,
                ))
            })?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_base_url])
        .build(tauri::generate_context!())
        .expect("error while building Atlas")
        .run(|app_handle, event| match event {
            RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                shutdown_backend(app_handle.state::<BackendState>().inner());
            }
            _ => {}
        });
}

fn spawn_backend(app: &mut tauri::App) -> Result<(), String> {
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Failed to resolve app data directory: {error}"))?;
    std::fs::create_dir_all(&app_data_dir)
        .map_err(|error| format!("Failed to create app data directory: {error}"))?;

    let state = app.state::<BackendState>().inner();
    let terminated = state.terminated.clone();
    let app_data_dir_arg = app_data_dir.to_string_lossy().into_owned();
    let sidecar = app
        .shell()
        .sidecar(SIDECAR_NAME)
        .map_err(|error| format!("Failed to prepare backend sidecar: {error}"))?
        .args([
            "--app-data-dir",
            app_data_dir_arg.as_str(),
            "--host",
            "127.0.0.1",
            "--port",
            "0",
        ]);

    let (mut rx, child) = sidecar
        .spawn()
        .map_err(|error| format!("Failed to spawn backend sidecar: {error}"))?;
    let child_pid = child.pid();

    match SidecarJob::attach_pid(child_pid) {
        Ok(job) => {
            state
                .job
                .lock()
                .map_err(|_| "Backend job lock is poisoned".to_string())?
                .replace(job);
        }
        Err(error) => {
            eprintln!("atlas-backend: {error}; continuing with taskkill tree cleanup only");
        }
    }

    state
        .pid
        .lock()
        .map_err(|_| "Backend pid lock is poisoned".to_string())?
        .replace(child_pid);
    state
        .child
        .lock()
        .map_err(|_| "Backend child lock is poisoned".to_string())?
        .replace(child);

    let (ready_tx, ready_rx) = mpsc::channel::<BackendReady>();
    tauri::async_runtime::spawn(async move {
        let mut stdout_buffer = String::new();
        let mut ready_tx = Some(ready_tx);

        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(bytes) => {
                    stdout_buffer.push_str(&String::from_utf8_lossy(&bytes));
                    while let Some(newline_index) = stdout_buffer.find('\n') {
                        let line = stdout_buffer.drain(..=newline_index).collect::<String>();
                        if let Some(ready) = parse_ready_line(&line) {
                            if let Some(sender) = ready_tx.take() {
                                let _ = sender.send(ready);
                            }
                        } else {
                            println!("atlas-backend stdout: {}", line.trim_end());
                        }
                    }
                }
                CommandEvent::Stderr(bytes) => {
                    eprintln!(
                        "atlas-backend stderr: {}",
                        String::from_utf8_lossy(&bytes).trim_end()
                    );
                }
                CommandEvent::Terminated(payload) => {
                    terminated.store(true, Ordering::SeqCst);
                    eprintln!("atlas-backend terminated: {payload:?}");
                    break;
                }
                _ => {}
            }
        }
    });

    let ready = ready_rx
        .recv_timeout(READY_TIMEOUT)
        .map_err(|_| "Timed out waiting for backend readiness handshake".to_string())?;
    state
        .base_url
        .lock()
        .map_err(|_| "Backend base URL lock is poisoned".to_string())?
        .replace(format!("http://{}:{}", ready.host, ready.port));

    Ok(())
}

fn parse_ready_line(line: &str) -> Option<BackendReady> {
    let ready = serde_json::from_str::<BackendReady>(line.trim()).ok()?;
    (ready.event == READY_EVENT).then_some(ready)
}

fn shutdown_backend(state: &BackendState) {
    if state.shutdown_started.swap(true, Ordering::SeqCst) {
        return;
    }

    let mut child = state.child.lock().ok().and_then(|mut guard| guard.take());
    let pid = state.pid.lock().ok().and_then(|mut guard| guard.take());

    terminate_sidecar_tree(&mut child, pid, &state.terminated);

    if let Ok(mut job_guard) = state.job.lock() {
        job_guard.take();
    }
}
