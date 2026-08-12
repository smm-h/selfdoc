"""Resolve the ``projects-cards`` site-level directive during a home build."""

from selfblog.sitedirectives import resolve_for_build


def resolve(attrs, config, body):
    return resolve_for_build("projects-cards", attrs, config)
