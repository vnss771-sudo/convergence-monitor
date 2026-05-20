#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly DEFAULT_REPO_URL="https://github.com/vnss771-sudo/convergence-monitor.git"
readonly DEFAULT_OUTPUT="${HOME}/convergence-monitor-source.zip"

usage() {
  cat <<'USAGE'
Usage:
  bash build_pinned_source_zip.sh --ref <tag|branch|commit> [options]

Required:
  --ref VALUE              Git ref to package. Prefer a tag or full commit SHA.

Options:
  --repo-url URL           Repository URL.
  --branch NAME            Fallback branch used when fetching a raw commit SHA.
  --expected-commit SHA    Refuse to package unless HEAD resolves to this SHA.
  --output PATH            Output zip path.
  --keep-work-dir          Do not remove the temporary clone.
  --allow-floating-ref     Allow branch names such as main.

Examples:
  bash build_pinned_source_zip.sh --ref v0.1.0-mvp-rc
  bash build_pinned_source_zip.sh --ref b7a2456 --branch main --expected-commit <full-sha>
USAGE
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

is_sha_like() {
  [[ "$1" =~ ^[0-9a-fA-F]{7,40}$ ]]
}

is_probably_floating_ref() {
  [[ "$1" =~ ^(main|master|develop|dev|release/.*|feature/.*|hotfix/.*)$ ]]
}

utc_now() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
    return
  fi
  python3 - "$1" <<'PY'
from pathlib import Path
import hashlib
import sys

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

write_manifest() {
  local export_dir="$1"
  local repo_url="$2"
  local requested_ref="$3"
  local actual_commit="$4"

  python3 - "$export_dir" "$repo_url" "$requested_ref" "$actual_commit" "$(utc_now)" <<'PY'
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys

export_dir = Path(sys.argv[1])
repo_url = sys.argv[2]
requested_ref = sys.argv[3]
actual_commit = sys.argv[4]
created_at_utc = sys.argv[5]

files = []
for path in sorted(export_dir.rglob("*")):
    if not path.is_file():
        continue
    rel = path.relative_to(export_dir).as_posix()
    if rel == "SOURCE_MANIFEST.json":
        continue
    files.append(
        {
            "path": rel,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        }
    )

manifest = {
    "schema_version": 1,
    "created_at_utc": created_at_utc,
    "repo_url": repo_url,
    "requested_ref": requested_ref,
    "resolved_commit": actual_commit,
    "file_count": len(files),
    "files": files,
}

(export_dir / "SOURCE_MANIFEST.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
}

remove_non_release_files() {
  local export_dir="$1"

  find "$export_dir" \
    \( -name ".git" -o -name ".venv" -o -name "__pycache__" -o -name ".pytest_cache" -o -name "htmlcov" -o -name "dist" -o -name "build" \) \
    -type d -prune -exec rm -rf {} +

  find "$export_dir" \
    \( -name "*.pyc" -o -name ".coverage" -o -name "*.egg-info" -o -name "*.zip" \) \
    -exec rm -rf {} +

  rm -rf \
    "$export_dir/data/raw" \
    "$export_dir/data/processed" \
    "$export_dir/data/runs" \
    "$export_dir/data/live_proof_sessions"

  rm -f \
    "$export_dir"/LIVE_HISTORY_OUTPUT.json \
    "$export_dir"/LIVE_PROOF_REPORT*.md
}

repo_url="$DEFAULT_REPO_URL"
ref=""
branch="main"
expected_commit=""
output_path="$DEFAULT_OUTPUT"
keep_work_dir=0
allow_floating_ref=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-url)
      repo_url="${2:-}"
      shift 2
      ;;
    --ref)
      ref="${2:-}"
      shift 2
      ;;
    --branch)
      branch="${2:-}"
      shift 2
      ;;
    --expected-commit)
      expected_commit="${2:-}"
      shift 2
      ;;
    --output)
      output_path="${2:-}"
      shift 2
      ;;
    --keep-work-dir)
      keep_work_dir=1
      shift
      ;;
    --allow-floating-ref)
      allow_floating_ref=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$ref" ]] || { usage >&2; die "--ref is required"; }
[[ -n "$repo_url" ]] || die "--repo-url cannot be empty"
[[ -n "$output_path" ]] || die "--output cannot be empty"

if [[ "$allow_floating_ref" -ne 1 ]] && is_probably_floating_ref "$ref"; then
  die "ref '$ref' looks floating; pass a tag/full SHA or add --allow-floating-ref"
fi

need_cmd git
need_cmd zip
need_cmd tar
need_cmd python3

work_root="$(mktemp -d "${TMPDIR:-/tmp}/convergence-monitor-build.XXXXXX")"
repo_dir="${work_root}/repo"
export_dir="${work_root}/export"

cleanup() {
  if [[ "$keep_work_dir" -eq 0 ]]; then
    rm -rf "$work_root"
  else
    printf 'kept work dir: %s\n' "$work_root" >&2
  fi
}
trap cleanup EXIT

git init -q "$repo_dir"
git -C "$repo_dir" remote add origin "$repo_url"

if ! git -C "$repo_dir" fetch --depth 1 origin "$ref"; then
  if is_sha_like "$ref"; then
    git -C "$repo_dir" fetch --depth 100 origin "$branch"
  else
    die "failed to fetch ref: $ref"
  fi
fi

git -C "$repo_dir" checkout -q --detach "$ref" 2>/dev/null || git -C "$repo_dir" checkout -q --detach FETCH_HEAD

actual_commit="$(git -C "$repo_dir" rev-parse HEAD)"

if [[ -n "$expected_commit" && "$actual_commit" != "$expected_commit" ]]; then
  die "resolved commit $actual_commit does not match expected commit $expected_commit"
fi

mkdir -p "$export_dir"
git -C "$repo_dir" archive --format=tar HEAD | tar -x -C "$export_dir"

remove_non_release_files "$export_dir"
write_manifest "$export_dir" "$repo_url" "$ref" "$actual_commit"

mkdir -p "$(dirname "$output_path")"
rm -f "$output_path"

(
  cd "$export_dir"
  zip -qr "$output_path" .
)

printf '%s  %s\n' "$(sha256_file "$output_path")" "$output_path" > "${output_path}.sha256"

printf 'created: %s\n' "$output_path"
printf 'sha256:  %s\n' "$(cat "${output_path}.sha256" | awk '{print $1}')"
printf 'commit:  %s\n' "$actual_commit"
