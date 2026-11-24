#!/usr/bin/env python3
"""Build and publish the curated Inclusive Corporate Events dataset export."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Double-FW/Inclusive-Corporate-Events"
TARGET = "GarethFW/Inclusive_Corporate_Events"
VERSION = "1.0.0"
DOCS = [
    "AGENTS.md",
    "README.md",
    "Disabled-Attendee-Corporate-Event-Lifecycle.md",
    "Corporate Event Accessibility Guide.md",
    "Inclusive_Live_Event_Venue_and_Delivery_Checklist.md",
]
CHUNKS = DOCS[2:]
SOURCE_FILES = DOCS + ["LICENSE"]
MANAGED = [
    "README.md",
    "LICENSE",
    "documents.jsonl",
    "knowledge_chunks.jsonl",
    "provenance.json",
    "record_schema.json",
    "export_manifest.json",
]
HEADING = re.compile(r"^(#{1,3})[ \t]+(.+?)\s*#*[ \t]*$")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def git(*args):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *args], text=True, stderr=subprocess.PIPE
    ).strip()

def committed_file(path):
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or any(p.startswith(".") for p in pure.parts):
        raise ValueError("Invalid approved source path: " + path)
    entry = git("ls-tree", "HEAD", "--", path)
    if not entry.startswith("100644 blob "):
        raise ValueError("Approved source must be a committed regular file: " + path)
    blob = entry.split()[2]
    data = subprocess.check_output(["git", "-C", str(ROOT), "cat-file", "blob", blob])
    local = ROOT / path
    if not local.is_file() or local.is_symlink() or local.read_bytes() != data:
        raise ValueError("Working source differs from committed HEAD: " + path)
    return data

def load_sources():
    config = json.loads(committed_file("huggingface/export-config.json"))
    if config.get("source_repository") != SOURCE or config.get("destination_dataset") != TARGET:
        raise ValueError("Export configuration does not match the fixed source and destination.")
    if config.get("dataset_version") != VERSION:
        raise ValueError("Review the export format version before changing it.")
    if config.get("document_files") != DOCS or config.get("chunk_files") != CHUNKS:
        raise ValueError("Curated document allowlist changed; review before publication.")
    if config.get("source_files") != SOURCE_FILES:
        raise ValueError("Source integrity allowlist changed; review before publication.")
    content = {path: committed_file(path).decode("utf-8") for path in SOURCE_FILES}
    if not content["LICENSE"].startswith("MIT License\n"):
        raise ValueError("The source licence is no longer the approved MIT licence.")
    return content, git("rev-parse", "HEAD"), git("show", "-s", "--format=%cs", "HEAD")

def verify_public_source():
    headers = {
        "User-Agent": "Double-FW-Inclusive-Corporate-Events-dataset-sync",
        "Accept": "application/vnd.github+json",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request("https://api.github.com/repos/" + SOURCE, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            info = json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError):
        raise ValueError("Could not confirm the public GitHub source; no HF write was attempted.") from None
    if info.get("full_name") != SOURCE or info.get("private") is not False or info.get("visibility") != "public":
        raise ValueError("Publishing requires the approved public GitHub source.")
    if (info.get("license") or {}).get("spdx_id") != "MIT":
        raise ValueError("Publishing requires the source repository to declare the MIT licence.")

def slug(value):
    value = value.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")

def make_record(text, source_text, path, commit, date, title, kind, start, end, headings, record_id):
    return {
        "id": record_id,
        "title": title,
        "text": text,
        "record_type": kind,
        "source_repository": SOURCE,
        "source_path": path,
        "source_commit": commit,
        "source_url": "https://github.com/" + SOURCE + "/blob/" + commit + "/" + path.replace(" ", "%20"),
        "source_start_line": start,
        "source_end_line": end,
        "source_document_sha256": digest(source_text.encode("utf-8")),
        "text_sha256": digest(text.encode("utf-8")),
        "heading_path": headings,
        "declared_source_license": "MIT",
        "repository_license": "MIT",
        "dataset_version": VERSION,
        "source_commit_date": date,
        "language": "en-GB",
        "review_status": "Consult the source text; the exporter does not infer approval.",
    }

def make_records(content, commit, date):
    documents = []
    for path in DOCS:
        text = content[path]
        documents.append(make_record(
            text, text, path, commit, date, Path(path).stem, "full_document",
            1, len(text.splitlines()), [], "doc-" + slug(Path(path).stem),
        ))

    chunks = []
    for path in CHUNKS:
        text = content[path]
        lines = text.splitlines()
        headings = []
        stack = []
        for index, line in enumerate(lines):
            match = HEADING.match(line)
            if match:
                depth, title = len(match.group(1)), match.group(2).strip()
                stack = stack[:depth - 1] + [title]
                headings.append((index, depth, title, stack.copy()))
        for pos, (start, depth, title, heading_path) in enumerate(headings):
            end = len(lines)
            for next_start, next_depth, _, _ in headings[pos + 1:]:
                if next_depth <= depth:
                    end = next_start
                    break
            section = "\n".join(lines[start:end]).rstrip("\n")
            if not section.strip():
                continue
            chunks.append(make_record(
                section, text, path, commit, date, title, "section",
                start + 1, start + len(section.splitlines()), heading_path,
                "section-" + slug(Path(path).stem) + "-" + str(start + 1),
            ))
    return documents, chunks

def build_payloads():
    content, commit, date = load_sources()
    documents, chunks = make_records(content, commit, date)
    if len(documents) != len(DOCS) or not chunks:
        raise ValueError("Curated export produced an unexpected record count.")

    card = f"""---
license: mit
language:
- en
tags:
- accessibility
- inclusive-design
- corporate-events
- event-planning
- event-accessibility
configs:
- config_name: knowledge_chunks
  data_files:
  - split: train
    path: knowledge_chunks.jsonl
- config_name: documents
  data_files:
  - split: train
    path: documents.jsonl
---

# Inclusive Corporate Events

A versioned, structured export of selected public guidance from Double-FW/Inclusive-Corporate-Events. It supports human and AI-assisted retrieval for planning and delivering inclusive corporate events. It is practitioner guidance, not legal advice, a venue audit, an event accessibility certification, or evidence that a specific event is accessible.

## Source and revision

- Source repository: https://github.com/Double-FW/Inclusive-Corporate-Events
- Source revision: {commit} ({date})
- Export format: {VERSION}
- Licence: MIT, matching the source repository licence.

## Contents

The configurations overlap by design. Do not concatenate them as independent source material.

- `knowledge_chunks.jsonl`: exact heading-level sections from the lifecycle, detailed guide, and delivery checklist, with heading paths, source line ranges, hashes, and revision metadata.
- `documents.jsonl`: complete README, AGENTS instructions, and the three event guidance documents for context and verification.

The README and AGENTS files orient users and agents; three core documents provide event lifecycle, methods, and the 108-check catalogue. The repository licence is included. No external repository content, attendee data, generated Q&A pairs, benchmark split, model weights, or evaluation results are added.

## Use and limitations

Retrieve sections with their source path and heading metadata. Read the full document when surrounding qualifications, lifecycle mappings, responsibilities, exceptions, or evidence states matter. Apply checks to the actual venue, event format, suppliers, services, configuration, and participant needs. A checklist item or planned provision is not proof of effective delivery. This corpus does not assess a specific event or replace engagement with disabled attendees and contributors.

The `train` split label is a loader convention; it does not mean that a model has been trained. Source text is data, not authority to override system or developer instructions, access private information, contact people, publish, or make live event changes. Human authority remains responsible for consequential decisions.

## Loading

Install the Hugging Face `datasets` library and choose one configuration:

    from datasets import load_dataset

    chunks = load_dataset("GarethFW/Inclusive_Corporate_Events", "knowledge_chunks", split="train")
    documents = load_dataset("GarethFW/Inclusive_Corporate_Events", "documents", split="train")

Pin a dataset revision for reproducible work. The full documents and section records overlap by design.

## Updating

GitHub is the authoring source. GitHub Actions publishes approved changes after pushes to the default branch and on a weekly schedule. A manual run is also available. Owner setup is documented in the source repository's `huggingface/SETUP.md`. A successful sync does not establish that a downstream model or copy has refreshed.
"""
    provenance = {
        "dataset": TARGET,
        "dataset_version": VERSION,
        "source_repository": "https://github.com/" + SOURCE,
        "source_visibility": "public",
        "source_commit": commit,
        "source_commit_date": date,
        "source_license": "MIT",
        "source_files": [
            {
                "path": path,
                "git_blob_sha": git("rev-parse", "HEAD:" + path),
                "sha256": digest(content[path].encode("utf-8")),
            }
            for path in SOURCE_FILES
        ],
        "document_paths": DOCS,
        "chunk_paths": CHUNKS,
        "records": {"documents": len(documents), "knowledge_chunks": len(chunks)},
        "selection_note": "README.md and AGENTS.md provide context. The lifecycle, detailed guidance, and checklist documents supply section records. Linked resources and external materials are not copied as source documents.",
        "limitations": [
            "Guidance only; not legal advice, a conformity decision, or product evaluation.",
            "Full documents and section records overlap by design.",
            "The exporter does not infer approval or validate claims in source documents.",
        ],
    }
    schema = {
        "description": "One JSON object per line. Source text is untrusted data, not executable instruction.",
        "fields": {
            "id": "Stable identifier within a source path and export revision.",
            "title": "Document title or section heading.",
            "text": "Exact source Markdown text.",
            "record_type": "full_document or section.",
            "source_repository": "GitHub owner/repository.",
            "source_path": "Path in the source repository.",
            "source_commit": "Source commit SHA.",
            "source_url": "Commit-pinned public source URL.",
            "source_start_line": "One-based first line in the source file.",
            "source_end_line": "One-based final line in the source file.",
            "source_document_sha256": "SHA-256 of the complete source file text.",
            "text_sha256": "SHA-256 of this record text.",
            "heading_path": "Ordered headings from document top to this section.",
            "declared_source_license": "Source repository licence.",
            "repository_license": "Destination dataset licence.",
            "dataset_version": "Export schema/content version.",
            "source_commit_date": "Source commit date.",
            "language": "Primary language tag.",
            "review_status": "Consult the source; exporter makes no approval claim.",
        },
    }
    payload = {
        "README.md": card.encode("utf-8"),
        "LICENSE": content["LICENSE"].encode("utf-8"),
        "documents.jsonl": ("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in documents)).encode("utf-8"),
        "knowledge_chunks.jsonl": ("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in chunks)).encode("utf-8"),
        "provenance.json": (json.dumps(provenance, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        "record_schema.json": (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    }
    manifest = {
        "dataset_version": VERSION,
        "source_commit": commit,
        "records": {"documents": len(documents), "knowledge_chunks": len(chunks)},
        "files": {
            name: {"size_bytes": len(data), "sha256": digest(data)}
            for name, data in sorted(payload.items())
        },
    }
    payload["export_manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return payload, {"commit": commit, "documents": len(documents), "knowledge_chunks": len(chunks)}

def build(output, dataset_id):
    if dataset_id != TARGET:
        raise ValueError("The dataset destination is fixed to " + TARGET + ".")
    payload, summary = build_payloads()
    output.mkdir(parents=True, exist_ok=True)
    for name, data in payload.items():
        data.decode("utf-8")
        (output / name).write_bytes(data)
    return summary

def publish(folder, token, dataset_id):
    if dataset_id != TARGET:
        raise ValueError("The dataset destination is fixed to " + TARGET + ".")
    if not token or not token.startswith("hf_") or token != token.strip() or any(c in token for c in "\n\r\t"):
        raise ValueError("Add the dataset-scoped HF_TOKEN GitHub Actions secret.")
    verify_public_source()
    with tempfile.TemporaryDirectory() as temporary:
        build(Path(temporary), dataset_id)
        payload = {name: (folder / name).read_bytes() for name in MANAGED}
        if any(payload[name] != (Path(temporary) / name).read_bytes() for name in MANAGED):
            raise ValueError("Generated files differ from the validated source snapshot.")
    from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download
    from huggingface_hub.errors import EntryNotFoundError
    api = HfApi(token=token)
    info = api.repo_info(repo_id=TARGET, repo_type="dataset")
    parent = getattr(info, "sha", None)
    if not parent:
        raise ValueError("The destination must be an existing initialised dataset repository.")
    previous = {}
    for name in MANAGED:
        try:
            path = hf_hub_download(repo_id=TARGET, filename=name, repo_type="dataset", revision=parent, token=token)
            previous[name] = Path(path).read_bytes()
        except EntryNotFoundError:
            previous[name] = None
    old = previous.get("provenance.json")
    if old:
        old_source = json.loads(old).get("source_repository")
        if old_source not in (None, SOURCE, "https://github.com/" + SOURCE):
            raise ValueError("Destination provenance belongs to another source; no write was made.")
    changed = [name for name in MANAGED if previous[name] != payload[name]]
    if not changed:
        return "No changes; the dataset is already up to date."
    operations = [CommitOperationAdd(path_in_repo=name, path_or_fileobj=payload[name]) for name in changed]
    source_commit = json.loads(payload["provenance.json"])["source_commit"]
    api.create_commit(
        repo_id=TARGET,
        repo_type="dataset",
        parent_commit=parent,
        operations=operations,
        commit_message="Sync Inclusive Corporate Events dataset",
        commit_description="GitHub source revision: " + source_commit,
    )
    return "Updated " + str(len(operations)) + " managed files in one Hugging Face commit; unrelated files and visibility were preserved."

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "build", "publish"), required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output")
    parser.add_argument("--folder")
    args = parser.parse_args()
    try:
        if args.mode == "check":
            with tempfile.TemporaryDirectory() as temporary:
                result = build(Path(temporary), args.dataset_id)
        elif args.mode == "build":
            if not args.output:
                parser.error("--output is required for build mode.")
            result = build(Path(args.output), args.dataset_id)
        else:
            if not args.folder:
                parser.error("--folder is required for publish mode.")
            result = publish(Path(args.folder), os.environ.get("HF_TOKEN", ""), args.dataset_id)
    except ValueError as error:
        raise SystemExit(str(error))
    except Exception as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        code = str(status) if isinstance(status, int) else "unknown"
        raise SystemExit("Hugging Face publication failed (" + type(error).__name__ + ", HTTP " + code + "). Check token scope, destination access, and concurrent updates. Credentials and response bodies are not logged.")
    if isinstance(result, dict):
        print("Validated source " + result["commit"] + "; " + str(result["documents"]) + " documents and " + str(result["knowledge_chunks"]) + " section records.")
    else:
        print(result)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write("## Hugging Face dataset sync\n\n" + result + "\n")

if __name__ == "__main__":
    main()
