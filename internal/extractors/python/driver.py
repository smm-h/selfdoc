"""Read one Python file's syntax tree and print what the extractor needs.

selfdoc's Python reference pages are built from the stdlib ``ast`` module, and
nothing else reproduces it: ``ast.unparse`` renders an annotation, a default
value and a base class exactly as the pages have always shown them, and the
tree's own child order is the order the pages list symbols in.  So the Go
extractor keeps asking Python, through this driver.

The split is deliberate.  This program reads the tree and renders the pieces
that come out of ``ast`` -- docstrings, signatures, unparsed types and
defaults, ``__all__``, re-export statements, line spans, and the two syntactic
predicates (dataclass, pydantic model).  Everything else -- which symbols are
skipped, how the Markdown is assembled, how docstring sections are formatted,
which parameters count as documented -- is the Go side's, because that is the
part a reader sees.

Invoked as ``python3 -c <this program> <display_path>`` with the source on
standard input, it writes one JSON document to standard output.
"""

import ast
import json
import sys

_SKIP_NAMES = {"self", "cls"}


def annotation_str(node):
    """Render an annotation node, or the empty string when there is none."""
    if node is None:
        return ""
    return ast.unparse(node)


def build_signature(node):
    """Build the parenthesized signature the reference pages print."""
    args = node.args
    parts = []

    posonlyargs = getattr(args, "posonlyargs", [])
    all_positional = posonlyargs + args.args

    num_defaults = len(args.defaults)
    num_positional = len(all_positional)

    for i, arg in enumerate(all_positional):
        name = arg.arg
        annotation = annotation_str(arg.annotation)
        part = f"{name}: {annotation}" if annotation else name

        default_idx = i - (num_positional - num_defaults)
        if default_idx >= 0:
            part += f"={ast.unparse(args.defaults[default_idx])}"

        parts.append(part)

    if posonlyargs:
        parts.insert(len(posonlyargs), "/")

    if args.vararg:
        annotation = annotation_str(args.vararg.annotation)
        if annotation:
            parts.append(f"*{args.vararg.arg}: {annotation}")
        else:
            parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")

    for i, arg in enumerate(args.kwonlyargs):
        name = arg.arg
        annotation = annotation_str(arg.annotation)
        part = f"{name}: {annotation}" if annotation else name

        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            part += f"={ast.unparse(args.kw_defaults[i])}"

        parts.append(part)

    if args.kwarg:
        annotation = annotation_str(args.kwarg.annotation)
        if annotation:
            parts.append(f"**{args.kwarg.arg}: {annotation}")
        else:
            parts.append(f"**{args.kwarg.arg}")

    ret = annotation_str(node.returns)
    sig = f"({', '.join(parts)})"
    if ret:
        sig += f" -> {ret}"
    return sig


def class_signature(node):
    """Build a ``class Name(Base1, Base2):`` signature line."""
    bases = [ast.unparse(b) for b in node.bases]
    keywords = []
    for kw in node.keywords:
        value = ast.unparse(kw.value)
        keywords.append(f"{kw.arg}={value}" if kw.arg else f"**{value}")
    bases_str = ", ".join(bases + keywords)
    if bases_str:
        return f"class {node.name}({bases_str}):"
    return f"class {node.name}:"


def is_dataclass(node):
    """Whether a class node carries a ``@dataclass`` decorator."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "dataclass":
            return True
        if isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Name) and func.id == "dataclass":
                return True
            if (isinstance(func, ast.Attribute)
                    and func.attr == "dataclass"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "dataclasses"):
                return True
    return False


def is_pydantic_model(node):
    """Whether a class node looks like a pydantic ``BaseModel`` subclass.

    A base-class name check covers ``pydantic.BaseModel``, aliased imports and
    plain ``BaseModel``.  A nested ``class Config:`` or a ``model_config = ...``
    assignment is the secondary signal, which config-bearing models carry even
    when the base class is the project's own intermediate base.  This is a
    single-hop syntactic check, not a resolved method resolution order.
    """
    for base in node.bases:
        base_name = None
        if isinstance(base, ast.Name):
            base_name = base.id
        elif isinstance(base, ast.Attribute):
            base_name = base.attr
        if base_name == "BaseModel":
            return True

    for item in ast.iter_child_nodes(node):
        if isinstance(item, ast.ClassDef) and item.name == "Config":
            return True
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id == "model_config":
                    return True
    return False


def details_params(node):
    """The parameters a symbol-details report names, in declaration order.

    ``self`` and ``cls`` are dropped from the positional groups only, and the
    variadic and keyword parameters carry the prefix the signature writes.
    """
    args = node.args
    entries = []

    posonlyargs = getattr(args, "posonlyargs", [])
    for arg in posonlyargs + args.args:
        if arg.arg not in _SKIP_NAMES:
            entries.append(("", arg))
    if args.vararg:
        entries.append(("*", args.vararg))
    for arg in args.kwonlyargs:
        entries.append(("", arg))
    if args.kwarg:
        entries.append(("**", args.kwarg))

    params = []
    for prefix, arg in entries:
        annotation = annotation_str(arg.annotation)
        params.append({
            "name": prefix + arg.arg,
            "type": annotation or None,
        })
    return params


def annotated_fields(node):
    """The annotated assignments a class declares, with their line numbers."""
    fields = []
    for child in ast.iter_child_nodes(node):
        if not isinstance(child, ast.AnnAssign):
            continue
        if not isinstance(child.target, ast.Name):
            continue
        fields.append({
            "name": child.target.id,
            "type": ast.unparse(child.annotation) if child.annotation else "",
            "default": ast.unparse(child.value) if child.value else "",
            "lineno": child.lineno,
        })
    return fields


def declaration(node):
    """Render one function or class declaration, or None for anything else."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return {
            "kind": "function",
            "name": node.name,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "doc": ast.get_docstring(node),
            "signature": build_signature(node),
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "params": details_params(node),
            "return_type": annotation_str(node.returns) or None,
        }
    if isinstance(node, ast.ClassDef):
        members = []
        for item in ast.iter_child_nodes(node):
            member = declaration(item)
            if member is not None:
                members.append(member)
        return {
            "kind": "class",
            "name": node.name,
            "is_async": False,
            "doc": ast.get_docstring(node),
            "class_signature": class_signature(node),
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "is_dataclass": is_dataclass(node),
            "is_pydantic": is_pydantic_model(node),
            "fields": annotated_fields(node),
            "members": members,
        }
    return None


def all_literal_names(tree):
    """The module's ``__all__`` contents when it is a literal list or tuple of
    string constants, else None.

    None covers both "no ``__all__``" and "``__all__`` defined but not a
    literal list of strings"; the caller falls back to a heuristic either way.
    """
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    names = []
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            names.append(elt.value)
                        else:
                            return None
                    return names
    return None


def importfrom_stub(node, alias):
    """Reconstruct the ``from X import Y [as Z]`` line for one alias."""
    dots = "." * node.level
    module = node.module or ""
    imported = alias.name if not alias.asname else f"{alias.name} as {alias.asname}"
    return f"from {dots}{module} import {imported}"


def iter_reexport_candidates(tree):
    """Module-level ``ImportFrom``/``Assign``/``AnnAssign`` statements.

    Statements nested one level inside top-level ``Try``/``If`` bodies are
    included -- that covers the ``try: from ._impl import X except ImportError:``
    fallback and ``if TYPE_CHECKING:`` guards.  Deeper nesting is not descended
    into.
    """
    for stmt in tree.body:
        if isinstance(stmt, (ast.ImportFrom, ast.Assign, ast.AnnAssign)):
            yield stmt
        elif isinstance(stmt, ast.Try):
            nested = list(stmt.body)
            for handler in stmt.handlers:
                nested.extend(handler.body)
            nested.extend(stmt.orelse)
            nested.extend(stmt.finalbody)
            for sub in nested:
                if isinstance(sub, (ast.ImportFrom, ast.Assign, ast.AnnAssign)):
                    yield sub
        elif isinstance(stmt, ast.If):
            for sub in (*stmt.body, *stmt.orelse):
                if isinstance(sub, (ast.ImportFrom, ast.Assign, ast.AnnAssign)):
                    yield sub


def reexport_stubs(tree):
    """``(name, source line)`` pairs for module-level re-exports and constants.

    Star imports are skipped: they are unresolvable, and their names would not
    appear in a literal ``__all__`` extraction anyway.
    """
    stubs = []
    for stmt in iter_reexport_candidates(tree):
        if isinstance(stmt, ast.ImportFrom):
            for alias in stmt.names:
                if alias.name == "*":
                    continue
                stubs.append({
                    "name": alias.asname or alias.name,
                    "stub": importfrom_stub(stmt, alias),
                })
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    stubs.append({"name": target.id, "stub": ast.unparse(stmt)})
    return stubs


def cli_constants(tree):
    """Module-level ``HELP``/``USAGE`` string constants, in source order."""
    constants = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or target.id not in ("HELP", "USAGE"):
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                constants.append({"name": target.id, "value": node.value.value})
    return constants


def main():
    display_path = sys.argv[1] if len(sys.argv) > 1 else "<stdin>"
    source = sys.stdin.read()

    try:
        tree = ast.parse(source, filename=display_path)
    except SyntaxError as exc:
        json.dump({"syntax_error": str(exc)}, sys.stdout)
        return

    declarations = []
    for node in ast.iter_child_nodes(tree):
        decl = declaration(node)
        if decl is not None:
            declarations.append(decl)

    json.dump(
        {
            "syntax_error": None,
            "docstring": ast.get_docstring(tree),
            "all_names": all_literal_names(tree),
            "declarations": declarations,
            "reexports": reexport_stubs(tree),
            "cli_constants": cli_constants(tree),
        },
        sys.stdout,
    )


main()
