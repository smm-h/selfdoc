"""The single authorized surface for effectful calls in selfdoc production code.

Every subprocess launch and every filesystem mutation made by ``selfdoc/``,
``selfblog/`` and ``selfdoc_core/`` goes through this module.  Nothing else in
the three packages may call ``subprocess.run``, ``subprocess.Popen``,
``open(path, "w")``, ``os.replace``, ``os.makedirs``, ``shutil.rmtree`` or
their siblings directly -- ``tests/test_effects_chokepoint.py`` enforces that
with an AST scan and a one-entry exemption list (this module, which holds the
primitives).

Why a chokepoint: selfdoc and selfblog ride strictcli's ``ctx.effects``
regime, where every mutation is declared, previewable under ``--dry-run``, and
recorded into the would-do log.  These CLIs force-push a ``gh-pages`` branch,
deploy to Cloudflare Pages, create GitHub repositories, set repository
secrets, write commits through the GitHub Git Data API and auto-commit to the
user's working tree -- a ``--dry-run`` that executed any of that would be
worse than no dry run at all.  With every effect funnelled through this one
module the regime is adapted in one file instead of at ~150 call sites.

The mode rule (declared, never inferred)
----------------------------------------

A command handler binds the dispatch context here (``@effects.handler``,
applied innermost on every selfdoc and selfblog command handler), and from
then on:

* **Preview mode** (``--dry-run``; ``ctx.dry_run`` is true) -- every mutating
  operation below is minted on ``ctx.effects``.  It is recorded, never
  executed, and returns strictcli's ``Unsettled`` carrier.  Forwarding that
  carrier into a later effect keeps the preview going; reading a field off it
  truncates the preview with the framework's own error, which is the honest
  outcome when nothing ran.
* **Live mode** -- the operations execute directly, with their full selfdoc
  semantics: per-call timeouts (the "external calls must have timeouts"
  convention), byte-vs-text captures, stdin payload streaming for ``gh api
  --input -``, ``atomic_write``'s temp-file + ``os.replace`` (the only way to
  rewrite the 0o444 generated root files), and the ``exist_ok`` /
  ``missing_ok`` distinctions call sites branch on.  The contract's closed
  method set expresses none of those, so routing a live run through it would
  silently drop a hang guard or a permission-preserving rename.

The split is by *mode*, decided before anything runs, and identical on every
invocation -- it is not a fallback: nothing here ever tries the handle, fails,
and retries elsewhere.

Reads are never effects
-----------------------

``read=True`` marks a subprocess run as a declared read.  A declared read
executes in **every** mode and is never minted, never recorded and never
logged -- the same treatment strictcli gives an allowlisted observe, and for
the same reason: a preview that could not look at the world would have nothing
to preview.  It is declared per call site rather than through an app-level
``proc_observe_allowlist`` because the argv cannot classify these: ``gh api``
is both ``GET /repos/.../contents`` and ``POST /repos/.../dispatches``, and
``git`` is both ``rev-parse`` and ``push --force``.  An allowlist prefix short
enough to cover the reads would be a blanket exemption over the writes --
exactly the breadth hazard strictcli's own ``observe-allowlist-breadth`` check
warns about.

Unbound calls -- the library path -- execute directly too.  ``selfdoc_core``
is a library: the build pipeline, the check helpers and the test suite call
these functions outside any command dispatch, and there is no handle to mint
on there.  ``tests/test_effects_binding.py`` asserts that every registered
command handler carries ``@effects.handler``, so a bound path is never missed
by accident.
"""

import functools
import io
import os
import shutil
import subprocess
import tempfile
from contextvars import ContextVar

import strictcli

# The dispatch context of the command currently running, or None outside a
# command dispatch (library callers, direct unit-test calls).
_CTX: ContextVar = ContextVar("selfdoc_effects_ctx", default=None)


def handler(fn):
    """Bind the dispatch context to this module for the length of a handler.

    Applied innermost on every selfdoc/selfblog command handler, under the
    ``@app.command(...)`` / ``@strictcli.flag(...)`` stack.  ``functools.wraps``
    keeps ``inspect.signature`` reporting the wrapped handler's real
    parameters, so strictcli's guard v2 still validates the declared flags and
    args against the signature it would have seen without the wrapper -- no
    ``forwarding=`` waiver is needed.
    """

    @functools.wraps(fn)
    def wrapper(ctx, *args, **kwargs):
        token = _CTX.set(ctx)
        try:
            return fn(ctx, *args, **kwargs)
        finally:
            _CTX.reset(token)

    wrapper.__selfdoc_effects_handler__ = True
    return wrapper


def unsettled(value):
    """True when *value* is a carrier standing in for a recorded mutation.

    The one thing a caller may do with a carrier besides forwarding it into a
    later effect: recognize it, and decline to read a result that does not
    exist.  Call sites that would otherwise reach for ``.returncode`` return
    the carrier itself instead, so a preview walks past a mutation whose
    output nobody needed and truncates (honestly) at the first caller that
    does need it.
    """
    return isinstance(value, strictcli.Unsettled)


def previewing():
    """True when the current dispatch is previewing rather than executing."""
    return _handle() is not None


def _handle():
    """The strictcli effects handle to mint on, or None to execute directly."""
    ctx = _CTX.get()
    if ctx is None or not getattr(ctx, "dry_run", False):
        return None
    return ctx.effects


def _p(path):
    """Render a path operand as text for the handle."""
    return os.fspath(path)


# ---------------------------------------------------------------------------
# Process effects
# ---------------------------------------------------------------------------


def run(
    argv,
    *,
    cwd=None,
    env=None,
    timeout=None,
    check=False,
    capture_output=False,
    text=False,
    input=None,
    read=False,
    resource=None,
    skip_if_current=None,
    grant=None,
):
    """Run a command and return the :class:`subprocess.CompletedProcess`.

    In preview mode a declared read (*read* true) still executes and returns a
    real ``CompletedProcess``; anything else is recorded on
    ``ctx.effects.run`` and returns the ``Unsettled`` carrier standing in for
    the run that did not happen.

    Args:
        argv: argument list.
        cwd: working directory for the child process.
        env: complete environment mapping for the child (None inherits).
        timeout: seconds before ``TimeoutExpired`` is raised.
        check: raise ``CalledProcessError`` on a non-zero exit.
        capture_output: capture stdout/stderr instead of inheriting them.
        text: decode captured streams as text.
        input: payload written to the child's stdin.
        read: declare this run an observation -- it changes nothing, so it
            executes in every mode and is never recorded.
        resource: opaque token naming what this run produces (preview only).
        skip_if_current: token the preview annotates the line with, spelling
            out that the handler skips this step when the resource is current.
        grant: name of a grant declared on the running command, whose reason
            is rendered beside the step in the preview.
    """
    h = _handle()
    if h is None or read:
        return _direct_run(
            argv,
            cwd=cwd,
            env=env,
            timeout=timeout,
            check=check,
            capture_output=capture_output,
            text=text,
            input=input,
        )

    listed = list(argv)
    result = h.run(
        listed,
        cwd=cwd,
        env=env,
        check=False,
        stream=not capture_output,
        resource=resource,
        skip_if_current=skip_if_current,
        grant=grant,
    )
    if isinstance(result, strictcli.Unsettled):
        # A recorded mutation: nothing ran, so there is no exit code to test.
        # Forwarding this into a later effect keeps the preview going; reading
        # a field off it truncates, which is the honest outcome.
        return result
    return _completed_from(result, listed, capture_output, text, check)


def pipeline(first_argv, second_argv, *, cwd=None, timeout=None):
    """Run ``first_argv | second_argv`` and return the second child's stderr.

    The contract's closed method set has no pipeline, so in preview mode the
    pair is recorded as the one ``/bin/sh -c`` invocation that performs it --
    a faithful rendering of the work, not an invented one.  Live mode keeps
    the real two-process ``Popen`` pipeline, which is what streams a
    ``git archive`` into ``tar`` without buffering the whole tree in memory.

    Returns ``(returncode, stderr_bytes)``, or the ``Unsettled`` carrier when
    the pipeline was recorded rather than run.
    """
    h = _handle()
    if h is not None:
        shell_form = " ".join(_shell_quote(a) for a in first_argv)
        shell_form += " | " + " ".join(_shell_quote(a) for a in second_argv)
        return h.run(["/bin/sh", "-c", shell_form], cwd=cwd, check=False,
                     stream=True)
    first = subprocess.Popen(
        list(first_argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=cwd,
    )
    second = subprocess.Popen(
        list(second_argv), stdin=first.stdout, stderr=subprocess.PIPE,
        cwd=cwd,
    )
    first.stdout.close()
    _, err = second.communicate(timeout=timeout)
    first.wait(timeout=timeout)
    return second.returncode, err


def _shell_quote(token):
    """Quote *token* for the rendered ``/bin/sh -c`` preview line."""
    if token and all(c.isalnum() or c in "-_./=:@^{}" for c in token):
        return token
    return "'" + token.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------------------
# Filesystem effects
# ---------------------------------------------------------------------------


class _RecordedWriter(io.StringIO):
    """A file-like sink that mints one ``write`` effect when it is closed.

    :func:`open_write` hands streaming writers (``json.dump``, loops of
    ``f.write``) a real file object in live mode.  The contract has no
    streaming write, so in preview mode the content accumulates here and the
    single resulting ``write`` carries the byte count the file would have had.
    """

    def __init__(self, handle, path, binary=False, append=False):
        super().__init__()
        self._handle = handle
        self._path = path
        self._binary = binary
        self._append = append

    def close(self):
        if self.closed:
            return
        content = self.getvalue()
        if self._append and os.path.exists(self._path):
            # The contract has no append: the recorded write carries the whole
            # resulting file, so the preview's byte count is the real one.
            mode, encoding = ("rb", None) if self._binary else ("r", "utf-8")
            with open(self._path, mode, encoding=encoding) as f:
                content = f.read() + content
        self._handle.write(self._path, content.encode() if self._binary else content)
        super().close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def open_write(path, mode="w", *, encoding=None, newline=None):
    """Open *path* for writing and return the file object.

    A thin ``open`` wrapper for streaming writers.  Use it as a context
    manager, exactly like ``open``.  Whole-content writers should prefer
    :func:`write_text` / :func:`atomic_write`.
    """
    if "w" not in mode and "a" not in mode and "x" not in mode:
        raise ValueError(f"open_write requires a write mode, got {mode!r}")
    h = _handle()
    if h is None:
        return open(path, mode, encoding=encoding, newline=newline)
    return _RecordedWriter(h, _p(path), binary="b" in mode, append="a" in mode)


def write_text(path, content, *, encoding="utf-8", newline=None):
    """Write *content* to *path*, truncating any existing file."""
    h = _handle()
    if h is None:
        with open(path, "w", encoding=encoding, newline=newline) as f:
            f.write(content)
        return
    h.write(_p(path), content)


def write_bytes(path, data):
    """Write *data* to *path*, truncating any existing file."""
    h = _handle()
    if h is None:
        with open(path, "wb") as f:
            f.write(data)
        return
    h.write(_p(path), data)


def atomic_write(filepath, content, permissions=None):
    """Write *content* to *filepath* atomically (temp file + ``os.replace``).

    A crash mid-write can never leave a truncated file: the content lands in a
    sibling temp file that is renamed over the target in one directory
    operation.  Because the rename is a directory operation it also succeeds
    when *filepath* itself is read-only (the 0o444 generated root files), with
    no unlock step -- which is why live mode keeps the temp-file dance instead
    of routing through the contract's plain ``write``.
    """
    h = _handle()
    if h is None:
        dir_name = os.path.dirname(filepath) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            if permissions is not None:
                os.chmod(tmp_path, permissions)
            os.replace(tmp_path, filepath)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return
    h.write(_p(filepath), content)
    if permissions is not None:
        h.chmod(_p(filepath), permissions)


def makedirs(path, *, exist_ok=False):
    """Create *path* and any missing parents.

    The default mirrors ``os.makedirs`` exactly (an existing *path* raises)
    so translating a call site never changes its behavior.
    """
    h = _handle()
    if h is None:
        os.makedirs(path, exist_ok=exist_ok)
        return
    h.mkdir(_p(path))


def remove(path, *, missing_ok=False):
    """Delete the file at *path*."""
    h = _handle()
    if h is None:
        if missing_ok and not os.path.lexists(path):
            return
        os.unlink(path)
        return
    h.remove(_p(path))


def rmdir(path):
    """Remove the empty directory at *path*."""
    h = _handle()
    if h is None:
        os.rmdir(path)
        return
    h.remove(_p(path))


def rmtree(path, *, ignore_errors=False):
    """Recursively delete the directory tree at *path*."""
    h = _handle()
    if h is None:
        shutil.rmtree(path, ignore_errors=ignore_errors)
        return
    h.remove(_p(path))


def chmod(path, mode):
    """Set the permission bits of *path*."""
    h = _handle()
    if h is None:
        os.chmod(path, mode)
        return
    h.chmod(_p(path), mode)


def copy_file(src, dst):
    """Copy *src* to *dst*, preserving metadata (``shutil.copy2``)."""
    h = _handle()
    if h is None:
        return shutil.copy2(src, dst)
    # The contract has no copy: reading the source is not an effect, writing
    # the destination is the one that gets recorded.
    with open(src, "rb") as f:
        h.write(_p(dst), f.read())
    return dst


def copytree(src, dst, *, dirs_exist_ok=False):
    """Recursively copy the directory tree *src* to *dst*."""
    h = _handle()
    if h is None:
        return shutil.copytree(src, dst, dirs_exist_ok=dirs_exist_ok)
    # One mkdir plus one write per file, so the preview names every path the
    # copy would create rather than a single opaque "copy tree" line.
    for dirpath, _dirnames, filenames in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        target_dir = dst if rel == "." else os.path.join(dst, rel)
        h.mkdir(target_dir)
        for name in filenames:
            with open(os.path.join(dirpath, name), "rb") as f:
                h.write(os.path.join(target_dir, name), f.read())
    return dst


# ---------------------------------------------------------------------------
# Live-mode primitives
# ---------------------------------------------------------------------------


def _direct_run(argv, *, cwd, env, timeout, check, capture_output, text, input):
    """Execute *argv* with the full subprocess semantics selfdoc relies on."""
    return subprocess.run(
        list(argv),
        cwd=cwd,
        env=env,
        timeout=timeout,
        check=check,
        capture_output=capture_output,
        text=text,
        input=input,
    )


def _completed_from(result, argv, capture_output, text, check):
    """Adapt a settled strictcli ``Completed`` to ``CompletedProcess``."""
    stdout, stderr = result.stdout, result.stderr
    if not capture_output:
        stdout = stderr = None
    elif not text:
        stdout, stderr = stdout.encode(), stderr.encode()
    if check and result.exit_code != 0:
        raise subprocess.CalledProcessError(result.exit_code, argv, stdout, stderr)
    return subprocess.CompletedProcess(argv, result.exit_code, stdout, stderr)
