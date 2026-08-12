"""Resolve the ``blog-highlights`` site-level directive during a home build."""

from selfblog.sitedirectives import resolve_for_build


def resolve(attrs, config, body):
    return resolve_for_build("blog-highlights", attrs, config)
