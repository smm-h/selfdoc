"""Command classification and effects binding, pinned.

Three guarantees this file holds:

1. **Every command carries the classification it was deliberately given.**
   strictcli makes ``effect=`` mandatory, so a missing one is a registration
   error and can never reach here -- but a *wrong* one is silent. The table
   below is the reviewed judgement, and changing a row has to be a deliberate
   edit to this file. ``read_only`` means the command performs no user-visible
   or consequential mutation: it may read the filesystem and shell out to
   declared reads, and nothing else.

2. **Every command handler is bound to the effects chokepoint.** Without
   ``@effects.handler`` a handler's effects execute in every mode, including
   ``--dry-run`` -- silently, since nothing else would fail. The test walks
   the registered commands rather than the source, so a handler added later
   without the decorator fails here.

3. **Exactly three commands are ``consequential``.** The framework prompts for
   those and no others; ``mutating`` no longer implies a prompt. The set below
   is pinned in both directions, so adding a fourth is a deliberate edit to
   this file rather than a passing thought at a registration site.
"""

import os
import subprocess
import sys

import selfblog.cli
import selfdoc.cli


# Reviewed classification. The comment on each mutating row names the mutation.
SELFDOC_EFFECTS = {
    # writes selfdoc.json + docs/index.md, then auto-commits them
    "init": "mutating",
    # writes the whole site output tree and the content-hash store, then
    # auto-commits the store
    "build": "mutating",
    # --drafts rebuilds the site before serving, which writes the output tree
    "serve": "mutating",
    # wrangler deploy, or a force-push of the remote gh-pages branch
    "deploy": "mutating",
    # rewrites .selfdoc/hashes/hashes.json (the staleness baseline) and
    # auto-commits it -- an app-level cache write is an ordinary mutation
    "check": "mutating",
    # advances the stored staleness/drift baselines, then auto-commits
    "baseline.accept": "mutating",
    # writes generated doc pages and the 0o444 root files, deletes stale
    # generated pages, updates hashes + manifest, then auto-commits
    "gen": "mutating",
    # runs the configured scripts under bwrap and writes their data outputs
    "gen-data": "mutating",
    # reads the tree and prints metrics
    "quality": "read_only",
}

SELFBLOG_EFFECTS = {
    # writes the scaffolded post file
    "post.new": "mutating",
    # reads the posts directory and prints
    "post.list": "read_only",
    # writes the generated post and updates the manifest
    "post.generate": "mutating",
    # pushes built HTML to the assembly repo via the Git Data API and
    # dispatches a workflow that republishes the live site
    "post.publish": "mutating",
    # creates a GitHub repo, a Cloudflare Pages project, and repo secrets
    "assembly.init": "mutating",
    # repository_dispatch against the assembly repo
    "assembly.push": "mutating",
    # queries workflow runs and prints them
    "assembly.status": "read_only",
    # repository_dispatch for every registered project
    "assembly.rebuild": "mutating",
    # prints the _redirects content to stdout
    "assembly.redirects": "read_only",
    # writes the assembled site's shared files
    "assembly.generate-shared": "mutating",
    # rewrites the content-hash store and auto-commits it
    "check": "mutating",
    # writes the built output tree and auto-commits the hash store
    "build": "mutating",
}


# The reviewed consequential set. A command belongs here when its effects are
# worth interrupting someone for -- not merely because they mutate. The line
# drawn across these two CLIs: an effect qualifies when it is destructive on a
# remote, creates a named external resource that rerunning cannot un-create, or
# makes something public that was not public before. Re-deriving already-public
# content from an already-public source does not qualify, which is why
# `assembly push` and `assembly rebuild` are absent despite carrying escaping
# PROC_MUTATE grants.
SELFDOC_CONSEQUENTIAL = {
    # Cloudflare Pages goes live on landing; the GitHub Pages provider
    # force-pushes gh-pages, so the previous published tree is gone from the
    # remote. Neither is undone by rerunning.
    "deploy",
}

SELFBLOG_CONSEQUENTIAL = {
    # Locally-authored, previously-private posts become publicly readable.
    "post.publish",
    # Creates a GitHub repository, claims a *.pages.dev subdomain, and writes
    # deployment credentials into repo secrets -- three named external
    # resources, none of them un-created by a rerun.
    "assembly.init",
}


def _walk(app):
    """Map dotted command path -> Command for every registered command."""
    found = {}

    def visit(container, prefix):
        registry = getattr(container, "_commands", None) or container.commands
        for name, cmd in registry.items():
            found[prefix + name] = cmd
        for name, group in container._groups.items():
            visit(group, prefix + name + ".")

    visit(app, "")
    return found


def test_selfdoc_classification_table():
    """Every selfdoc command carries its reviewed classification."""
    commands = _walk(selfdoc.cli.app)
    for path, effect in SELFDOC_EFFECTS.items():
        assert path in commands, f"selfdoc command '{path}' is gone"
        assert commands[path].effect == effect, (
            f"selfdoc '{path}' is classified {commands[path].effect!r}, "
            f"the reviewed table says {effect!r}"
        )


def test_selfblog_classification_table():
    """Every selfblog command carries its reviewed classification."""
    commands = _walk(selfblog.cli.app)
    for path, effect in SELFBLOG_EFFECTS.items():
        assert path in commands, f"selfblog command '{path}' is gone"
        assert commands[path].effect == effect, (
            f"selfblog '{path}' is classified {commands[path].effect!r}, "
            f"the reviewed table says {effect!r}"
        )


def test_no_selfdoc_command_escapes_the_table():
    """A new selfdoc command must be classified in the table above."""
    registered = set(_walk(selfdoc.cli.app))
    unreviewed = registered - set(SELFDOC_EFFECTS)
    assert not unreviewed, (
        f"unreviewed selfdoc commands: {sorted(unreviewed)} -- add each to "
        "SELFDOC_EFFECTS with the mutation it performs, or read_only"
    )


def test_no_selfblog_command_escapes_the_table():
    """A new selfblog command must be classified in the table above."""
    registered = set(_walk(selfblog.cli.app))
    unreviewed = registered - set(SELFBLOG_EFFECTS)
    assert not unreviewed, (
        f"unreviewed selfblog commands: {sorted(unreviewed)} -- add each to "
        "SELFBLOG_EFFECTS with the mutation it performs, or read_only"
    )


def test_every_handler_is_bound_to_the_chokepoint():
    """Every command handler carries @effects.handler.

    An unbound handler's effects execute in every mode -- including under
    ``--dry-run``, where nothing is supposed to run and nothing would fail to
    signal it.
    """
    unbound = []
    for app, label in ((selfdoc.cli.app, "selfdoc"), (selfblog.cli.app, "selfblog")):
        for path, cmd in _walk(app).items():
            if not getattr(cmd.handler, "__selfdoc_effects_handler__", False):
                unbound.append(f"{label} {path}")
    assert not unbound, (
        f"command handlers missing @effects.handler: {sorted(unbound)}"
    )


def test_reserved_quartet_is_not_redeclared():
    """No command redeclares a framework-reserved flag name.

    The quartet is dry-run/approve-consequential/quiet/verbose, and ``yes``
    stays separately banned even though it no longer owns a framework flag --
    a private ``--yes`` would restate ``--approve-consequential`` in the very
    spelling the rename removed. All five are registration errors at every
    level; this pins that selfdoc's three former ``--dry-run`` flags stay gone
    rather than reappearing under a near-miss spelling.
    """
    reserved = {"dry-run", "approve-consequential", "yes", "quiet", "verbose"}
    for app, label in ((selfdoc.cli.app, "selfdoc"), (selfblog.cli.app, "selfblog")):
        for path, cmd in _walk(app).items():
            names = {f.name for f in cmd.flags}
            assert not (names & reserved), (
                f"{label} '{path}' declares reserved flag(s) "
                f"{sorted(names & reserved)}"
            )


def test_consequential_set_is_exactly_the_reviewed_one():
    """Exactly the reviewed commands declare ``consequential``.

    Pinned in both directions. A command that gains the declaration without
    being added here fails, and so does one that quietly loses it -- the second
    direction matters more, because losing it removes a gate silently while the
    command keeps working.
    """
    for app, label, expected in (
        (selfdoc.cli.app, "selfdoc", SELFDOC_CONSEQUENTIAL),
        (selfblog.cli.app, "selfblog", SELFBLOG_CONSEQUENTIAL),
    ):
        actual = {
            path
            for path, cmd in _walk(app).items()
            if getattr(cmd, "consequential", False)
        }
        assert actual == expected, (
            f"{label} consequential set is {sorted(actual)}, the reviewed set "
            f"is {sorted(expected)} -- justify the change in this file's "
            "docstring before editing the set"
        )


def test_mutating_but_not_consequential_commands_do_not_prompt():
    """The routine mutating commands carry no confirm gate.

    This is the whole point of the redesign: 63% of the fleet classified
    ``mutating``, and prompting for all of them made the gate noise. ``gen``,
    ``check`` and ``build`` are invoked bare by release pipelines with no TTY,
    so a gate on any of them is a hard breakage, not an inconvenience.
    """
    for app, label, names in (
        (selfdoc.cli.app, "selfdoc", ["gen", "check", "build", "baseline.accept"]),
        (selfblog.cli.app, "selfblog", ["post.new", "assembly.push", "check", "build"]),
    ):
        commands = _walk(app)
        for name in names:
            assert not getattr(commands[name], "consequential", False), (
                f"{label} '{name}' became consequential; release pipelines "
                "invoke it with no TTY and would hard-error"
            )


def _run_cli(module, argv, cwd):
    """Run a CLI module as a real subprocess with a non-TTY stdin."""
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    with open(os.devnull, "rb") as devnull:
        return subprocess.run(
            [sys.executable, "-m", module, *argv],
            cwd=str(cwd),
            stdin=devnull,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )


def test_consequential_command_refuses_on_non_interactive_stdin(tmp_path):
    """``selfdoc deploy`` hard-errors before its handler when stdin is not a TTY.

    Pins the framework's message verbatim: a rename there is exactly the class
    of upstream change that broke auto-commit, and the failure would otherwise
    surface only in a release. The command is safe to run here because the gate
    fires *before* dispatch -- no deploy is attempted.
    """
    result = _run_cli("selfdoc", ["deploy"], tmp_path)

    assert result.returncode == 1
    assert (
        "error: stdin is not interactive; pass --approve-consequential to confirm"
        in result.stderr
    )


def test_non_consequential_command_runs_without_a_confirmation_flag(tmp_path):
    """``selfdoc check`` reaches its handler with no TTY and no flag.

    The counterpart to the test above: it fails on its own terms (no
    selfdoc.json in an empty directory) rather than at a confirm gate, which is
    what proves no gate is there.
    """
    result = _run_cli("selfdoc", ["check"], tmp_path)

    assert "stdin is not interactive" not in result.stderr
    assert "--approve-consequential" not in result.stderr
