from __future__ import annotations

import argparse
import platform
import shutil
import sys
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

    binary_path = dist_dir / (f"{name}.exe" if args.target_platform == "win32" else name)
    if not binary_path.exists():
        raise SystemExit(f"Beklenen çıktı üretilemedi: {binary_path}")

    print(binary_path)


if __name__ == "__main__":
    main()
