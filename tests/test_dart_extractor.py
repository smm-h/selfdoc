"""Tests for the Dart source extractor (selfdoc.extractors.dart)."""

import os

import pytest

from selfdoc.extractors.dart import DartExtractor


@pytest.fixture()
def dart_project(tmp_path):
    """Create a sample Dart project structure for testing."""
    lib_dir = os.path.join(tmp_path, "lib")
    src_dir = os.path.join(lib_dir, "src")
    os.makedirs(src_dir)

    # pubspec.yaml
    pubspec = os.path.join(tmp_path, "pubspec.yaml")
    with open(pubspec, "w", encoding="utf-8") as f:
        f.write("name: my_package\nversion: 1.0.0\n")

    # Main library file with various declarations
    main_dart = os.path.join(lib_dir, "my_package.dart")
    with open(main_dart, "w", encoding="utf-8") as f:
        f.write("""\
/// The main library for my_package.
library my_package;

abstract class Animal {
  String get name;
  void speak();
}

class Dog extends Animal {
  @override
  String get name => 'Dog';
  @override
  void speak() => print('Woof!');
}

sealed class Shape {}
class Circle extends Shape {}

base class Base {}
interface class Interface {}
final class Final {}
mixin class MixinClass {}
abstract base class AbstractBase {}
abstract interface class AbstractInterface {}
abstract mixin class AbstractMixin {}
base mixin class BaseMixinClass {}

mixin Serializable {
  Map<String, dynamic> toJson();
}

base mixin BaseMixin {}

enum Color { red, green, blue }

extension type Meters(double value) {}

typedef StringCallback = void Function(String);

void greet(String name) {
  print('Hello, \\$name');
}

Future<List<int>> fetchNumbers() async {
  return [1, 2, 3];
}

const maxRetries = 3;
final defaultName = 'World';
var counter = 0;

String _privateHelper() => '';
int _privateVar = 0;
class _PrivateClass {}
""")

    # Generated file that should be skipped
    gen_dart = os.path.join(lib_dir, "my_package.g.dart")
    with open(gen_dart, "w", encoding="utf-8") as f:
        f.write("""\
// GENERATED CODE - DO NOT MODIFY BY HAND
class GeneratedClass {}
""")

    # Freezed generated file
    freezed_dart = os.path.join(lib_dir, "my_package.freezed.dart")
    with open(freezed_dart, "w", encoding="utf-8") as f:
        f.write("""\
// GENERATED CODE - DO NOT MODIFY BY HAND
class FreezedClass {}
""")

    return tmp_path


class TestDetection:
    def test_dart_detection(self, dart_project):
        ext = DartExtractor()
        assert ext.detect(str(dart_project)) is True

    def test_dart_no_detection(self, tmp_path):
        ext = DartExtractor()
        assert ext.detect(str(tmp_path)) is False

    def test_file_extensions(self):
        ext = DartExtractor()
        assert ext.file_extensions() == [".dart"]

    def test_name(self):
        ext = DartExtractor()
        assert ext.name == "dart"


class TestPublicSymbols:
    def test_extracts_classes(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.dart")
        )
        assert "Animal" in symbols
        assert "Dog" in symbols

    def test_extracts_sealed_class(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.dart")
        )
        assert "Shape" in symbols
        assert "Circle" in symbols

    def test_extracts_class_modifiers(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.dart")
        )
        assert "Base" in symbols
        assert "Interface" in symbols
        assert "Final" in symbols
        assert "MixinClass" in symbols
        assert "AbstractBase" in symbols
        assert "AbstractInterface" in symbols
        assert "AbstractMixin" in symbols
        assert "BaseMixinClass" in symbols

    def test_extracts_mixin(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.dart")
        )
        assert "Serializable" in symbols
        assert "BaseMixin" in symbols

    def test_extracts_enum(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.dart")
        )
        assert "Color" in symbols

    def test_extracts_extension_type(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.dart")
        )
        assert "Meters" in symbols

    def test_extracts_typedef(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.dart")
        )
        assert "StringCallback" in symbols

    def test_extracts_functions(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.dart")
        )
        assert "greet" in symbols
        assert "fetchNumbers" in symbols

    def test_extracts_top_level_variables(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.dart")
        )
        assert "maxRetries" in symbols
        assert "defaultName" in symbols
        assert "counter" in symbols

    def test_skips_private_symbols(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.dart")
        )
        assert "_privateHelper" not in symbols
        assert "_privateVar" not in symbols
        assert "_PrivateClass" not in symbols

    def test_skips_generated_files(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.g.dart")
        )
        assert symbols == []

    def test_skips_freezed_generated_files(self, dart_project):
        ext = DartExtractor()
        symbols = ext.public_symbols(
            os.path.join(dart_project, "lib", "my_package.freezed.dart")
        )
        assert symbols == []

    def test_skips_class_members(self, tmp_path):
        """Symbols inside class bodies should not be extracted as top-level."""
        dart_file = tmp_path / "test.dart"
        dart_file.write_text(
            """\
class MyClass {
  void memberMethod() {}
  static void staticMethod() {}
  final int memberVar = 0;
}

void topLevelFunc() {}
""",
            encoding="utf-8",
        )
        ext = DartExtractor()
        symbols = ext.public_symbols(str(dart_file))
        assert "MyClass" in symbols
        assert "topLevelFunc" in symbols
        assert "memberMethod" not in symbols
        assert "staticMethod" not in symbols
        assert "memberVar" not in symbols

    def test_handles_block_comments(self, tmp_path):
        dart_file = tmp_path / "test.dart"
        dart_file.write_text(
            """\
/* This is a block comment
class CommentedClass {}
*/

class RealClass {}
""",
            encoding="utf-8",
        )
        ext = DartExtractor()
        symbols = ext.public_symbols(str(dart_file))
        assert "CommentedClass" not in symbols
        assert "RealClass" in symbols

    def test_handles_empty_file(self, tmp_path):
        dart_file = tmp_path / "empty.dart"
        dart_file.write_text("", encoding="utf-8")
        ext = DartExtractor()
        assert ext.public_symbols(str(dart_file)) == []

    def test_handles_nonexistent_file(self):
        ext = DartExtractor()
        assert ext.public_symbols("/nonexistent/file.dart") == []


class TestResolvePath:
    def test_resolve_dart_file(self, dart_project):
        ext = DartExtractor()
        result = ext.resolve_path("lib/my_package.dart", [], str(dart_project))
        assert result is not None
        assert result.endswith("my_package.dart")

    def test_resolve_dart_directory(self, dart_project):
        ext = DartExtractor()
        result = ext.resolve_path("lib", [], str(dart_project))
        assert result is not None
        assert result.endswith("lib")

    def test_resolve_with_source_paths(self, dart_project):
        ext = DartExtractor()
        result = ext.resolve_path("my_package.dart", ["lib/"], str(dart_project))
        assert result is not None
        assert result.endswith("my_package.dart")

    def test_resolve_not_found(self, dart_project):
        ext = DartExtractor()
        result = ext.resolve_path("nonexistent.dart", [], str(dart_project))
        assert result is None

    def test_resolve_implicit_extension(self, dart_project):
        ext = DartExtractor()
        result = ext.resolve_path("lib/my_package", [], str(dart_project))
        assert result is not None
        assert result.endswith("my_package.dart")


class TestUnknownDirective:
    def test_unknown_directive_errors(self):
        ext = DartExtractor()
        result = ext.extract(
            "code-help",
            {"path": "test.dart"},
            [],
            [],
            "/tmp",
        )
        assert "selfdoc:" in result
        assert "unknown directive" in result
