//! Talking to the Python host.
//!
//! The whole of the transport is here: spawn the sidecar, write one JSON line per
//! request, read one JSON line per response. There is no port, no socket and no
//! listener; see the README for why that is the point rather than an implementation
//! detail.
//!
//! Two things this module is careful about.
//!
//! **Standard output is the protocol.** Anything the sidecar writes to stderr is logged
//! and ignored. Anything on stdout is expected to be a response, and a line that does not
//! parse is an error rather than something to skip, because silently skipping is how a
//! protocol desynchronises and then hangs.
//!
//! **A dead sidecar is reported, not retried.** If the child exits, the window says so.
//! Restarting it automatically would lose every open redaction handle — and with them the
//! only copy of the real values — without the user being told.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};

/// The protocol version this shell understands.
///
/// Checked against the sidecar's `health` reply at startup. A desktop application and
/// its sidecar are installed as one unit, so a mismatch means the installer went wrong,
/// and continuing would produce confusing failures later instead of a clear one now.
pub const EXPECTED_PROTOCOL_VERSION: u64 = 1;

#[derive(Serialize)]
struct Request<'a> {
    jsonrpc: &'a str,
    id: u64,
    method: &'a str,
    params: serde_json::Value,
}

#[derive(Deserialize)]
struct Response {
    #[allow(dead_code)]
    id: Option<serde_json::Value>,
    result: Option<serde_json::Value>,
    error: Option<RpcError>,
}

#[derive(Deserialize, Debug)]
pub struct RpcError {
    pub code: i64,
    pub message: String,
}

pub struct Sidecar {
    child: Child,
    stdin: Mutex<ChildStdin>,
    stdout: Mutex<BufReader<ChildStdout>>,
    next_id: AtomicU64,
}

impl Sidecar {
    /// Spawn the sidecar executable.
    ///
    /// On Windows this must be a console-subsystem binary, because a GUI-subsystem
    /// executable has no standard input or output to inherit and would start and then
    /// answer nothing. `CREATE_NO_WINDOW` is what keeps the console invisible; the
    /// subsystem and the window are different things.
    pub fn spawn(program: &std::path::Path) -> std::io::Result<Self> {
        let mut command = Command::new(program);
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(CREATE_NO_WINDOW);
        }

        let mut child = command.spawn()?;
        let stdin = child.stdin.take().expect("stdin was piped");
        let stdout = child.stdout.take().expect("stdout was piped");

        Ok(Self {
            child,
            stdin: Mutex::new(stdin),
            stdout: Mutex::new(BufReader::new(stdout)),
            next_id: AtomicU64::new(1),
        })
    }

    /// Send one request and wait for its response.
    pub fn call(
        &self,
        method: &str,
        params: serde_json::Value,
    ) -> Result<serde_json::Value, String> {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let request = Request {
            jsonrpc: "2.0",
            id,
            method,
            params,
        };
        let line = serde_json::to_string(&request).map_err(|e| e.to_string())?;

        {
            let mut stdin = self.stdin.lock().map_err(|_| "sidecar lock poisoned")?;
            writeln!(stdin, "{line}").map_err(|e| format!("the sidecar is not accepting input: {e}"))?;
            stdin
                .flush()
                .map_err(|e| format!("could not flush to the sidecar: {e}"))?;
        }

        let mut reply = String::new();
        {
            let mut stdout = self.stdout.lock().map_err(|_| "sidecar lock poisoned")?;
            let read = stdout
                .read_line(&mut reply)
                .map_err(|e| format!("could not read from the sidecar: {e}"))?;
            if read == 0 {
                return Err("the sidecar stopped. Open redactions are gone with it.".into());
            }
        }

        let response: Response = serde_json::from_str(reply.trim())
            .map_err(|e| format!("the sidecar sent a line that is not a response: {e}"))?;

        if let Some(error) = response.error {
            return Err(format!("{} (code {})", error.message, error.code));
        }
        response
            .result
            .ok_or_else(|| "the sidecar sent a response with neither result nor error".into())
    }

    /// Check the sidecar is alive and speaks a version we understand.
    pub fn handshake(&self) -> Result<serde_json::Value, String> {
        let health = self.call("health", serde_json::json!({}))?;
        let version = health
            .get("protocol_version")
            .and_then(|v| v.as_u64())
            .ok_or("the sidecar did not report a protocol version")?;
        if version != EXPECTED_PROTOCOL_VERSION {
            return Err(format!(
                "this application speaks protocol {EXPECTED_PROTOCOL_VERSION} and the \
                 sidecar speaks {version}. They are installed together, so this means the \
                 installation is inconsistent rather than that something is out of date."
            ));
        }
        Ok(health)
    }
}

impl Drop for Sidecar {
    /// Closing the pipe is how the sidecar is asked to stop.
    ///
    /// It exits when its input ends, so there is no shutdown message to get wrong and no
    /// way for it to outlive the window. The kill is a backstop for a wedged process.
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
