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


class TestDocComments:
    def test_doc_comment_on_class(self, tmp_path):
        dart_file = tmp_path / "pubspec.yaml"
        dart_file.write_text("name: test\n")
        src = tmp_path / "lib.dart"
        src.write_text("""\
/// A widget that displays a greeting.
///
/// Use this widget in your app:
/// ```dart
/// Greeting('Hello')
/// ```
class Greeting {}
""")
        ext = DartExtractor()
        result = ext.extract("ref", {"path": "lib.dart"}, [], [], str(tmp_path))
        assert "A widget that displays a greeting" in result
        assert "### Greeting" in result

    def test_doc_comment_cross_reference(self, tmp_path):
        dart_file = tmp_path / "pubspec.yaml"
        dart_file.write_text("name: test\n")
        src = tmp_path / "lib.dart"
        src.write_text("""\
/// Returns a [Widget] based on [BuildContext].
class MyWidget {}
""")
        ext = DartExtractor()
        result = ext.extract("ref", {"path": "lib.dart"}, [], [], str(tmp_path))
        assert "`Widget`" in result
        assert "`BuildContext`" in result

    def test_doc_comment_across_blank_lines(self, tmp_path):
        """Dart associates /// comments with declarations across blank lines."""
        dart_file = tmp_path / "pubspec.yaml"
        dart_file.write_text("name: test\n")
        src = tmp_path / "lib.dart"
        src.write_text("""\
/// This doc comment is above a blank line.

class Spaced {}
""")
        ext = DartExtractor()
        result = ext.extract("ref", {"path": "lib.dart"}, [], [], str(tmp_path))
        assert "This doc comment is above a blank line" in result

    def test_doc_comment_with_macro_tags(self, tmp_path):
        dart_file = tmp_path / "pubspec.yaml"
        dart_file.write_text("name: test\n")
        src = tmp_path / "lib.dart"
        src.write_text("""\
/// {@macro my_widget}
/// This uses a macro reference.
class MacroWidget {}
""")
        ext = DartExtractor()
        result = ext.extract("ref", {"path": "lib.dart"}, [], [], str(tmp_path))
        assert "{@macro my_widget}" in result

    def test_doc_comment_preserves_markdown_links(self, tmp_path):
        dart_file = tmp_path / "pubspec.yaml"
        dart_file.write_text("name: test\n")
        src = tmp_path / "lib.dart"
        src.write_text("""\
/// See [documentation](https://example.com) for details.
/// Also references [Widget] type.
class LinkedDoc {}
""")
        ext = DartExtractor()
        result = ext.extract("ref", {"path": "lib.dart"}, [], [], str(tmp_path))
        # Markdown link should be preserved
        assert "[documentation](https://example.com)" in result
        # Cross-reference should be converted
        assert "`Widget`" in result


class TestRef:
    def test_ref_extracts_library_doc(self, tmp_path):
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        src = tmp_path / "lib.dart"
        src.write_text("""\
/// The main library.
/// Provides utilities for testing.
library my_lib;

class Foo {}
""")
        ext = DartExtractor()
        result = ext.extract("ref", {"path": "lib.dart"}, [], [], str(tmp_path))
        assert "The main library" in result
        assert "Provides utilities for testing" in result
        assert "### Foo" in result

    def test_ref_extracts_declarations(self, dart_project):
        ext = DartExtractor()
        result = ext.extract(
            "ref", {"path": "lib/my_package.dart"}, [], [], str(dart_project)
        )
        assert "### Animal" in result
        assert "### Dog" in result
        assert "### greet" in result
        assert "### fetchNumbers" in result
        assert "### Color" in result
        assert "### Meters" in result
        assert "### StringCallback" in result
        assert "```dart" in result
        # Private symbols should not appear
        assert "_privateHelper" not in result
        assert "_PrivateClass" not in result

    def test_ref_no_arg_errors(self):
        ext = DartExtractor()
        result = ext.extract("ref", {"path": ""}, [], [], "/tmp")
        assert "selfdoc:" in result
        assert "requires" in result

    def test_ref_not_found_errors(self, tmp_path):
        ext = DartExtractor()
        result = ext.extract(
            "ref", {"path": "nonexistent.dart"}, [], [], str(tmp_path)
        )
        assert "selfdoc:" in result
        assert "not found" in result

    def test_ref_directory(self, dart_project):
        ext = DartExtractor()
        result = ext.extract("ref", {"path": "lib"}, [], [], str(dart_project))
        # Should include declarations from dart files in the directory
        assert "## lib" in result

    def test_ref_with_target(self, tmp_path):
        """ref directive with target renders only the specified symbol."""
        dart_file = tmp_path / "core.dart"
        dart_file.write_text(
            "/// Initializes the system.\n"
            "void initialize() {}\n\n"
            "/// Processes the input data.\n"
            "String process(String data) => data;\n",
            encoding="utf-8",
        )
        result = DartExtractor().extract(
            "ref",
            {"path": "core.dart", "target": "process"},
            [],
            [],
            str(tmp_path),
        )
        assert "### process" in result
        assert "Processes the input" in result
        assert "initialize" not in result

    def test_ref_with_target_not_found(self, tmp_path):
        dart_file = tmp_path / "core.dart"
        dart_file.write_text("void foo() {}\n", encoding="utf-8")
        result = DartExtractor().extract(
            "ref",
            {"path": "core.dart", "target": "nonexistent"},
            [],
            [],
            str(tmp_path),
        )
        assert "not found" in result


class TestProseDesc:
    def test_prose_desc_extracts_library_doc(self, tmp_path):
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        src = tmp_path / "lib.dart"
        src.write_text("""\
/// The main library.
/// Provides utilities for testing.
library my_lib;

class Foo {}
""")
        ext = DartExtractor()
        result = ext.extract(
            "prose-desc", {"path": "lib.dart"}, [], [], str(tmp_path)
        )
        assert "The main library" in result
        assert "Provides utilities for testing" in result
        assert "### Foo" not in result

    def test_prose_desc_no_doc(self, tmp_path):
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        src = tmp_path / "nodoc.dart"
        src.write_text("class Foo {}\n")
        ext = DartExtractor()
        result = ext.extract(
            "prose-desc", {"path": "nodoc.dart"}, [], [], str(tmp_path)
        )
        assert "selfdoc:" in result
        assert "no library doc" in result


class TestTableSchema:
    def test_table_schema_extracts_fields(self, tmp_path):
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        src = tmp_path / "models.dart"
        src.write_text("""\
/// A user model.
class User {
  /// The user's unique identifier.
  final String id;
  final String name;
  int age = 0;
  String? email;

  User(this.id, this.name);
}
""")
        ext = DartExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "models.dart", "target": "User"},
            [],
            [],
            str(tmp_path),
        )
        assert "| Field | Type | Default | Description |" in result
        assert "`id`" in result
        assert "`String`" in result
        assert "`age`" in result
        assert "`0`" in result
        assert "unique identifier" in result

    def test_table_schema_all_classes(self, tmp_path):
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        src = tmp_path / "models.dart"
        src.write_text("""\
class Point {
  final double x;
  final double y;

  Point(this.x, this.y);
}

class Size {
  final double width;
  final double height;

  Size(this.width, this.height);
}
""")
        ext = DartExtractor()
        result = ext.extract(
            "table-schema", {"path": "models.dart"}, [], [], str(tmp_path)
        )
        assert "### Point" in result
        assert "### Size" in result
        assert "`x`" in result
        assert "`width`" in result

    def test_table_schema_class_not_found(self, tmp_path):
        """When the file has a class with fields but the target name doesn't match."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        src = tmp_path / "models.dart"
        src.write_text("""\
class Foo {
  final String name;
  Foo(this.name);
}
""")
        ext = DartExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "models.dart", "target": "Bar"},
            [],
            [],
            str(tmp_path),
        )
        assert "selfdoc:" in result
        assert "not found" in result

    def test_table_schema_no_fields(self, tmp_path):
        """When the file has a class but it has no fields."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        src = tmp_path / "models.dart"
        src.write_text("class Foo {}\n")
        ext = DartExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "models.dart", "target": "Foo"},
            [],
            [],
            str(tmp_path),
        )
        assert "selfdoc:" in result
        assert "no classes with fields" in result

    def test_table_schema_skips_private_fields(self, tmp_path):
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        src = tmp_path / "models.dart"
        src.write_text("""\
class Config {
  final String host;
  final int _port;
  String? _cache;

  Config(this.host);
}
""")
        ext = DartExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "models.dart", "target": "Config"},
            [],
            [],
            str(tmp_path),
        )
        assert "`host`" in result
        assert "_port" not in result
        assert "_cache" not in result


class TestPackageResolution:
    def test_resolve_package_path(self, dart_project):
        ext = DartExtractor()
        result = ext.resolve_path(
            "package:my_package/my_package.dart", [], str(dart_project)
        )
        assert result is not None
        assert result.endswith("my_package.dart")
        assert "/lib/" in result

    def test_resolve_package_path_wrong_name(self, dart_project):
        ext = DartExtractor()
        result = ext.resolve_path(
            "package:wrong_name/my_package.dart", [], str(dart_project)
        )
        assert result is None

    def test_resolve_package_path_nonexistent_file(self, dart_project):
        ext = DartExtractor()
        result = ext.resolve_path(
            "package:my_package/nonexistent.dart", [], str(dart_project)
        )
        assert result is None

    def test_resolve_package_path_subdirectory(self, dart_project):
        """Package paths can reference files in subdirectories."""
        src_file = os.path.join(dart_project, "lib", "src", "helper.dart")
        os.makedirs(os.path.dirname(src_file), exist_ok=True)
        with open(src_file, "w") as f:
            f.write("class Helper {}\n")
        ext = DartExtractor()
        result = ext.resolve_path(
            "package:my_package/src/helper.dart", [], str(dart_project)
        )
        assert result is not None
        assert result.endswith("helper.dart")


class TestPartFiles:
    def test_part_file_symbols_included(self, tmp_path):
        """Symbols from part files should appear in the library's symbol list."""
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        src_dir = lib_dir / "src"
        src_dir.mkdir()

        # Library file with part directive
        (lib_dir / "mylib.dart").write_text("""\
/// My library.
library mylib;

part 'src/models.dart';
part 'src/utils.dart';

class LibraryClass {}
""", encoding="utf-8")

        # Part file 1
        (src_dir / "models.dart").write_text("""\
part of '../mylib.dart';

class User {}
class Product {}
""", encoding="utf-8")

        # Part file 2
        (src_dir / "utils.dart").write_text("""\
part of '../mylib.dart';

String formatName(String name) => name.trim();
const defaultTimeout = 30;
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "mylib.dart"))
        assert "LibraryClass" in symbols
        assert "User" in symbols
        assert "Product" in symbols
        assert "formatName" in symbols
        assert "defaultTimeout" in symbols

    def test_generated_part_files_skipped(self, tmp_path):
        """Generated part files (.g.dart, .freezed.dart) should be skipped."""
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()

        (lib_dir / "model.dart").write_text("""\
library model;

part 'model.g.dart';
part 'model.freezed.dart';

class Model {}
""", encoding="utf-8")

        (lib_dir / "model.g.dart").write_text("""\
part of 'model.dart';
class GeneratedModel {}
""", encoding="utf-8")

        (lib_dir / "model.freezed.dart").write_text("""\
part of 'model.dart';
class FreezedModel {}
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "model.dart"))
        assert "Model" in symbols
        assert "GeneratedModel" not in symbols
        assert "FreezedModel" not in symbols

    def test_part_files_in_ref_handler(self, tmp_path):
        """The ref handler should include declarations from part files."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()

        (lib_dir / "mylib.dart").write_text("""\
/// My library docs.
library mylib;

part 'part_a.dart';

class MainClass {}
""", encoding="utf-8")

        (lib_dir / "part_a.dart").write_text("""\
part of 'mylib.dart';

/// A utility class from part file.
class PartClass {}
""", encoding="utf-8")

        ext = DartExtractor()
        result = ext.extract("ref", {"path": "lib/mylib.dart"}, [], [], str(tmp_path))
        assert "### MainClass" in result
        assert "### PartClass" in result
        assert "A utility class from part file" in result

    def test_missing_part_file_skipped(self, tmp_path):
        """If a part file doesn't exist, it should be silently skipped."""
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()

        (lib_dir / "mylib.dart").write_text("""\
library mylib;

part 'missing.dart';

class Present {}
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "mylib.dart"))
        assert "Present" in symbols

    def test_private_symbols_in_part_files_skipped(self, tmp_path):
        """Private symbols in part files should not be included."""
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()

        (lib_dir / "mylib.dart").write_text("""\
library mylib;
part 'impl.dart';
class Public {}
""", encoding="utf-8")

        (lib_dir / "impl.dart").write_text("""\
part of 'mylib.dart';
class _Private {}
class AlsoPublic {}
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "mylib.dart"))
        assert "Public" in symbols
        assert "AlsoPublic" in symbols
        assert "_Private" not in symbols


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


class TestExportFollowing:
    def test_basic_export(self, tmp_path):
        """Exported symbols should appear in the barrel file's symbol list."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        src_dir = lib_dir / "src"
        src_dir.mkdir(parents=True)

        # Barrel file
        (lib_dir / "test.dart").write_text("""\
export 'src/models.dart';
export 'src/utils.dart';
""", encoding="utf-8")

        (src_dir / "models.dart").write_text("""\
class User {}
class Product {}
""", encoding="utf-8")

        (src_dir / "utils.dart").write_text("""\
String formatName(String name) => name.trim();
const apiVersion = '1.0';
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "test.dart"))
        assert "User" in symbols
        assert "Product" in symbols
        assert "formatName" in symbols
        assert "apiVersion" in symbols

    def test_export_show_combinator(self, tmp_path):
        """show combinator should filter to only the listed symbols."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        src_dir = lib_dir / "src"
        src_dir.mkdir(parents=True)

        (lib_dir / "barrel.dart").write_text("""\
export 'src/models.dart' show User;
""", encoding="utf-8")

        (src_dir / "models.dart").write_text("""\
class User {}
class Product {}
class Order {}
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "barrel.dart"))
        assert "User" in symbols
        assert "Product" not in symbols
        assert "Order" not in symbols

    def test_export_hide_combinator(self, tmp_path):
        """hide combinator should exclude the listed symbols."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        src_dir = lib_dir / "src"
        src_dir.mkdir(parents=True)

        (lib_dir / "barrel.dart").write_text("""\
export 'src/models.dart' hide Product;
""", encoding="utf-8")

        (src_dir / "models.dart").write_text("""\
class User {}
class Product {}
class Order {}
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "barrel.dart"))
        assert "User" in symbols
        assert "Product" not in symbols
        assert "Order" in symbols

    def test_transitive_exports(self, tmp_path):
        """Exports should be followed transitively (A exports B which exports C)."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        src_dir = lib_dir / "src"
        src_dir.mkdir(parents=True)

        (lib_dir / "test.dart").write_text("""\
export 'src/layer1.dart';
""", encoding="utf-8")

        (src_dir / "layer1.dart").write_text("""\
export 'layer2.dart';
class FromLayer1 {}
""", encoding="utf-8")

        (src_dir / "layer2.dart").write_text("""\
class FromLayer2 {}
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "test.dart"))
        assert "FromLayer1" in symbols
        assert "FromLayer2" in symbols

    def test_circular_export_detection(self, tmp_path):
        """Circular exports should not cause infinite loops."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir(parents=True)

        (lib_dir / "a.dart").write_text("""\
export 'b.dart';
class FromA {}
""", encoding="utf-8")

        (lib_dir / "b.dart").write_text("""\
export 'a.dart';
class FromB {}
""", encoding="utf-8")

        ext = DartExtractor()
        # Should not hang or crash
        symbols = ext.public_symbols(str(lib_dir / "a.dart"))
        assert "FromA" in symbols
        assert "FromB" in symbols

    def test_conditional_export(self, tmp_path):
        """Conditional exports should include all variants."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        src_dir = lib_dir / "src"
        src_dir.mkdir(parents=True)

        (lib_dir / "test.dart").write_text("""\
export 'src/stub.dart' if (dart.library.io) 'src/native.dart';
""", encoding="utf-8")

        (src_dir / "stub.dart").write_text("""\
class StubImpl {}
""", encoding="utf-8")

        (src_dir / "native.dart").write_text("""\
class NativeImpl {}
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "test.dart"))
        assert "StubImpl" in symbols
        assert "NativeImpl" in symbols

    def test_export_with_local_declarations(self, tmp_path):
        """Local declarations should shadow re-exported names in ref output."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        src_dir = lib_dir / "src"
        src_dir.mkdir(parents=True)

        (lib_dir / "test.dart").write_text("""\
/// The main API.
export 'src/models.dart';

/// Local override of User.
class User {}
""", encoding="utf-8")

        (src_dir / "models.dart").write_text("""\
/// Exported User.
class User {}
class Product {}
""", encoding="utf-8")

        ext = DartExtractor()
        result = ext.extract("ref", {"path": "lib/test.dart"}, [], [], str(tmp_path))
        # Should have User (local) and Product (exported)
        assert "### User" in result
        assert "### Product" in result
        # The local User's doc should win (shadow)
        assert "Local override" in result

    def test_export_missing_file_skipped(self, tmp_path):
        """Missing export targets should be silently skipped."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir(parents=True)

        (lib_dir / "test.dart").write_text("""\
export 'nonexistent.dart';
class Local {}
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "test.dart"))
        assert "Local" in symbols

    def test_export_in_ref_handler(self, tmp_path):
        """The ref handler should include declarations from exports."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        src_dir = lib_dir / "src"
        src_dir.mkdir(parents=True)

        (lib_dir / "test.dart").write_text("""\
/// Package API.
export 'src/widget.dart';
""", encoding="utf-8")

        (src_dir / "widget.dart").write_text("""\
/// A custom widget.
class MyWidget {}
""", encoding="utf-8")

        ext = DartExtractor()
        result = ext.extract("ref", {"path": "lib/test.dart"}, [], [], str(tmp_path))
        assert "### MyWidget" in result
        assert "A custom widget" in result

    def test_show_combinator_multiple_names(self, tmp_path):
        """show combinator with multiple names."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        src_dir = lib_dir / "src"
        src_dir.mkdir(parents=True)

        (lib_dir / "barrel.dart").write_text("""\
export 'src/all.dart' show Alpha, Beta;
""", encoding="utf-8")

        (src_dir / "all.dart").write_text("""\
class Alpha {}
class Beta {}
class Gamma {}
class Delta {}
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "barrel.dart"))
        assert "Alpha" in symbols
        assert "Beta" in symbols
        assert "Gamma" not in symbols
        assert "Delta" not in symbols


class TestEndToEnd:
    def test_full_library_with_parts_and_exports(self, tmp_path):
        """A complete Dart library with parts, exports, and doc comments."""
        (tmp_path / "pubspec.yaml").write_text("name: marketplace\nversion: 1.0.0\n")
        lib_dir = tmp_path / "lib"
        src_dir = lib_dir / "src"
        src_dir.mkdir(parents=True)

        # Main barrel file
        (lib_dir / "marketplace.dart").write_text("""\
/// The marketplace library.
///
/// Provides models and utilities for the marketplace.
library marketplace;

export 'src/models.dart';
export 'src/cart.dart' show Cart;
""", encoding="utf-8")

        # Models file with part
        (src_dir / "models.dart").write_text("""\
/// Models for the marketplace.
library;

part 'models_impl.dart';

/// A product in the marketplace.
class Product {
  final String name;
  final double price;

  Product(this.name, this.price);
}
""", encoding="utf-8")

        # Part file with additional model
        (src_dir / "models_impl.dart").write_text("""\
part of 'models.dart';

/// A category for organizing products.
class Category {
  final String label;

  Category(this.label);
}
""", encoding="utf-8")

        # Cart file (only Cart is shown in barrel)
        (src_dir / "cart.dart").write_text("""\
/// A shopping cart.
class Cart {
  final List<dynamic> items;

  Cart() : items = [];
}

/// Internal cart item -- hidden by show combinator.
class CartItem {
  final String productId;
  final int quantity;

  CartItem(this.productId, this.quantity);
}
""", encoding="utf-8")

        ext = DartExtractor()

        # Test symbol extraction from barrel
        symbols = ext.public_symbols(str(lib_dir / "marketplace.dart"))
        assert "Product" in symbols
        assert "Category" in symbols  # From part file via export
        assert "Cart" in symbols       # show combinator
        assert "CartItem" not in symbols  # Hidden by show combinator

        # Test ref handler
        result = ext.extract("ref", {"path": "lib/marketplace.dart"}, [], [], str(tmp_path))
        assert "The marketplace library" in result
        assert "### Product" in result
        assert "### Category" in result
        assert "### Cart" in result
        assert "### CartItem" not in result  # Hidden by show combinator
        assert "A product in the marketplace" in result
        assert "A category for organizing" in result
        assert "A shopping cart" in result

    def test_package_import_in_exports(self, tmp_path):
        """Package-style imports in exports should be resolved."""
        (tmp_path / "pubspec.yaml").write_text("name: myapp\n")
        lib_dir = tmp_path / "lib"
        src_dir = lib_dir / "src"
        src_dir.mkdir(parents=True)

        (lib_dir / "myapp.dart").write_text("""\
export 'src/core.dart';
""", encoding="utf-8")

        (src_dir / "core.dart").write_text("""\
class AppCore {}
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "myapp.dart"))
        assert "AppCore" in symbols

    def test_detection_in_registry(self, tmp_path):
        """DartExtractor should be usable via the registry."""
        from selfdoc.extractors import EXTRACTORS, detect_language

        (tmp_path / "pubspec.yaml").write_text("name: test\n")

        assert "dart" in EXTRACTORS
        assert detect_language(str(tmp_path)) == "dart"

    def test_generated_files_throughout_pipeline(self, tmp_path):
        """Generated files should be skipped at every level."""
        (tmp_path / "pubspec.yaml").write_text("name: test\n")
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()

        (lib_dir / "test.dart").write_text("""\
part 'test.g.dart';
export 'test.freezed.dart';

class RealClass {}
""", encoding="utf-8")

        (lib_dir / "test.g.dart").write_text("""\
part of 'test.dart';
class Generated1 {}
""", encoding="utf-8")

        (lib_dir / "test.freezed.dart").write_text("""\
class Generated2 {}
""", encoding="utf-8")

        ext = DartExtractor()
        symbols = ext.public_symbols(str(lib_dir / "test.dart"))
        assert "RealClass" in symbols
        assert "Generated1" not in symbols
        assert "Generated2" not in symbols


class TestModuleDocstring:
    def test_module_docstring(self, tmp_path):
        dart_file = tmp_path / "lib.dart"
        dart_file.write_text(
            "/// The main library for my_package.\n"
            "/// Provides utilities for parsing.\n"
            "library my_package;\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.module_docstring(str(dart_file))
        assert result == "The main library for my_package.\nProvides utilities for parsing."


class TestSymbolDetails:
    def test_symbol_details_basic_function(self, tmp_path):
        """Function with all params documented."""
        dart_file = tmp_path / "lib.dart"
        dart_file.write_text(
            "/// Greets the [name] with a [greeting].\n"
            "/// Returns the formatted message.\n"
            "String greet(String name, String greeting) {\n"
            "  return '$greeting, $name!';\n"
            "}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "greet")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0] == {"name": "name", "type": "String", "documented": True}
        assert result["params"][1] == {"name": "greeting", "type": "String", "documented": True}
        assert result["return_type"] == "String"
        assert result["return_documented"] is True

    def test_symbol_details_undocumented_params(self, tmp_path):
        """Some params not in doc brackets."""
        dart_file = tmp_path / "lib.dart"
        dart_file.write_text(
            "/// Sends a message to [recipient].\n"
            "void sendMessage(String recipient, String body, int priority) {\n"
            "}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "sendMessage")
        assert result is not None
        assert len(result["params"]) == 3
        assert result["params"][0]["name"] == "recipient"
        assert result["params"][0]["documented"] is True
        assert result["params"][1]["name"] == "body"
        assert result["params"][1]["documented"] is False
        assert result["params"][2]["name"] == "priority"
        assert result["params"][2]["documented"] is False

    def test_symbol_details_named_params(self, tmp_path):
        """Named required params with {required Type name}."""
        dart_file = tmp_path / "lib.dart"
        dart_file.write_text(
            "/// Fetches items for [userId] with [limit].\n"
            "Future<List<String>> fetchItems(\n"
            "  String userId,\n"
            "  {required int limit,\n"
            "   bool includeDeleted = false}\n"
            ") async {\n"
            "  return [];\n"
            "}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "fetchItems")
        assert result is not None
        assert len(result["params"]) == 3
        assert result["params"][0] == {"name": "userId", "type": "String", "documented": True}
        assert result["params"][1] == {"name": "limit", "type": "int", "documented": True}
        assert result["params"][2] == {"name": "includeDeleted", "type": "bool", "documented": False}
        assert result["return_type"] == "Future<List<String>>"

    def test_symbol_details_optional_positional(self, tmp_path):
        """Optional positional params with [Type name = default]."""
        dart_file = tmp_path / "lib.dart"
        dart_file.write_text(
            "/// Logs [message] with optional [level].\n"
            "void log(String message, [int level = 0, String? tag]) {\n"
            "}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "log")
        assert result is not None
        assert len(result["params"]) == 3
        assert result["params"][0] == {"name": "message", "type": "String", "documented": True}
        assert result["params"][1] == {"name": "level", "type": "int", "documented": True}
        assert result["params"][2] == {"name": "tag", "type": "String?", "documented": False}

    def test_symbol_details_return_type(self, tmp_path):
        """Function with return type and Returns doc."""
        dart_file = tmp_path / "lib.dart"
        dart_file.write_text(
            "/// Computes the sum.\n"
            "/// Returns the total.\n"
            "int sum(int a, int b) {\n"
            "  return a + b;\n"
            "}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "sum")
        assert result is not None
        assert result["return_type"] == "int"
        assert result["return_documented"] is True

    def test_symbol_details_no_return_type(self, tmp_path):
        """Void function."""
        dart_file = tmp_path / "lib.dart"
        dart_file.write_text(
            "/// Prints hello.\n"
            "void sayHello() {\n"
            "  print('hello');\n"
            "}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "sayHello")
        assert result is not None
        assert result["params"] == []
        assert result["return_type"] == "void"
        assert result["return_documented"] is False

    def test_symbol_details_unknown(self, tmp_path):
        """Unknown symbol returns None."""
        dart_file = tmp_path / "lib.dart"
        dart_file.write_text(
            "void hello() {}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "nonexistent")
        assert result is None

    def test_symbol_details_dotted_class_method(self, tmp_path):
        """Dotted name resolves to a method within a class."""
        dart_file = tmp_path / "repo.dart"
        dart_file.write_text(
            "class UserRepository {\n"
            "  /// Finds a user by their [id].\n"
            "  /// Returns the user or null if not found.\n"
            "  Future<User?> findById(int id) async {\n"
            "    return null;\n"
            "  }\n"
            "\n"
            "  void deleteAll() {}\n"
            "}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "UserRepository.findById")
        assert result is not None
        assert len(result["params"]) == 1
        assert result["params"][0] == {"name": "id", "type": "int", "documented": True}
        assert result["return_type"] == "Future<User?>"
        assert result["return_documented"] is True

    def test_symbol_details_dotted_abstract_class(self, tmp_path):
        """Dotted name works with abstract classes."""
        dart_file = tmp_path / "service.dart"
        dart_file.write_text(
            "abstract class AuthService {\n"
            "  /// Authenticates a [user] with [password].\n"
            "  Future<bool> login(String user, String password);\n"
            "}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "AuthService.login")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0]["name"] == "user"
        assert result["params"][1]["name"] == "password"
        assert result["return_type"] == "Future<bool>"

    def test_symbol_details_dotted_mixin(self, tmp_path):
        """Dotted name works with mixins."""
        dart_file = tmp_path / "mixin.dart"
        dart_file.write_text(
            "mixin Loggable {\n"
            "  void log(String message) {\n"
            "    print(message);\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "Loggable.log")
        assert result is not None
        assert len(result["params"]) == 1
        assert result["params"][0]["name"] == "message"

    def test_symbol_details_dotted_unknown_type(self, tmp_path):
        """Dotted name with nonexistent type returns None."""
        dart_file = tmp_path / "lib.dart"
        dart_file.write_text(
            "class Foo {\n"
            "  void bar() {}\n"
            "}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "NonExistent.bar")
        assert result is None

    def test_symbol_details_dotted_unknown_member(self, tmp_path):
        """Dotted name with nonexistent member returns None."""
        dart_file = tmp_path / "lib.dart"
        dart_file.write_text(
            "class Foo {\n"
            "  void bar() {}\n"
            "}\n",
            encoding="utf-8",
        )
        ext = DartExtractor()
        result = ext.symbol_details(str(dart_file), "Foo.nonexistent")
        assert result is None
