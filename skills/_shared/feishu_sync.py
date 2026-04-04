#!/usr/bin/env python3
"""Sync local markdown notes to Feishu docs through lark-cli.

This keeps the existing local markdown workflow intact, but adds a Feishu
publishing layer on top so the repo no longer depends on Obsidian as the
final reading surface.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

_SHARED_DIR = Path(__file__).resolve().parent
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from user_config import backend_name, feishu_config, knowledge_base_root_path

_IMAGE_LINK_RE = re.compile(r"!\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_MD_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_DOC_URL_RE = re.compile(r"https?://[^\s\"']+")


@dataclass
class RenderResult:
    markdown: str
    local_media: list[Path]
    unresolved_links: list[str]


def _expand(path_value: str) -> Path:
    return Path(path_value).expanduser()


def cli_path() -> str:
    configured = str(feishu_config().get("cli_path", "")).strip()
    if configured:
        expanded = str(_expand(configured))
        if Path(expanded).exists():
            return expanded

    found = shutil.which("lark-cli")
    if found:
        return found

    raise FileNotFoundError(
        "lark-cli not found. Set publishing.feishu.cli_path in user-config.local.json."
    )


def manifest_path() -> Path:
    return knowledge_base_root_path() / feishu_config().get("manifest_file", ".feishu_manifest.json")


def load_manifest() -> dict:
    path = manifest_path()
    if not path.exists():
        return {"version": 1, "files": {}}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {"version": 1, "files": {}}
    data.setdefault("version", 1)
    data.setdefault("files", {})
    return data


def save_manifest(manifest: dict) -> None:
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)


def build_markdown_index(root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for note in root.rglob("*.md"):
        if note.name.startswith("."):
            continue
        relative = note.relative_to(root).with_suffix("").as_posix().lower()
        index.setdefault(relative, []).append(note)
        index.setdefault(note.stem.lower(), []).append(note)
    return index


def resolve_note_path(token: str, source_path: Path, root: Path, index: dict[str, list[Path]]) -> Path | None:
    normalized = token.strip().replace("\\", "/")
    candidates: list[Path] = []

    if "/" in normalized:
        root_candidate = root / normalized
        local_candidate = source_path.parent / normalized
        candidates.extend(
            [
                root_candidate.with_suffix(".md"),
                local_candidate.with_suffix(".md"),
            ]
        )

    matches = index.get(normalized.lower(), [])
    candidates.extend(matches)

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def resolve_local_media(token: str, source_path: Path, root: Path) -> Path | None:
    normalized = token.strip().replace("\\", "/")
    candidates = [
        source_path.parent / normalized,
        source_path.parent / "assets" / normalized,
        root / normalized,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _strip_optional_title(target: str) -> str:
    cleaned = target.strip()
    if ' "' in cleaned and cleaned.endswith('"'):
        cleaned = cleaned.rsplit(' "', 1)[0]
    if " '" in cleaned and cleaned.endswith("'"):
        cleaned = cleaned.rsplit(" '", 1)[0]
    return cleaned.strip()


def _is_external_target(target: str) -> bool:
    lowered = target.lower()
    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or lowered.startswith("#")
    )


def _extract_frontmatter_metadata(text: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')

    return metadata, text[match.end():]


def _render_metadata_block(metadata: dict[str, str]) -> str:
    if not metadata:
        return ""

    preferred_keys = ("date", "created", "title", "method_name", "tags")
    lines = []
    for key in preferred_keys:
        value = metadata.get(key)
        if value:
            lines.append(f"> {key}: {value}")

    if not lines:
        return ""

    return "\n".join(lines) + "\n\n"


def render_for_feishu(
    *,
    source_path: Path,
    root: Path,
    index: dict[str, list[Path]],
    manifest: dict,
    prefer_urls: bool,
) -> RenderResult:
    root = root.resolve()
    source_path = source_path.resolve()
    raw_text = source_path.read_text(encoding="utf-8")
    metadata, body = _extract_frontmatter_metadata(raw_text)
    media_files: list[Path] = []
    unresolved_links: list[str] = []

    def replace_image(match: re.Match[str]) -> str:
        token = match.group(1)
        media_path = resolve_local_media(token, source_path, root)
        if media_path:
            media_files.append(media_path)
            return f"> [图片将在文末追加上传: {media_path.name}]"
        return match.group(0)

    body = _IMAGE_LINK_RE.sub(replace_image, body)

    def replace_markdown_image(match: re.Match[str]) -> str:
        token = _strip_optional_title(match.group(2))
        if _is_external_target(token):
            return match.group(0)
        media_path = resolve_local_media(token, source_path, root)
        if media_path:
            media_files.append(media_path)
            alt = match.group(1) or media_path.name
            return f"> [图片将在文末追加上传: {alt}]"
        return match.group(0)

    body = _MD_IMAGE_RE.sub(replace_markdown_image, body)

    def replace_wikilink(match: re.Match[str]) -> str:
        token = match.group(1)
        label = match.group(2) or Path(token).name
        note_path = resolve_note_path(token, source_path, root, index)
        if not note_path:
            unresolved_links.append(token)
            return label

        relative = note_path.relative_to(root).as_posix()
        entry = manifest.get("files", {}).get(relative, {})
        if prefer_urls and entry.get("url"):
            return f"[{label}]({entry['url']})"
        if prefer_urls and entry.get("doc_ref"):
            return f"[{label}]({entry['doc_ref']})"
        unresolved_links.append(token)
        return label

    body = _WIKILINK_RE.sub(replace_wikilink, body)

    def replace_markdown_link(match: re.Match[str]) -> str:
        label = match.group(1)
        token = _strip_optional_title(match.group(2))
        if _is_external_target(token):
            return match.group(0)

        note_path = resolve_note_path(token, source_path, root, index)
        if not note_path:
            unresolved_links.append(token)
            return label

        relative = note_path.relative_to(root).as_posix()
        entry = manifest.get("files", {}).get(relative, {})
        if prefer_urls and entry.get("url"):
            return f"[{label}]({entry['url']})"
        if prefer_urls and entry.get("doc_ref"):
            return f"[{label}]({entry['doc_ref']})"
        unresolved_links.append(token)
        return label

    body = _MD_LINK_RE.sub(replace_markdown_link, body)
    markdown = _render_metadata_block(metadata) + body.strip() + "\n"
    return RenderResult(markdown=markdown, local_media=media_files, unresolved_links=sorted(set(unresolved_links)))


def _walk_json_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for key, inner in value.items():
            if isinstance(key, str):
                yield key
            yield from _walk_json_strings(inner)
        return
    if isinstance(value, list):
        for inner in value:
            yield from _walk_json_strings(inner)


def extract_doc_metadata(payload: object) -> dict[str, str]:
    strings = list(_walk_json_strings(payload))
    urls = [text for text in strings if _DOC_URL_RE.search(text)]
    doc_url = next((text for text in urls if "/docx/" in text or "/wiki/" in text), "")
    doc_ref = doc_url

    preferred_keys = ("document_id", "doc_token", "document_token", "token", "obj_token")
    token = ""
    if isinstance(payload, dict):
        stack = [payload]
        while stack and not token:
            current = stack.pop()
            for key, value in current.items():
                if isinstance(value, dict):
                    stack.append(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            stack.append(item)
                elif key in preferred_keys and isinstance(value, str) and value:
                    token = value
                    break

    if not doc_ref:
        doc_ref = token

    return {
        "url": doc_url,
        "token": token,
        "doc_ref": doc_ref,
    }


def run_cli(command: list[str], *, dry_run: bool) -> object:
    if dry_run and "--dry-run" not in command:
        command = [*command, "--dry-run"]

    proc = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(stderr or f"lark-cli exited with code {proc.returncode}")

    output = proc.stdout.strip()
    if not output:
        return {}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"raw_output": output}


def build_create_command(title: str, markdown: str) -> list[str]:
    config = feishu_config()
    command = [cli_path(), "docs", "+create", "--title", title, "--markdown", markdown]
    identity = str(config.get("identity", "user")).strip() or "user"
    command.extend(["--as", identity])

    folder_token = str(config.get("folder_token", "")).strip()
    wiki_space = str(config.get("wiki_space", "")).strip()
    wiki_node = str(config.get("wiki_node", "")).strip()

    if folder_token:
        command.extend(["--folder-token", folder_token])
    if wiki_space:
        command.extend(["--wiki-space", wiki_space])
    if wiki_node:
        command.extend(["--wiki-node", wiki_node])

    return command


def build_update_command(doc_ref: str, title: str, markdown: str) -> list[str]:
    config = feishu_config()
    command = [
        cli_path(),
        "docs",
        "+update",
        "--doc",
        doc_ref,
        "--mode",
        "overwrite",
        "--new-title",
        title,
        "--markdown",
        markdown,
    ]
    identity = str(config.get("identity", "user")).strip() or "user"
    command.extend(["--as", identity])
    return command


def insert_media(doc_ref: str, media_files: list[Path], *, dry_run: bool) -> int:
    config = feishu_config()
    identity = str(config.get("identity", "user")).strip() or "user"
    inserted = 0
    for media_path in media_files:
        command = [
            cli_path(),
            "docs",
            "+media-insert",
            "--doc",
            doc_ref,
            "--file",
            str(media_path),
            "--caption",
            media_path.name,
            "--as",
            identity,
        ]
        run_cli(command, dry_run=dry_run)
        inserted += 1
    return inserted


def sync_markdown_file(
    *,
    file_path: Path,
    root: Path,
    index: dict[str, list[Path]],
    manifest: dict,
    prefer_urls: bool,
    upload_media: bool,
    dry_run: bool,
) -> dict:
    rendered = render_for_feishu(
        source_path=file_path,
        root=root,
        index=index,
        manifest=manifest,
        prefer_urls=prefer_urls,
    )

    relative = file_path.relative_to(root).as_posix()
    title = file_path.stem
    existing = manifest.get("files", {}).get(relative, {})
    doc_ref = str(existing.get("doc_ref", "")).strip()

    if doc_ref:
        payload = run_cli(build_update_command(doc_ref, title, rendered.markdown), dry_run=dry_run)
        action = "updated"
    else:
        payload = run_cli(build_create_command(title, rendered.markdown), dry_run=dry_run)
        action = "created"

    doc_meta = extract_doc_metadata(payload)
    stored_ref = doc_meta.get("doc_ref") or doc_ref
    manifest.setdefault("files", {})[relative] = {
        "doc_ref": stored_ref,
        "title": title,
        "token": doc_meta.get("token", existing.get("token", "")),
        "url": doc_meta.get("url", existing.get("url", "")),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }

    media_inserted = 0
    if upload_media and stored_ref and rendered.local_media:
        unique_media = sorted(set(rendered.local_media), key=lambda path: str(path))
        media_inserted = insert_media(stored_ref, unique_media, dry_run=dry_run)

    return {
        "file": relative,
        "action": action,
        "unresolved_links": rendered.unresolved_links,
        "media_inserted": media_inserted,
    }


def collect_target_files(root: Path, file_args: list[str], dir_args: list[str]) -> list[Path]:
    files: set[Path] = set()

    for file_arg in file_args:
        candidate = Path(file_arg).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        if candidate.exists() and candidate.suffix == ".md":
            files.add(candidate.resolve())

    for dir_arg in dir_args:
        candidate = Path(dir_arg).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.exists():
            continue
        for note in candidate.rglob("*.md"):
            if note.name.startswith("."):
                continue
            files.add(note.resolve())

    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync markdown notes to Feishu docs")
    parser.add_argument("--file", action="append", default=[], help="Markdown file to sync")
    parser.add_argument("--dir", action="append", default=[], help="Directory containing markdown files to sync")
    parser.add_argument("--dry-run", action="store_true", help="Preview lark-cli requests without executing")
    args = parser.parse_args()

    if backend_name() != "feishu":
        print("publishing.backend is not 'feishu'; skipping sync.")
        return 0

    root = knowledge_base_root_path()
    files = collect_target_files(root, args.file, args.dir)
    if not files:
        print("No markdown files selected for sync.")
        return 0

    manifest = load_manifest()
    index = build_markdown_index(root)

    first_pass_results = []
    for file_path in files:
        first_pass_results.append(
            sync_markdown_file(
                file_path=file_path,
                root=root,
                index=index,
                manifest=manifest,
                prefer_urls=False,
                upload_media=False,
                dry_run=args.dry_run,
            )
        )
    save_manifest(manifest)

    second_pass_results = []
    for file_path in files:
        second_pass_results.append(
            sync_markdown_file(
                file_path=file_path,
                root=root,
                index=index,
                manifest=manifest,
                prefer_urls=True,
                upload_media=True,
                dry_run=args.dry_run,
            )
        )
    save_manifest(manifest)

    summary = {
        "root": str(root),
        "manifest": str(manifest_path()),
        "files": second_pass_results,
        "passes": {
            "first": first_pass_results,
            "second": second_pass_results,
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
