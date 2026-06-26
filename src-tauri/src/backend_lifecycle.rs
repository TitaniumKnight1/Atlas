//! Backend sidecar lifecycle helpers.
//!
//! PyInstaller one-file executables spawn a bootloader parent and a child worker on Windows.
//! `CommandChild::kill()` and single-PID termination can leave the worker and its loopback
//! port alive. Atlas therefore attaches the sidecar to a Windows Job Object with
//! `KILL_ON_JOB_CLOSE` at spawn time and always terminates the full process tree on shutdown.

use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::Duration;

use tauri_plugin_shell::process::CommandChild;

pub const GRACEFUL_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(1);

#[cfg(windows)]
mod windows_job {
    use std::ffi::c_void;
    use std::io;
    use std::ptr::null_mut;

    type Handle = *mut c_void;

    const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: u32 = 9;
    const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: u32 = 0x0000_2000;
    const PROCESS_SET_QUOTA: u32 = 0x0100;
    const PROCESS_TERMINATE: u32 = 0x0001;

    extern "system" {
        fn CloseHandle(handle: Handle) -> i32;
        fn CreateJobObjectW(attributes: *mut c_void, name: *const u16) -> Handle;
        fn SetInformationJobObject(
            job: Handle,
            info_class: u32,
            info: *mut c_void,
            info_length: u32,
        ) -> i32;
        fn AssignProcessToJobObject(job: Handle, process: Handle) -> i32;
        fn OpenProcess(access: u32, inherit: i32, process_id: u32) -> Handle;
    }

    #[repr(C)]
    struct JobObjectBasicLimitInformation {
        per_process_user_time_limit: i64,
        per_job_user_time_limit: i64,
        limit_flags: u32,
        minimum_working_set_size: usize,
        maximum_working_set_size: usize,
        active_process_limit: u32,
        affinity: usize,
        priority_class: u32,
        scheduling_class: u32,
    }

    #[repr(C)]
    struct IoCounters {
        read_operation_count: u64,
        write_operation_count: u64,
        other_operation_count: u64,
        read_transfer_count: u64,
        write_transfer_count: u64,
        other_transfer_count: u64,
    }

    #[repr(C)]
    struct JobObjectExtendedLimitInformation {
        basic_limit_information: JobObjectBasicLimitInformation,
        io_info: IoCounters,
        process_memory_limit: usize,
        job_memory_limit: usize,
        peak_process_memory_used: usize,
        peak_job_memory_used: usize,
    }

    pub struct JobObject {
        handle: Handle,
    }

    pub fn close_handle(handle: usize) {
        if handle != 0 {
            unsafe {
                CloseHandle(handle as Handle);
            }
        }
    }

    impl JobObject {
        pub fn into_handle(self) -> usize {
            let handle = self.handle as usize;
            std::mem::forget(self);
            handle
        }
        pub fn new() -> io::Result<Self> {
            unsafe {
                let handle = CreateJobObjectW(null_mut(), null_mut());
                if handle.is_null() {
                    return Err(io::Error::last_os_error());
                }

                let mut info = JobObjectExtendedLimitInformation {
                    basic_limit_information: JobObjectBasicLimitInformation {
                        per_process_user_time_limit: 0,
                        per_job_user_time_limit: 0,
                        limit_flags: JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
                        minimum_working_set_size: 0,
                        maximum_working_set_size: 0,
                        active_process_limit: 0,
                        affinity: 0,
                        priority_class: 0,
                        scheduling_class: 0,
                    },
                    io_info: IoCounters {
                        read_operation_count: 0,
                        write_operation_count: 0,
                        other_operation_count: 0,
                        read_transfer_count: 0,
                        write_transfer_count: 0,
                        other_transfer_count: 0,
                    },
                    process_memory_limit: 0,
                    job_memory_limit: 0,
                    peak_process_memory_used: 0,
                    peak_job_memory_used: 0,
                };

                if SetInformationJobObject(
                    handle,
                    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                    &mut info as *mut _ as *mut c_void,
                    std::mem::size_of::<JobObjectExtendedLimitInformation>() as u32,
                ) == 0
                {
                    CloseHandle(handle);
                    return Err(io::Error::last_os_error());
                }

                Ok(Self { handle })
            }
        }

        pub fn assign_pid(&self, pid: u32) -> io::Result<()> {
            unsafe {
                let process =
                    OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, pid);
                if process.is_null() {
                    return Err(io::Error::last_os_error());
                }

                let assigned = AssignProcessToJobObject(self.handle, process);
                CloseHandle(process);
                if assigned == 0 {
                    return Err(io::Error::last_os_error());
                }

                Ok(())
            }
        }
    }

    impl Drop for JobObject {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.handle);
            }
        }
    }
}

#[cfg(windows)]
use std::process::Command as StdCommand;

#[cfg(windows)]
pub struct SidecarJob {
    handle: usize,
}

#[cfg(windows)]
unsafe impl Send for SidecarJob {}

#[cfg(windows)]
unsafe impl Sync for SidecarJob {}

#[cfg(windows)]
impl SidecarJob {
    pub fn attach_pid(pid: u32) -> Result<Self, String> {
        let job = windows_job::JobObject::new()
            .map_err(|error| format!("Failed to create Windows job object: {error}"))?;
        job.assign_pid(pid)
            .map_err(|error| format!("Failed to assign sidecar pid={pid} to job object: {error}"))?;
        Ok(Self {
            handle: job.into_handle(),
        })
    }
}

#[cfg(windows)]
impl Drop for SidecarJob {
    fn drop(&mut self) {
        windows_job::close_handle(self.handle);
    }
}

#[cfg(not(windows))]
pub struct SidecarJob;

#[cfg(not(windows))]
impl SidecarJob {
    pub fn attach_pid(_pid: u32) -> Result<Self, String> {
        Ok(Self)
    }
}

pub fn terminate_sidecar_tree(
    child: &mut Option<CommandChild>,
    pid: Option<u32>,
    terminated: &AtomicBool,
) {
    if let Some(child_handle) = child.as_mut() {
        let _ = child_handle.write(b"shutdown\n");
    }

    let grace_checks = GRACEFUL_SHUTDOWN_TIMEOUT.as_millis() / 100;
    for _ in 0..grace_checks {
        if terminated.load(Ordering::SeqCst) {
            break;
        }
        thread::sleep(Duration::from_millis(100));
    }

    if let Some(pid) = pid {
        kill_process_tree(pid);
    }

    if let Some(child_handle) = child.take() {
        let _ = child_handle.kill();
    }

    if !terminated.load(Ordering::SeqCst) {
        thread::sleep(Duration::from_millis(200));
    }
}

#[cfg(windows)]
pub fn kill_process_tree(pid: u32) {
    let _ = StdCommand::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .status();
}

#[cfg(not(windows))]
pub fn kill_process_tree(pid: u32) {
    let _ = std::process::Command::new("pkill")
        .args(["-TERM", "-P", &pid.to_string()])
        .status();
    thread::sleep(Duration::from_millis(100));
    let _ = std::process::Command::new("kill")
        .args(["-KILL", &pid.to_string()])
        .status();
}
