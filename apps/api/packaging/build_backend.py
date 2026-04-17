from __future__ import annotations

import argparse
import errno
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def current_target_platform() -> str:
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def current_target_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "x64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    return machine or "unknown"


def default_binary_name(target_platform: str, target_arch: str) -> str:
    if target_platform == "win32":
        return "lawcopilot-api"
    if target_platform == "darwin":
        return f"lawcopilot-api-{target_arch}"
    return "lawcopilot-api"


def ensure_same_platform(target_platform: str) -> None:
    current = current_target_platform()
    if current != target_platform:
        raise SystemExit(
            f"PyInstaller çapraz derleme desteklenmiyor. Geçerli platform: {current}, istenen platform: {target_platform}."
        )


def validate_binary(binary_path: Path) -> tuple[bool, str]:
    if not binary_path.exists():
        for attempt in range(5):
            time.sleep(0.4 * (attempt + 1))
            if binary_path.exists():
                break
        else:
            return False, "binary_missing"
    validation_root = Path(tempfile.mkdtemp(prefix="lawcopilot-pyinstaller-validate-"))
    env = {
        **os.environ,
        "LAWCOPILOT_DB_PATH": str(validation_root / "lawcopilot.db"),
        "LAWCOPILOT_AUDIT_LOG": str(validation_root / "audit.log.jsonl"),
        "LAWCOPILOT_STRUCTURED_LOG": str(validation_root / "events.log.jsonl"),
        "LAWCOPILOT_PERSONAL_KB_ROOT": str(validation_root / "personal-kb"),
        "LAWCOPILOT_ARTIFACTS_DIR": str(validation_root / "artifacts"),
        "LAWCOPILOT_ALLOW_LOCAL_TOKEN_BOOTSTRAP": "true",
    }
    try:
        last_os_error = ""
        for attempt in range(5):
            try:
                result = subprocess.run(
                    [str(binary_path), "--help"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=20,
                    check=False,
                    env=env,
                )
                break
            except subprocess.TimeoutExpired:
                return False, "validation_timeout"
            except OSError as exc:
                if exc.errno in {errno.ETXTBSY, errno.ENOENT} and attempt < 4:
                    last_os_error = f"validation_os_error:{exc}"
                    time.sleep(0.6 * (attempt + 1))
                    continue
                return False, f"validation_os_error:{exc}"
        else:
            return False, last_os_error or "validation_os_error"
    finally:
        shutil.rmtree(validation_root, ignore_errors=True)
    if result.returncode == 0:
        return True, ""
    error_text = (result.stderr or "").strip()
    return False, error_text or f"validation_exit_{result.returncode}"


def main() -> None:
    parser = argparse.ArgumentParser(description="LawCopilot API ikilisini PyInstaller ile üretir.")
    parser.add_argument("--target-platform", default=current_target_platform())
    parser.add_argument("--target-arch", default=current_target_arch())
    parser.add_argument("--dist-dir")
    parser.add_argument("--build-dir")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    ensure_same_platform(args.target_platform)

    try:
        import PyInstaller.__main__ as pyinstaller_main
    except ModuleNotFoundError as exc:
        raise SystemExit("PyInstaller kurulu değil. Önce requirements.txt içindeki paketleri yükleyin.") from exc

    api_root = Path(__file__).resolve().parents[1]
    project_root = api_root.parent.parent
    entrypoint = api_root / "main.py"
    dist_dir = Path(args.dist_dir) if args.dist_dir else api_root / "dist"
    build_dir = Path(args.build_dir) if args.build_dir else api_root / "build" / "pyinstaller"
    name = default_binary_name(args.target_platform, args.target_arch)

    if args.clean:
        shutil.rmtree(build_dir, ignore_errors=True)
        target_path = dist_dir / (f"{name}.exe" if args.target_platform == "win32" else name)
        if target_path.exists():
            if target_path.is_dir():
                shutil.rmtree(target_path, ignore_errors=True)
            else:
                target_path.unlink()

    dist_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    binary_path = dist_dir / (f"{name}.exe" if args.target_platform == "win32" else name)

    def _build_once() -> None:
        pyinstaller_args = [
            str(entrypoint),
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            name,
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(build_dir),
            "--specpath",
            str(build_dir),
            "--paths",
            str(api_root),
            "--add-data",
            f"{project_root / 'configs' / 'model-profiles.json'}{';' if args.target_platform == 'win32' else ':'}configs",
            "--add-data",
            f"{api_root / 'lawcopilot_api' / 'openclaw_assets'}{';' if args.target_platform == 'win32' else ':'}lawcopilot_api/openclaw_assets",
            "--collect-submodules",
            "lawcopilot_api",
            "--collect-submodules",
            "uvicorn",
            "--collect-submodules",
            "fastapi",
            "--collect-submodules",
            "starlette",
            "--collect-submodules",
            "anyio",
        ]
        pyinstaller_main.run(pyinstaller_args)

    last_error = ""
    for attempt in range(2):
        if attempt > 0:
            shutil.rmtree(build_dir, ignore_errors=True)
            if binary_path.exists():
                if binary_path.is_dir():
                    shutil.rmtree(binary_path, ignore_errors=True)
                else:
                    binary_path.unlink()
            build_dir.mkdir(parents=True, exist_ok=True)
            dist_dir.mkdir(parents=True, exist_ok=True)
        _build_once()
        valid, validation_error = validate_binary(binary_path)
        if valid:
            print(binary_path)
            return
        last_error = validation_error
        print(f"PyInstaller doğrulaması başarısız, temiz rebuild deneniyor: {validation_error}", file=sys.stderr)

    raise SystemExit(f"PyInstaller doğrulaması başarısız: {binary_path} | {last_error}")


if __name__ == "__main__":
    main()
