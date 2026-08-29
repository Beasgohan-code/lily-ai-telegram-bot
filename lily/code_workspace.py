"""Isolated source-code workspaces for Lily.

The workspace is intentionally not an arbitrary shell. It creates and edits
small source projects below a Lily-managed directory, packages them for Telegram
delivery, and performs fixed syntax checks only.
"""
from __future__ import annotations

import json
import os
import py_compile
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from .config import settings


_NAME_RE = re.compile(r"[a-z][a-z0-9-]{1,62}$")
_OWNER_RE = re.compile(r"[a-z0-9-]{1,48}$")
_MAX_FILE_BYTES = 512_000
_MAX_ARCHIVE_FILES = 200
_MAX_ARCHIVE_BYTES = 20_000_000


def _clean_text(value: Any, fallback: str, limit: int) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    if not text:
        return fallback
    return text[:limit]


def _language(value: str) -> str:
    aliases = {"py": "python", "js": "javascript", "ts": "typescript", "c#": "csharp", "cs": "csharp", "yml": "yaml", "sh": "bash"}
    normalized = aliases.get(str(value or "").strip().lower(), str(value or "").strip().lower())
    if normalized not in CodeWorkspace.LANGUAGES:
        raise ValueError(f"Unsupported language. Choose one of: {', '.join(CodeWorkspace.LANGUAGES)}.")
    return normalized


class CodeWorkspace:
    LANGUAGES = ("python", "javascript", "typescript", "html", "css", "json", "yaml", "bash", "java", "csharp", "go", "rust")

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or settings.work_dir / "code-workspaces").resolve()

    @staticmethod
    def _owner(owner: str | int) -> str:
        normalized = str(owner or "local").strip().lower().replace("_", "-")
        if not _OWNER_RE.fullmatch(normalized):
            raise ValueError("Workspace owner must use lowercase letters, digits, or hyphens.")
        return normalized

    def _project(self, owner: str | int, name: str, create_root: bool = True) -> tuple[str, Path]:
        normalized = str(name or "").strip().lower().replace("_", "-")
        if not _NAME_RE.fullmatch(normalized):
            raise ValueError("Project name must use 2–63 lowercase letters, digits, or hyphens and start with a letter.")
        owner_name = self._owner(owner)
        owner_root = (self.root / owner_name).resolve()
        if create_root:
            owner_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = (owner_root / normalized).resolve()
        if owner_root not in path.parents:
            raise PermissionError("Workspace project path must remain inside Lily’s code-workspace root.")
        return normalized, path

    @staticmethod
    def _relative(path: str) -> Path:
        candidate = Path(str(path or "").strip())
        if not str(candidate) or candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("File and directory paths must be relative and stay inside the selected workspace.")
        return candidate

    def _templates(self, language: str, brief: str) -> dict[str, str]:
        note = _clean_text(brief, "A Lily-generated starter project.", 500)
        templates = {
            "python": {"main.py": f'"""{note}"""\n\ndef main() -> None:\n    print("Hello from Lily")\n\n\nif __name__ == "__main__":\n    main()\n', "requirements.txt": ""},
            "javascript": {"index.js": f"// {note}\nconsole.log('Hello from Lily');\n", "package.json": json.dumps({"name": "lily-project", "private": True, "version": "0.1.0", "scripts": {"start": "node index.js"}}, indent=2) + "\n"},
            "typescript": {"index.ts": f"// {note}\nconsole.log('Hello from Lily');\n", "tsconfig.json": json.dumps({"compilerOptions": {"target": "ES2022", "strict": True}}, indent=2) + "\n"},
            "html": {"index.html": f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Lily project</title></head><body><main><h1>Hello from Lily</h1><p>{note}</p></main></body></html>\n"},
            "css": {"styles.css": f"/* {note} */\n:root {{ color-scheme: light dark; }}\nbody {{ margin: 0; font-family: system-ui, sans-serif; }}\n"},
            "json": {"data.json": json.dumps({"title": "Lily project", "brief": note}, ensure_ascii=False, indent=2) + "\n"},
            "yaml": {"config.yaml": f"title: Lily project\nbrief: {json.dumps(note, ensure_ascii=False)}\n"},
            "bash": {"main.sh": f"#!/usr/bin/env bash\nset -euo pipefail\n# {note}\nprintf '%s\\n' 'Hello from Lily'\n"},
            "java": {"Main.java": f"// {note}\npublic final class Main {{\n  public static void main(String[] args) {{\n    System.out.println(\"Hello from Lily\");\n  }}\n}}\n"},
            "csharp": {"Program.cs": f"// {note}\nConsole.WriteLine(\"Hello from Lily\");\n"},
            "go": {"main.go": f"// {note}\npackage main\n\nimport \"fmt\"\n\nfunc main() {{ fmt.Println(\"Hello from Lily\") }}\n"},
            "rust": {"main.rs": f"// {note}\nfn main() {{\n    println!(\"Hello from Lily\");\n}}\n"},
        }
        return templates[language]

    def create_project(self, owner: str | int, name: str, language: str, brief: str = "") -> dict[str, Any]:
        slug, project = self._project(owner, name)
        if project.exists():
            raise FileExistsError(f"The Lily workspace {slug!r} already exists. Use the editor commands to update it.")
        language = _language(language)
        project.mkdir(mode=0o700)
        try:
            templates = self._templates(language, brief)
            for relative, content in templates.items():
                target = project / relative
                target.write_text(content, encoding="utf-8")
                if target.suffix == ".sh":
                    os.chmod(target, 0o700)
            (project / "README.md").write_text(
                f"# {slug}\n\nLanguage: `{language}`\n\n{_clean_text(brief, 'Generated by Lily.', 500)}\n",
                encoding="utf-8",
            )
            (project / ".lily-project.json").write_text(
                json.dumps({"schema": 1, "project": slug, "language": language, "generator": "Lily", "created_at": int(time.time())}, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:
            shutil.rmtree(project, ignore_errors=True)
            raise
        return {"owner": self._owner(owner), "project": slug, "language": language, "path": str(project), "files": self.tree(owner, slug)}

    def mkdir(self, owner: str | int, project: str, directory: str) -> dict[str, Any]:
        slug, root = self._project(owner, project, create_root=False)
        if not root.is_dir():
            raise FileNotFoundError(f"Workspace {slug!r} does not exist.")
        target = (root / self._relative(directory)).resolve()
        if root not in target.parents:
            raise PermissionError("Directory must remain inside the selected workspace.")
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        return {"owner": self._owner(owner), "project": slug, "directory": str(target.relative_to(root))}

    def write_file(self, owner: str | int, project: str, relative_path: str, content: str) -> dict[str, Any]:
        slug, root = self._project(owner, project, create_root=False)
        if not root.is_dir():
            raise FileNotFoundError(f"Workspace {slug!r} does not exist.")
        target = (root / self._relative(relative_path)).resolve()
        if root not in target.parents:
            raise PermissionError("File must remain inside the selected workspace.")
        encoded = str(content).encode("utf-8")
        if len(encoded) > _MAX_FILE_BYTES:
            raise ValueError("Workspace file content exceeds Lily’s 512 KB editor limit.")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(encoded)
        return {"owner": self._owner(owner), "project": slug, "file": str(target.relative_to(root)), "bytes": len(encoded)}

    def tree(self, owner: str | int, project: str) -> list[dict[str, Any]]:
        _, root = self._project(owner, project, create_root=False)
        if not root.is_dir():
            raise FileNotFoundError("Workspace does not exist.")
        entries: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*")):
            if len(entries) >= _MAX_ARCHIVE_FILES:
                break
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            if root not in resolved.parents:
                continue
            entries.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size})
        return entries

    def archive(self, owner: str | int, project: str) -> Path:
        slug, root = self._project(owner, project, create_root=False)
        entries = self.tree(owner, slug)
        total = sum(int(item["bytes"]) for item in entries)
        if not entries:
            raise ValueError("The workspace has no files to archive.")
        if total > _MAX_ARCHIVE_BYTES:
            raise ValueError("The workspace exceeds Lily’s 20 MB source archive limit.")
        owner_root = root.parent
        destination = owner_root / f"{slug}.zip"
        with tempfile.NamedTemporaryFile(prefix=f".{slug}-", suffix=".zip", dir=owner_root, delete=False) as handle:
            temporary = Path(handle.name)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for entry in entries:
                    source = root / str(entry["path"])
                    archive.write(source, arcname=str(entry["path"]))
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def validate(self, owner: str | int, project: str) -> dict[str, Any]:
        slug, root = self._project(owner, project, create_root=False)
        files = self.tree(owner, slug)
        checked: list[str] = []
        for entry in files:
            relative = str(entry["path"])
            target = root / relative
            if target.suffix == ".py":
                py_compile.compile(str(target), doraise=True)
                checked.append(relative)
            elif target.suffix == ".json":
                json.loads(target.read_text(encoding="utf-8"))
                checked.append(relative)
        return {"owner": self._owner(owner), "project": slug, "checked": checked, "execution": False, "note": "Lily performed fixed syntax checks only; it did not run project code."}


code_workspace = CodeWorkspace()
