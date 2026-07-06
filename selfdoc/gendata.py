"""Generate data files by running sandboxed scripts via bubblewrap (bwrap).

Re-export shim: actual implementation in selfdoc_core.gendata.
"""

from selfdoc_core.gendata import *  # noqa: F401,F403
from selfdoc_core.gendata import (  # noqa: F401
    _build_bwrap_command,
    _check_bwrap,
    _validate_output,
    _validate_script,
)
