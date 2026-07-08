# selfdoc-core

Shared engine for code-aware documentation generation. Provides the build
pipeline, directive parser, language extractors (Python, Go, TypeScript,
and more), theming, and site output machinery used by
[selfdoc](https://pypi.org/project/selfdoc/) and
[selfblog](https://pypi.org/project/selfblog/).

Most users should install `selfdoc` (the CLI) instead of this package
directly -- `selfdoc-core` is a library dependency with no command-line
interface of its own.

```bash
pip install selfdoc
```

Documentation: https://selfdoc.smmh.dev

Source: https://github.com/smm-h/selfdoc
