#!/usr/bin/env bash
#
# fleet-diff.sh -- before/after parity sweep between the pinned Python selfdoc
# and the Go rewrite, over every selfdoc-managed project on this machine.
#
# For each project it clones the repository twice (a local clone, so tags come
# along for multi-version builds), runs `gen`, `build` and `check --json` in
# each clone -- the pinned Python binary in one, the Go binary in the other --
# normalizes the outputs, diffs them, and writes .fleet-diff/report.md.
#
# Both clones get the SAME leaf directory name, because a project's name is
# derived from its directory and would otherwise leak into every title.
#
# Usage:
#   scripts/fleet-diff.sh --list                 # print the plan, touch nothing
#   scripts/fleet-diff.sh                        # sweep every project
#   scripts/fleet-diff.sh --repos rlsbl,safegit  # sweep a subset
#   scripts/fleet-diff.sh --reuse-clones         # keep existing clones
#
# Environment overrides: FLEET_DIR, PY_SELFDOC, GO_SELFDOC, PAGEFIND_PYTHON,
# FLEET_DIFF_TIMEOUT, FLEET_DIFF_PYREF, FLEET_DIFF_SITE_PACKAGES.
#
# Both sides run with the same PYTHONPATH, carrying the Python packages the
# pinned tool was installed against: selfdoc_core/selfblog (extracted from this
# repository's history into $ROOT/pyref, because the pinned install of
# selfdoc-core was an editable one pointing at the now-deleted source tree) and
# the pinned tool's own site-packages (strictcli, selfdoc, strictspec,
# tinymoon). Equalizing this is deliberate: the Python side resolves custom
# directive scripts by importing them in-process, where those modules are
# already loaded, while the Go side spawns `python3`, where they are not. A
# consumer script that imports selfdoc_core or strictcli would otherwise fail
# on the Go side only, and the sweep would report an environment difference as
# an engine difference. Which consumer scripts depend on those imports is a
# separate, static question.

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ROOT="$REPO_ROOT/.fleet-diff"
FLEET_DIR="${FLEET_DIR:-$(dirname "$REPO_ROOT")}"
PY_BIN="${PY_SELFDOC:-$HOME/.local/bin/selfdoc}"
GO_BIN="${GO_SELFDOC:-$REPO_ROOT/bin/selfdoc}"
PAGEFIND_PYTHON="${PAGEFIND_PYTHON:-$HOME/.local/share/uv/tools/selfdoc/bin/python3}"
CMD_TIMEOUT="${FLEET_DIFF_TIMEOUT:-600}"
PYREF="${FLEET_DIFF_PYREF:-$ROOT/pyref}"
SITE_PACKAGES="${FLEET_DIFF_SITE_PACKAGES:-$HOME/.local/share/uv/tools/selfdoc/lib/python3.13/site-packages}"

LIST_ONLY=0
REUSE_CLONES=0
SELECTED=""

while [ $# -gt 0 ]; do
  case "$1" in
    --list) LIST_ONLY=1 ;;
    --reuse-clones) REUSE_CLONES=1 ;;
    --repos) shift; SELECTED="${1:-}" ;;
    --repos=*) SELECTED="${1#--repos=}" ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# Project discovery: every /path/*/selfdoc.json, skipping dot-directories.
# ---------------------------------------------------------------------------
discover() {
  local f name
  for f in "$FLEET_DIR"/*/selfdoc.json; do
    [ -e "$f" ] || continue
    name=$(basename "$(dirname "$f")")
    case "$name" in
      .*|.archive) continue ;;
    esac
    if [ -n "$SELECTED" ]; then
      case ",$SELECTED," in
        *",$name,"*) ;;
        *) continue ;;
      esac
    fi
    printf '%s\n' "$name"
  done
}

REPOS=$(discover)
[ -n "$REPOS" ] || { echo "no projects matched" >&2; exit 1; }

if [ "$LIST_ONLY" = 1 ]; then
  echo "fleet-diff plan"
  echo "  fleet dir     : $FLEET_DIR"
  echo "  scratch root  : $ROOT (gitignored)"
  echo "  python binary : $PY_BIN"
  echo "  go binary     : $GO_BIN"
  echo "  timeout       : ${CMD_TIMEOUT}s per command"
  echo "  pagefind shim : $ROOT/bin/pagefind -> $PAGEFIND_PYTHON -m pagefind"
  echo "  PYTHONPATH    : $PYREF:$SITE_PACKAGES (both sides)"
  echo
  echo "for each project below, the sweep would:"
  echo "  1. git clone --quiet <repo> $ROOT/work/<name>/py/<name>"
  echo "  2. git clone --quiet <repo> $ROOT/work/<name>/go/<name>"
  echo "  3. run, in each clone: gen --no-auto-commit, build --no-auto-commit,"
  echo "     check --json --no-auto-commit (python binary in py/, go binary in go/)"
  echo "  4. snapshot docs/, the root files, the build output and the manifest"
  echo "  5. normalize both snapshots and diff them"
  echo "  6. append a section to $ROOT/runs/<timestamp>/report.md"
  echo
  printf '%s\n' "$REPOS" | sed 's/^/  - /'
  echo
  printf 'projects: %s\n' "$(printf '%s\n' "$REPOS" | wc -l)"
  exit 0
fi

[ -x "$PY_BIN" ] || { echo "python selfdoc not executable: $PY_BIN" >&2; exit 1; }
[ -x "$GO_BIN" ] || { echo "go selfdoc not executable: $GO_BIN (go build -o bin/selfdoc ./cmd/selfdoc)" >&2; exit 1; }

RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN="$ROOT/runs/$RUN_ID"
mkdir -p "$ROOT/work" "$ROOT/bin" "$RUN/logs" "$RUN/snap" "$RUN/norm"

# The Go binary looks for `python3 -m pagefind` and then a `pagefind` binary.
# The pinned Python tool carries pagefind inside its own virtualenv, so the
# shim below is what makes the Go side able to index at all. This is an
# environment provision, not a normalization.
cat > "$ROOT/bin/pagefind" <<EOF
#!/bin/sh
exec "$PAGEFIND_PYTHON" -m pagefind "\$@"
EOF
chmod +x "$ROOT/bin/pagefind"
export PATH="$ROOT/bin:$PATH"

if [ ! -d "$PYREF/selfdoc_core" ]; then
  echo "missing python reference tree at $PYREF/selfdoc_core" >&2
  echo "recreate it from the last commit that carried the Python packages:" >&2
  echo "  mkdir -p $PYREF && git archive <commit> selfdoc_core selfblog | tar -x -C $PYREF" >&2
  exit 1
fi
export PYTHONPATH="$PYREF:$SITE_PACKAGES"

# ---------------------------------------------------------------------------
# The normalizer. Named normalizations, all reported:
#   N1  drop .gz and .br companions
#   N2  drop the pagefind/ index directory
#   N3  og-*.png compared by dimensions only
#   N4  manifest.json: drop last_gen
#   N5  mask the interior of <code class="language-...">...</code>
#   N6  drop the highlight stylesheet (chroma replaced pygments)
#   N7  split HTML/XML at tag boundaries so diffs are line-oriented
# ---------------------------------------------------------------------------
NORMALIZER="$ROOT/bin/normalize.py"
cat > "$NORMALIZER" <<'PYEOF'
"""Normalize a selfdoc output tree for diffing. Usage: normalize.py SRC DST"""
import json
import os
import re
import struct
import sys

CODE_RE = re.compile(r'(<code class="language-[^"]*">)(.*?)(</code>)', re.S)
STYLE_RE = re.compile(r'(<style[^>]*>)(.*?)(</style>)', re.S)
HL_DECL_RE = re.compile(r'--sd-hl-[A-Za-z0-9_-]+\s*:[^;}]*;?')


def png_dimensions(path):
    with open(path, 'rb') as fh:
        head = fh.read(33)
    if head[:8] != b'\x89PNG\r\n\x1a\n' or head[12:16] != b'IHDR':
        return 'PNG unreadable'
    w, h = struct.unpack('>II', head[16:24])
    return 'PNG %dx%d' % (w, h)


def split_css(text):
    """Split minified CSS into top-level chunks (declaration runs and blocks)."""
    chunks, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                chunks.append(text[start:i + 1])
                start = i + 1
    if start < len(text):
        chunks.append(text[start:])
    return chunks


def strip_highlight(css):
    """N6: remove the generated highlight stylesheet from a CSS body.

    Drops --sd-hl-* custom properties, every rule whose body reads one, and
    every rule left empty by that removal. Recurses into at-rule blocks.
    """
    out = []
    for chunk in split_css(css):
        brace = chunk.find('{')
        if brace < 0:
            out.append(chunk)
            continue
        selector = chunk[:brace]
        body = chunk[brace + 1:-1]
        if selector.lstrip().startswith('@') and '{' in body:
            body = strip_highlight(body)
            if body.strip():
                out.append(selector + '{' + body + '}')
            continue
        body = HL_DECL_RE.sub('', body)
        if 'var(--sd-hl-' in body:
            body = ';'.join(d for d in body.split(';') if 'var(--sd-hl-' not in d)
        if not body.strip(';').strip():
            continue
        out.append(selector + '{' + body + '}')
    return ''.join(out)


def normalize_html(text):
    text = CODE_RE.sub(lambda m: m.group(1) + '[CODE]' + m.group(3), text)  # N5
    text = STYLE_RE.sub(
        lambda m: m.group(1) + strip_highlight(m.group(2)) + m.group(3), text)  # N6
    return text.replace('><', '>\n<')  # N7


def normalize_file(src, dst):
    base = os.path.basename(src)
    if base.endswith('.gz') or base.endswith('.br'):
        return  # N1
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if base.startswith('og-') and base.endswith('.png'):
        with open(dst, 'w') as fh:  # N3
            fh.write(png_dimensions(src) + '\n')
        return
    if base == 'manifest.json':
        with open(src, encoding='utf-8') as fh:
            doc = json.load(fh)
        if isinstance(doc, dict):
            doc.pop('last_gen', None)  # N4
        with open(dst, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write('\n')
        return
    try:
        with open(src, encoding='utf-8') as fh:
            text = fh.read()
    except (UnicodeDecodeError, ValueError):
        with open(src, 'rb') as fh:
            raw = fh.read()
        with open(dst, 'w') as fh:
            fh.write('binary %d bytes\n' % len(raw))
        return
    if base.endswith('.html'):
        text = normalize_html(text)
    elif base.endswith('.css'):
        text = strip_highlight(text)
        text = text.replace('}', '}\n')
    elif base.endswith('.xml') or base.endswith('.svg'):
        text = text.replace('><', '>\n<')  # N7
    with open(dst, 'w', encoding='utf-8') as fh:
        fh.write(text)


def main():
    src_root, dst_root = sys.argv[1], sys.argv[2]
    if not os.path.isdir(src_root):
        return
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [d for d in dirnames if d != 'pagefind']  # N2
        for name in sorted(filenames):
            src = os.path.join(dirpath, name)
            if os.path.islink(src) or not os.path.isfile(src):
                continue
            rel = os.path.relpath(src, src_root)
            normalize_file(src, os.path.join(dst_root, rel))


main()
PYEOF

# Reads the docs and output directories a project's selfdoc.json declares.
CONFIG_READER="$ROOT/bin/config_dirs.py"
cat > "$CONFIG_READER" <<'PYEOF'
import json
import sys

with open(sys.argv[1], encoding='utf-8') as fh:
    try:
        cfg = json.load(fh)
    except ValueError:
        cfg = {}
docs = str(cfg.get('docs', 'docs')).strip('/') or 'docs'
out = str(cfg.get('output', docs + '/_build')).strip('/') or docs + '/_build'
print(docs)
print(out)
PYEOF

# Extracts the payload of a strictcli machine-mode envelope, canonically.
PAYLOAD_READER="$ROOT/bin/payload.py"
cat > "$PAYLOAD_READER" <<'PYEOF'
import json
import sys

raw = open(sys.argv[1], encoding='utf-8', errors='replace').read()
start = raw.find('{"interface_version"')
if start < 0:
    print('NO ENVELOPE ON STDOUT')
    print(raw[:4000])
    raise SystemExit(0)
try:
    env = json.loads(raw[start:])
except ValueError as exc:
    print('UNPARSEABLE ENVELOPE: %s' % exc)
    print(raw[start:start + 4000])
    raise SystemExit(0)
print(json.dumps(env.get('payload'), indent=2, sort_keys=True))
PYEOF

# ---------------------------------------------------------------------------
# Per-command runner: records exit code, stdout and stderr, never aborts.
# ---------------------------------------------------------------------------
run_cmd() {
  local dir="$1" bin="$2" tag="$3" logdir="$4"; shift 4
  local code=0
  ( cd "$dir" && timeout "$CMD_TIMEOUT" "$bin" "$@" ) \
    > "$logdir/$tag.out" 2> "$logdir/$tag.err" || code=$?
  printf '%s\n' "$code" > "$logdir/$tag.exit"
  printf '%s' "$code"
}

REPORT="$RUN/report.md"
: > "$REPORT"
SUMMARY="$RUN/summary.tsv"
: > "$SUMMARY"

{
  echo "# Fleet diff: pinned Python selfdoc vs the Go rewrite"
  echo
  echo "- python: \`$PY_BIN\` ($("$PY_BIN" --version 2>/dev/null | head -1))"
  echo "- go: \`$GO_BIN\` ($("$GO_BIN" --version 2>/dev/null | head -1))"
  echo "- per-command timeout: ${CMD_TIMEOUT}s"
  echo
  echo "## Normalizations applied before diffing"
  echo
  echo "| id | normalization |"
  echo "| --- | --- |"
  echo "| N1 | \`.gz\` and \`.br\` companions dropped |"
  echo "| N2 | the \`pagefind/\` index directory dropped |"
  echo "| N3 | \`og-*.png\` compared by dimensions only, not bytes |"
  echo "| N4 | \`manifest.json\`: \`last_gen\` dropped |"
  echo "| N5 | the interior of \`<code class=\"language-...\">...</code>\` masked |"
  echo "| N6 | the generated highlight stylesheet dropped (chroma replaced pygments) |"
  echo "| N7 | HTML/XML split at tag boundaries, so diffs are line-oriented |"
  echo
  echo "Both sides run with PYTHONPATH=\`$PYREF:$SITE_PACKAGES\`, so a custom"
  echo "directive script imports the same modules whether the engine loads it"
  echo "in-process (Python) or spawns \`python3\` (Go)."
  echo
  echo "A \`pagefind\` shim is put on PATH for both sides (the pinned Python tool"
  echo "carries pagefind inside its own virtualenv; the Go binary needs it on PATH)."
  echo
} >> "$REPORT"

for name in $REPOS; do
  src="$FLEET_DIR/$name"
  work="$ROOT/work/$name"
  logs="$RUN/logs/$name"
  mkdir -p "$logs"
  echo "=== $name"

  for side in py go; do
    if [ "$REUSE_CLONES" = 1 ] && [ -d "$work/$side/$name/.git" ]; then
      continue
    fi
    mkdir -p "$work/$side"
    if [ -e "$work/$side/$name" ]; then
      if command -v saferm > /dev/null 2>&1; then
        saferm delete -r --on-error abort \
          --description "fleet-diff: superseded throwaway clone of $name ($side side), re-cloned for a fresh sweep" \
          "$work/$side/$name" > /dev/null
      else
        mkdir -p "$ROOT/superseded"
        mv "$work/$side/$name" "$ROOT/superseded/$name.$side.$(date +%s)"
      fi
    fi
    git clone --quiet "$src" "$work/$side/$name" 2> "$logs/clone-$side.err" || true
  done

  if [ ! -d "$work/py/$name/.git" ] || [ ! -d "$work/go/$name/.git" ]; then
    {
      echo "## $name"
      echo
      echo "CLONE FAILED -- see \`$logs/clone-*.err\`."
      echo
    } >> "$REPORT"
    printf '%s\tCLONE\tCLONE\tCLONE\tCLONE\tCLONE\tCLONE\t-\n' "$name" >> "$SUMMARY"
    continue
  fi

  read -r DOCS_DIR OUT_DIR < <(python3 "$CONFIG_READER" "$work/py/$name/selfdoc.json" | paste -s -)

  declare -A EXITS=()
  for side in py go; do
    bin="$PY_BIN"; [ "$side" = go ] && bin="$GO_BIN"
    dir="$work/$side/$name"
    EXITS[$side.gen]=$(run_cmd "$dir" "$bin" "$side-gen" "$logs" gen --no-auto-commit)
    # Snapshot the generated docs and root files before the build writes into
    # the output directory that lives underneath docs/.
    snap="$RUN/snap/$name/$side"
    mkdir -p "$snap/gen" "$snap/root" "$snap/build" "$snap/meta"
    if [ -d "$dir/$DOCS_DIR" ]; then
      ( cd "$dir" && tar cf - --exclude="./$OUT_DIR" --exclude="./$OUT_DIR/*" "./$DOCS_DIR" 2>/dev/null ) \
        | ( cd "$snap/gen" && tar xf - ) || true
    fi
    for rf in README.md CLAUDE.md AGENTS.md; do
      if [ -f "$dir/$rf" ]; then cp --remove-destination "$dir/$rf" "$snap/root/$rf"; fi
    done
    EXITS[$side.build]=$(run_cmd "$dir" "$bin" "$side-build" "$logs" build --no-auto-commit)
    if [ -d "$dir/$OUT_DIR" ]; then
      ( cd "$dir/$OUT_DIR" && tar cf - . ) | ( cd "$snap/build" && tar xf - ) || true
    fi
    if [ -f "$dir/.selfdoc/manifest.json" ]; then
      cp --remove-destination "$dir/.selfdoc/manifest.json" "$snap/meta/manifest.json"
    fi
    EXITS[$side.check]=$(run_cmd "$dir" "$bin" "$side-check" "$logs" check --json --no-auto-commit)
    python3 "$PAYLOAD_READER" "$logs/$side-check.out" > "$snap/meta/check-payload.json" || true
  done

  for side in py go; do
    for part in gen root build meta; do
      python3 "$NORMALIZER" "$RUN/snap/$name/$side/$part" "$RUN/norm/$name/$side/$part"
    done
  done

  python3 - "$name" "$RUN" "$REPORT" "$SUMMARY" "${EXITS[py.gen]}" "${EXITS[py.build]}" "${EXITS[py.check]}" "${EXITS[go.gen]}" "${EXITS[go.build]}" "${EXITS[go.check]}" <<'PYEOF'
import difflib
import os
import sys

name, root, report_path, summary_path = sys.argv[1:5]
py_gen, py_build, py_check, go_gen, go_build, go_check = sys.argv[5:11]

norm = os.path.join(root, 'norm', name)
PY = os.path.join(norm, 'py')
GO = os.path.join(norm, 'go')

ASSET_NAMES = {'sitemap.xml', 'feed.xml', 'llms.txt', 'llms-full.txt',
               'robots.txt', '_headers', '_redirects', 'rss.xml', 'atom.xml'}


def listing(base):
    found = {}
    for dirpath, _dirnames, filenames in os.walk(base):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            found[os.path.relpath(p, base)] = p
    return found


def category(rel):
    part = rel.split(os.sep, 1)[0]
    rest = rel.split(os.sep, 1)[1] if os.sep in rel else ''
    if part == 'gen':
        return 'gen pages'
    if part == 'root':
        return 'root files'
    if part == 'meta':
        if os.path.basename(rel) == 'manifest.json':
            return 'manifest'
        return 'check payload'
    base = os.path.basename(rel)
    if base.endswith('.html'):
        return 'HTML'
    if base in ASSET_NAMES:
        return 'sitemap/feed/llms/robots/headers/redirects'
    return 'other build output'


def read(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.readlines()


py_files, go_files = listing(PY), listing(GO)
allrel = sorted(set(py_files) | set(go_files))

counts, examples, only = {}, {}, {}
for rel in allrel:
    cat = category(rel)
    counts.setdefault(cat, 0)
    only.setdefault(cat, [])
    examples.setdefault(cat, [])
    if rel not in py_files:
        counts[cat] += 1
        only[cat].append('only in go: ' + rel)
        continue
    if rel not in go_files:
        counts[cat] += 1
        only[cat].append('only in py: ' + rel)
        continue
    a, b = read(py_files[rel]), read(go_files[rel])
    if a == b:
        continue
    counts[cat] += 1
    if len(examples[cat]) < 5:
        d = list(difflib.unified_diff(a, b, 'py/' + rel, 'go/' + rel, n=1))
        capped = d[:60]
        if len(d) > 60:
            capped.append('... (%d more diff lines)\n' % (len(d) - 60))
        examples[cat].append(''.join(x if x.endswith('\n') else x + '\n'
                                     for x in capped))

order = ['gen pages', 'root files', 'HTML',
         'sitemap/feed/llms/robots/headers/redirects',
         'other build output', 'manifest', 'check payload']
for cat in counts:
    if cat not in order:
        order.append(cat)

with open(report_path, 'a', encoding='utf-8') as rep:
    rep.write('## %s\n\n' % name)
    rep.write('| command | py exit | go exit |\n| --- | --- | --- |\n')
    rep.write('| gen | %s | %s |\n' % (py_gen, go_gen))
    rep.write('| build | %s | %s |\n' % (py_build, go_build))
    rep.write('| check | %s | %s |\n\n' % (py_check, go_check))
    rep.write('| category | differing files |\n| --- | --- |\n')
    total = 0
    for cat in order:
        n = counts.get(cat, 0)
        total += n
        rep.write('| %s | %d |\n' % (cat, n))
    rep.write('\n')
    for cat in order:
        if not counts.get(cat):
            continue
        rep.write('### %s -- %s\n\n' % (name, cat))
        for line in only.get(cat, [])[:5]:
            rep.write('- %s\n' % line)
        if only.get(cat):
            rep.write('\n')
        for ex in examples.get(cat, []):
            rep.write('```diff\n%s```\n\n' % ex)

with open(summary_path, 'a', encoding='utf-8') as sfh:
    sfh.write('\t'.join([name, py_gen, py_build, py_check, go_gen, go_build,
                         go_check] + ['%s=%d' % (c, counts.get(c, 0))
                                      for c in order]) + '\n')

print('  diffs: ' + ', '.join('%s=%d' % (c, counts.get(c, 0))
                              for c in order if counts.get(c)))
PYEOF
done

{
  echo "## Fleet summary"
  echo
  echo "| repo | py gen | py build | py check | go gen | go build | go check | differing files by category |"
  echo "| --- | --- | --- | --- | --- | --- | --- | --- |"
  while IFS=$'\t' read -r repo a b c d e f rest; do
    cats=$(printf '%s' "$rest" | tr '\t' ' ')
    echo "| $repo | $a | $b | $c | $d | $e | $f | $cats |"
  done < "$SUMMARY"
  echo
} >> "$REPORT"

ln -sfn "$RUN" "$ROOT/latest"
echo "report written to $REPORT (also $ROOT/latest/report.md)"
