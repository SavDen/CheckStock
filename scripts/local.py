#!/usr/bin/env python3
"""Optional local launcher with PostgreSQL, no Docker. Keeps all data inside .local/."""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
PG_VERSION = "18.6.0-beta.19"  # npm distribution version, PostgreSQL engine 18.6


def run(*command, **kwargs):
    subprocess.run([str(x) for x in command], check=True, cwd=ROOT, **kwargs)


def prepare_postgres():
    package = LOCAL / "postgres"
    binary = package / "native" / "bin" / "pg_ctl"
    if binary.exists():
        return package / "native" / "bin"
    system = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    arch = {"x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine())
    if not system or not arch:
        raise SystemExit("Для этой ОС используйте Docker Compose или внешний PostgreSQL.")
    print("Загрузка переносимого PostgreSQL из npm registry…", flush=True)
    filename = f"{system}-{arch}-{PG_VERSION}.tgz"
    url = f"https://registry.npmjs.org/@embedded-postgres/{system}-{arch}/-/{filename}"
    archive = LOCAL / "postgres.tgz"
    urllib.request.urlretrieve(url, archive)
    staging = LOCAL / "pg-download"
    staging.mkdir(exist_ok=True)
    with tarfile.open(archive) as tar:
        tar.extractall(staging, filter="data")
    (staging / "package").rename(package)
    symlinks = package / "native" / "pg-symlinks.json"
    if symlinks.exists():
        for link in json.loads(symlinks.read_text()):
            source, target = (package / link["source"]).resolve(), package / link["target"]
            if not source.is_relative_to(package.resolve()) or not target.resolve().is_relative_to(
                package.resolve()
            ):
                raise RuntimeError("Unexpected path in PostgreSQL package")
            if not target.exists() and not target.is_symlink():
                target.symlink_to(os.path.relpath(source, target.parent))
    archive.unlink()
    shutil.rmtree(staging)
    return package / "native" / "bin"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Prepare DB, apply migrations, check health; do not serve"
    )
    parser.add_argument("--stop-db", action="store_true", help="Stop only the local PostgreSQL cluster")
    args = parser.parse_args()
    LOCAL.mkdir(exist_ok=True)
    binaries = prepare_postgres()
    cluster = LOCAL / "pgdata"
    if args.stop_db:
        run(binaries / "pg_ctl", "-D", cluster, "stop", "-m", "fast")
        return
    port = int(os.getenv("LOCAL_PG_PORT", "55433"))
    if not (cluster / "PG_VERSION").exists():
        run(
            binaries / "initdb",
            "-D",
            cluster,
            "-U",
            "checkstock",
            "--auth=trust",
            "--encoding=UTF8",
            "--locale=C",
        )
    status = subprocess.run([str(binaries / "pg_ctl"), "-D", str(cluster), "status"], capture_output=True)
    if status.returncode:
        run(
            binaries / "pg_ctl",
            "-D",
            cluster,
            "-l",
            LOCAL / "postgres.log",
            "-o",
            f"-p {port} -h 127.0.0.1 -k {LOCAL}",
            "start",
        )
    import psycopg
    from psycopg import sql

    with psycopg.connect(f"postgresql://checkstock@127.0.0.1:{port}/postgres", autocommit=True) as connection:
        if not connection.execute("SELECT 1 FROM pg_database WHERE datname='checkstock'").fetchone():
            connection.execute(sql.SQL("CREATE DATABASE checkstock"))
    os.environ["DATABASE_URL"] = f"postgresql+psycopg://checkstock@127.0.0.1:{port}/checkstock"
    run(sys.executable, "-m", "alembic", "upgrade", "head", env=os.environ)
    if args.check:
        sys.path.insert(0, str(ROOT))
        from app.seed import seed

        seed()
        print("PostgreSQL, миграции и тестовые данные готовы.")
        return
    app_port = int(os.getenv("CHECKSTOCK_PORT", "8000"))
    print(
        f"\nCheckStock: http://127.0.0.1:{app_port}\nCtrl+C останавливает приложение. Данные сохраняются в .local/pgdata.\n",
        flush=True,
    )
    try:
        run(
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(app_port),
            env=os.environ,
        )
    except KeyboardInterrupt:
        print(
            "\nПриложение остановлено. PostgreSQL можно остановить: .venv/bin/python scripts/local.py --stop-db"
        )


if __name__ == "__main__":
    main()
