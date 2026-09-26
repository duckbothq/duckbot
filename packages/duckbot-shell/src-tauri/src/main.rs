// The window.
//
// Deliberately thin. Everything that decides anything lives in Python, where it is
// tested; this file starts a process and forwards allowlisted calls. If it grows past that,
// logic has leaked out of the tested half into the untested one.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod sidecar;

use std::path::PathBuf;
use std::sync::Arc;

use sidecar::Sidecar;
use tauri::Manager;

struct AppState {
    sidecar: Arc<Sidecar>,
}

/// Where the sidecar executable lives next to the installed application.
///
/// Resolved relative to the running binary rather than from a configured path: a path in
/// configuration is a path somebody can point at a different executable, and this one
/// spawns a process.
fn sidecar_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let name = if cfg!(windows) {
        "duckbot-host.exe"
    } else {
        "duckbot-host"
    };
    app.path()
        .resource_dir()
        .map_err(|e| format!("could not locate the application's resources: {e}"))
        .map(|dir| dir.join(name))
}

async fn call_host(
    sidecar: Arc<Sidecar>,
    method: String,
    params: serde_json::Value,
) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || sidecar.call(&method, params))
        .await
        .map_err(|_| "the local service worker stopped unexpectedly".to_string())?
}

#[tauri::command]
async fn health(state: tauri::State<'_, AppState>) -> Result<serde_json::Value, String> {
    call_host(
        Arc::clone(&state.sidecar),
        "health".into(),
        serde_json::json!({}),
    )
    .await
}

#[tauri::command]
async fn redact(
    state: tauri::State<'_, AppState>,
    text: String,
) -> Result<serde_json::Value, String> {
    call_host(
        Arc::clone(&state.sidecar),
        "redact".into(),
        serde_json::json!({ "text": text }),
    )
    .await
}

#[tauri::command]
async fn restore(
    state: tauri::State<'_, AppState>,
    redaction_id: String,
    text: String,
) -> Result<serde_json::Value, String> {
    call_host(
        Arc::clone(&state.sidecar),
        "restore".into(),
        serde_json::json!({ "redaction_id": redaction_id, "text": text }),
    )
    .await
}

#[tauri::command]
async fn classify(
    state: tauri::State<'_, AppState>,
    text: String,
) -> Result<serde_json::Value, String> {
    call_host(
        Arc::clone(&state.sidecar),
        "classify".into(),
        serde_json::json!({ "text": text }),
    )
    .await
}

#[tauri::command]
async fn rpc(
    state: tauri::State<'_, AppState>,
    method: String,
    params: serde_json::Value,
) -> Result<serde_json::Value, String> {
    const ALLOWED: &[&str] = &[
        "task_prepare",
        "task_execute",
        "task_cancel",
        "approval_decide",
        "tasks_list",
        "audit_list",
        "audit_verify",
        "settings_get",
        "settings_update",
        "connector_list",
    ];
    if !ALLOWED.contains(&method.as_str()) {
        return Err("the requested host method is not exposed to the window".into());
    }
    if !params.is_object() {
        return Err("RPC params must be an object".into());
    }
    call_host(Arc::clone(&state.sidecar), method, params).await
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let path = sidecar_path(app.handle())?;
            let sidecar = Sidecar::spawn(&path).map_err(|e| {
                format!(
                    "could not start the Duckbot host at {}: {e}",
                    path.display()
                )
            })?;
            // Fail loudly at startup rather than at the first call. A version mismatch
            // between the window and its sidecar means the installation is inconsistent,
            // and finding that out during a demonstration is worse than finding it out
            // when the icon is double-clicked.
            sidecar.handshake()?;
            app.manage(AppState {
                sidecar: Arc::new(sidecar),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            health, redact, restore, classify, rpc
        ])
        .run(tauri::generate_context!())
        .expect("the Duckbot window failed to start");
}
