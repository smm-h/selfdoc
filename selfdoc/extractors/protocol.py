"""Language extractor protocol -- defines the interface all extractors must implement.

Extractors are runtime-checkable so the registry can validate them.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LanguageExtractor(Protocol):
    @property
    def name(self) -> str: ...

    def detect(self, dir_path: str) -> bool: ...

    def resolve_path(
        self, path_arg: str, source_paths: list[str], base_dir: str
    ) -> str | None: ...

    def extract(
        self,
        directive_name: str,
        attrs: dict[str, str],
        body: list[str],
        source_paths: list[str],
        base_dir: str,
    ) -> str: ...

    def file_extensions(self) -> list[str]: ...

    def public_symbols(self, file_path: str) -> list[str]: ...
