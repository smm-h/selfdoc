"""Render data as Markdown tables with alignment, pretty-printing, and pipe escaping."""


def _escape_pipes(text):
    """Escape pipe characters in text, preserving pipes inside backtick spans.

    If a backtick opens a span but never closes, pipes after the unclosed
    backtick are escaped as if the span never opened.
    """
    result = []
    in_backtick = False
    backtick_start = None
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "`":
            if not in_backtick:
                in_backtick = True
                backtick_start = len(result)
            else:
                in_backtick = False
                backtick_start = None
            result.append(ch)
        elif ch == "|" and not in_backtick:
            result.append("\\|")
        else:
            result.append(ch)
        i += 1

    if in_backtick:
        # Unclosed backtick: re-scan from the backtick position and escape pipes
        tail = result[backtick_start:]
        escaped_tail = []
        for ch in tail:
            if ch == "|":
                escaped_tail.append("\\|")
            else:
                escaped_tail.append(ch)
        result[backtick_start:] = escaped_tail

    return "".join(result)


def render_markdown_table(headers, rows, *, align=None, pretty=False):
    """Render a Markdown table from headers and rows.

    Parameters:
        headers: Column header labels.
        rows: Each inner list is one row of cell values.
        align: Per-column alignment ("left", "center", "right"), or None.
        pretty: If True, pad cells for visual alignment.

    Returns:
        Complete markdown table string.

    Raises:
        ValueError: If a cell contains a newline, or a row has more cells
            than headers, or align contains an invalid value.
    """
    if not headers:
        raise ValueError("headers must not be empty")

    num_cols = len(headers)

    # Validate align
    if align is not None:
        valid_alignments = {"left", "center", "right"}
        for a in align:
            if a not in valid_alignments:
                raise ValueError(
                    f"invalid alignment {a!r}, must be one of: left, center, right"
                )

    # Validate and normalize rows
    processed_rows = []
    for row_idx, row in enumerate(rows):
        if len(row) > num_cols:
            raise ValueError(
                f"row {row_idx} has {len(row)} cells, but only {num_cols} headers"
            )
        # Check for newlines and escape pipes
        normalized = []
        for cell in row:
            cell = str(cell)
            if "\n" in cell:
                raise ValueError("cell values must not contain newline characters")
            normalized.append(_escape_pipes(cell))
        # Pad short rows
        while len(normalized) < num_cols:
            normalized.append("")
        processed_rows.append(normalized)

    # Escape pipes in headers too
    escaped_headers = []
    for h in headers:
        if "\n" in h:
            raise ValueError("cell values must not contain newline characters")
        escaped_headers.append(_escape_pipes(h))

    # Build separator cells
    def _sep_cell(col_idx):
        base = "---"
        if align is not None and col_idx < len(align):
            a = align[col_idx]
            if a == "left":
                return ":---"
            elif a == "center":
                return ":---:"
            elif a == "right":
                return "---:"
        return base

    sep_cells = [_sep_cell(i) for i in range(num_cols)]

    if pretty:
        # Compute column widths: max of header, separator, and all row cells
        col_widths = []
        for col in range(num_cols):
            w = len(escaped_headers[col])
            w = max(w, len(sep_cells[col]))
            for row in processed_rows:
                w = max(w, len(row[col]))
            col_widths.append(w)

        def _pad(text, col):
            return text.ljust(col_widths[col])

        def _pad_sep(text, col):
            # Extend dashes to fill width, preserving colon markers
            width = col_widths[col]
            if text.startswith(":") and text.endswith(":"):
                return ":" + "-" * (width - 2) + ":"
            elif text.startswith(":"):
                return ":" + "-" * (width - 1)
            elif text.endswith(":"):
                return "-" * (width - 1) + ":"
            else:
                return "-" * width

        header_line = "| " + " | ".join(_pad(escaped_headers[c], c) for c in range(num_cols)) + " |"
        sep_line = "| " + " | ".join(_pad_sep(sep_cells[c], c) for c in range(num_cols)) + " |"
        data_lines = []
        for row in processed_rows:
            data_lines.append("| " + " | ".join(_pad(row[c], c) for c in range(num_cols)) + " |")
    else:
        header_line = "| " + " | ".join(escaped_headers) + " |"
        sep_line = "| " + " | ".join(sep_cells) + " |"
        data_lines = []
        for row in processed_rows:
            data_lines.append("| " + " | ".join(row) + " |")

    lines = [header_line, sep_line] + data_lines
    return "\n".join(lines)
