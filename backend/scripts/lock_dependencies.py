"""Regenerate or verify the universal Python requirement locks.

The application is developed on Windows and deployed on Linux. A platform-
specific resolver can silently omit dependencies needed by the other system,
so this script requires a pinned uv release and its universal resolver.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


EXPECTED_UV_VERSION = "0.12.10"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCKS = (
    (Path("backend/requirements.in"), Path("backend/requirements.txt")),
    (Path("backend/requirements-dev.in"), Path("backend/requirements-dev.txt")),
)
COMPILE_COMMAND = "python backend/scripts/lock_dependencies.py"


def _uv_executable() -> str:
    executable = shutil.which("uv")
    if executable is None:
        raise RuntimeError(
            "uv est absent. Installez l'outil avec "
            "`python -m pip install -r backend/requirements-tools.txt`."
        )

    completed = subprocess.run(
        [executable, "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    parts = completed.stdout.strip().split()
    version = parts[1] if len(parts) >= 2 else ""
    if version != EXPECTED_UV_VERSION:
        raise RuntimeError(
            f"Version uv inattendue ({version or 'inconnue'}). "
            f"La version {EXPECTED_UV_VERSION} est requise."
        )
    return executable


def _compile(
    uv: str,
    source: Path,
    output: Path,
    *,
    upgrade: bool,
) -> None:
    command = [
        uv,
        "pip",
        "compile",
        "--universal",
        "--python-version",
        "3.10",
        "--custom-compile-command",
        COMPILE_COMMAND,
        "--output-file",
        str(output),
        str(source),
    ]
    if upgrade:
        command.insert(3, "--upgrade")
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def _normalized_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def verify_locks(uv: str) -> int:
    stale: list[str] = []
    with tempfile.TemporaryDirectory(prefix="copilot-lock-check-") as directory:
        temporary_root = Path(directory)
        for source, target in LOCKS:
            absolute_target = PROJECT_ROOT / target
            generated = temporary_root / target.name
            # Existing pins are copied first so uv verifies the committed
            # resolution instead of opportunistically upgrading dependencies.
            shutil.copy2(absolute_target, generated)
            _compile(uv, source, generated, upgrade=False)
            if _normalized_text(absolute_target) != _normalized_text(generated):
                stale.append(str(target))

    if stale:
        print(
            "Verrous Python obsolètes : " + ", ".join(stale),
            file=sys.stderr,
        )
        print(
            f"Régénérez-les avec `{COMPILE_COMMAND}`.",
            file=sys.stderr,
        )
        return 1

    print("Verrous Python universels à jour.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Vérifie les verrous sans modifier les fichiers suivis.",
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Met à niveau toutes les dépendances autorisées par les fichiers .in.",
    )
    arguments = parser.parse_args()
    if arguments.check and arguments.upgrade:
        parser.error("--check et --upgrade ne peuvent pas être combinés")

    try:
        uv = _uv_executable()
        if arguments.check:
            return verify_locks(uv)
        for source, target in LOCKS:
            _compile(
                uv,
                source,
                PROJECT_ROOT / target,
                upgrade=arguments.upgrade,
            )
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Échec du verrouillage des dépendances : {error}", file=sys.stderr)
        return 1

    print("Verrous Python universels régénérés.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
