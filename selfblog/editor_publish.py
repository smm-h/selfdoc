"""The editor's publish surface: the descriptor, the plan, and the consent path.

Publishing is the moment locally-authored posts become publicly readable,
and it cannot be undone from the reader's side.  ``selfblog post publish``
already says so in the only place that decision belongs -- its strictcli
declaration, where it is ``effect="mutating"`` and ``consequential=True``
with a named grant for the workflow it dispatches.

So the editor does not restate any of that.  It **reads** the declaration
(:func:`publish_descriptor`, straight out of ``App.dump_schema_dict``),
renders a consent dialog from it, and, on confirm, calls the command
through strictcli's programmatic path carrying the consent the human just
gave.  Three properties follow, and each is asserted by the suite:

* the dialog cannot drift from the command -- a classification changed in
  ``cli.py`` changes what the dialog says, with nothing to update here;
* a call without consent is refused by the framework, not by a check
  written here that could be forgotten or bypassed;
* the refusal and the result both reach the author verbatim.

Two things the surface must be honest about, because the command is:

* **The scope is the repository, not the open post.**  ``post publish``
  builds and pushes every non-draft post the project declares.  Saying
  "publish this post" would be a lie about what the button does, so the
  descriptor carries :data:`SCOPE_NOTE` and the plan carries the actual
  list, computed here rather than guessed at in the browser.
* **Consent is per publish.**  Nothing is remembered: there is no
  don't-ask-again, no stored answer, and no session in which the question
  has already been asked.  A second publish asks a second time.
"""

from __future__ import annotations

import contextlib
import io
import os
import threading

from selfblog.editor_server import EditorError, repo_config, require_local

#: The command the surface drives, as strictcli addresses it.
PUBLISH_COMMAND = "post.publish"

#: What the publish reaches, stated the way the surface has to state it.
SCOPE = "repository"

#: Rendered verbatim by the consent dialog.  The command publishes a
#: project, not a document, and a surface that implied otherwise would be
#: describing something the button does not do.
SCOPE_NOTE = (
    "This publishes every non-draft post in this repository -- not just the "
    "post open in the editor. Published posts become publicly readable and "
    "cannot be unpublished from the reader's side."
)

#: One publish at a time, and nothing else in the process meanwhile.  The
#: command reads the project out of the current working directory and
#: prints to the process's own streams, so running it means changing both
#: for the duration.  The editor is single-user and local, so serialising
#: publishes costs nothing; doing it without the lock would let a concurrent
#: request see the wrong working directory.
_PUBLISH_LOCK = threading.Lock()


class PublishRefused(EditorError):
    """strictcli refused the call.  The message is the framework's, verbatim."""

    status = 403


class PublishFailed(EditorError):
    """The publish ran and did not succeed.  Its own output says why."""

    status = 500


def _app():
    """The selfblog CLI application object.

    Imported here rather than at module scope: the CLI imports the editor
    on its way to serving it, so the dependency only closes at call time.
    """
    from selfblog.cli import app

    return app


def _command_schema():
    """The publish command's entry in strictcli's own schema dump."""
    group, _, name = PUBLISH_COMMAND.partition(".")
    schema = _app().dump_schema_dict()
    try:
        return schema["groups"][group]["commands"][name]
    except KeyError:
        raise EditorError(
            f"the selfblog CLI declares no command {PUBLISH_COMMAND!r}; the "
            f"editor's publish surface is bound to a command that no longer "
            f"exists"
        ) from None


def publish_descriptor():
    """The publish command's declaration, as the dialog renders it.

    Every classification field comes from strictcli's schema for the
    command -- ``effect``, ``consequential`` and the grants it declares --
    so this is a projection of the declaration, never a copy of it.
    """
    declared = _command_schema()
    return {
        "command": PUBLISH_COMMAND,
        "effect": declared["effect"],
        # Absent means "not consequential" in the schema, so the default is
        # read the same way strictcli writes it.
        "consequential": bool(declared.get("consequential", False)),
        "help": declared["help"],
        "grants": [dict(grant) for grant in declared.get("grants") or []],
        "scope": SCOPE,
        "scope_note": SCOPE_NOTE,
        "consent_parameter": "approve_consequential",
    }


def publish_plan(entry):
    """What a publish of *entry* would make public, computed here.

    The browser is told the list rather than asked to derive it: which
    posts publish is the project's answer, read off the same discovery the
    publish itself runs.
    """
    from selfblog.editor_server import repo_posts

    require_local(entry)
    config = repo_config(entry)
    posts = repo_posts(entry)
    assembly = (config.get("assembly") or {}).get("repo", "")
    slug = (config.get("topology") or {}).get("slug", "")

    return {
        "repo": entry.name,
        "path": entry.path,
        "project": slug,
        "assembly": assembly,
        "publishing": [post for post in posts if not post["draft"]],
        "withheld": [post for post in posts if post["draft"]],
    }


def run_publish(entry, approve_consequential):
    """Invoke the publish for *entry* through strictcli's consent path.

    Args:
        entry: The local registry entry to publish.
        approve_consequential: The consent the human gave, passed straight
            to strictcli.  False (or absent) is not handled here at all --
            the framework refuses the call, which is the point: the
            refusal comes from the consent regime, not from a condition
            this module could forget to write.

    Returns:
        ``{"ok": True, "exit_code": 0, "stdout": ..., "stderr": ...}``.

    Raises:
        PublishRefused: strictcli refused, message verbatim.
        PublishFailed: the command ran and exited non-zero, with whatever
            it printed.
    """
    import strictcli

    require_local(entry)
    app = _app()

    out = io.StringIO()
    err = io.StringIO()
    exit_code = 0

    with _PUBLISH_LOCK:
        previous_cwd = os.getcwd()
        try:
            os.chdir(entry.path)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    app.call(
                        PUBLISH_COMMAND,
                        approve_consequential=bool(approve_consequential),
                    )
                except SystemExit as exc:
                    code = exc.code
                    exit_code = code if isinstance(code, int) else (1 if code else 0)
        except strictcli.InvokeError as exc:
            raise PublishRefused(str(exc)) from None
        finally:
            os.chdir(previous_cwd)

    result = {
        "repo": entry.name,
        "command": PUBLISH_COMMAND,
        "exit_code": exit_code,
        "stdout": out.getvalue(),
        "stderr": err.getvalue(),
        "ok": exit_code == 0,
    }
    if exit_code != 0:
        raise PublishFailed(
            (err.getvalue() or out.getvalue() or "").strip()
            or f"{PUBLISH_COMMAND} exited {exit_code} without saying why"
        )
    return result
