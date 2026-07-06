"""Generate shared elements for multi-project documentation assembly including homepage, blog index, nav JSON, RSS feed, and sitemap.

Re-export shim: actual implementation in selfblog.shared.
"""

from selfblog.shared import *  # noqa: F401,F403
from selfblog.shared import _page_path_to_url_segment  # noqa: F401
