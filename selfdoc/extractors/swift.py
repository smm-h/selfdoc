"""Swift source extractor for selfdoc -- parses .swift files to extract public declarations, doc comments, and struct schemas for documentation."""

from selfdoc_core.extractors.swift import *  # noqa: F401,F403
from selfdoc_core.extractors.swift import _parse_swift_doc_comment  # noqa: F401
