use std::{env, fs, path::PathBuf};

fn main() {
    tauri_build::build();
    copy_sidecar_for_local_target();
}

/// Install the PyInstaller sidecar where `tauri-plugin-shell` looks in dev builds.
///
/// `Command::new_sidecar("binaries/atlas-backend")` resolves to
/// `{target}/{profile}/binaries/atlas-backend.exe` next to `atlas.exe`, not the
/// triple-suffixed filename under `src-tauri/binaries/`.
fn copy_sidecar_for_local_target() {
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    let target_triple = env::var("TARGET").expect("TARGET");
    let extension = if cfg!(windows) { ".exe" } else { "" };
    let source = manifest_dir.join(format!(
        "binaries/atlas-backend-{target_triple}{extension}"
    ));

    if !source.is_file() {
        println!(
            "cargo:warning=Sidecar source missing at {}; run `npm run sidecar:build` before `tauri dev`",
            source.display()
        );
        return;
    }

    let out_dir = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR"));
    let Some(profile_dir) = out_dir.ancestors().nth(3) else {
        println!("cargo:warning=Unable to resolve Cargo profile directory for sidecar install");
        return;
    };

    let dest_dir = profile_dir.join("binaries");
    if let Err(error) = fs::create_dir_all(&dest_dir) {
        println!("cargo:warning=Failed to create {}: {error}", dest_dir.display());
        return;
    }

    let dest = dest_dir.join(format!("atlas-backend{extension}"));
    match fs::copy(&source, &dest) {
        Ok(_) => println!(
            "cargo:warning=Installed sidecar for local runs: {}",
            dest.display()
        ),
        Err(error) => println!(
            "cargo:warning=Failed to install sidecar to {}: {error}",
            dest.display()
        ),
    }
}
