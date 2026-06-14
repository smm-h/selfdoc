"""Tests for the Swift source extractor (selfdoc.extractors.swift)."""

import os

import pytest

from selfdoc.extractors.swift import SwiftExtractor, _parse_swift_doc_comment


@pytest.fixture()
def swift_project(tmp_path):
    """Create a sample Swift project structure for testing."""
    sources_dir = os.path.join(tmp_path, "Sources")
    os.makedirs(sources_dir)

    # Main source file with module doc, public/open declarations, doc comments
    parser_swift = os.path.join(sources_dir, "Parser.swift")
    with open(parser_swift, "w", encoding="utf-8") as f:
        f.write("""\
/// Parser module: handles source code parsing and AST construction.
/// Supports incremental parsing and error recovery.

import Foundation

/// A source code parser with incremental support.
///
/// Use ``Parser`` to parse source files into an AST.
/// - Note: Thread-safe for read operations only.
public class Parser {
    /// The source text being parsed.
    public var sourceText: String = ""

    /// Whether to enable error recovery.
    public let errorRecovery: Bool = true

    /// Parse the given source text into an AST.
    ///
    /// - Parameter source: The source code to parse.
    /// - Returns: The parsed AST root node.
    /// - Throws: `ParseError` if the source is malformed.
    public func parse(source: String) -> ASTNode {
        return ASTNode()
    }

    /// Configure the parser with options.
    ///
    /// - Parameters:
    ///   - mode: The parsing mode to use.
    ///   - flags: Additional compiler flags.
    /// - Returns: The configured parser instance.
    public static func configure(mode: ParseMode, flags: [String]) -> Parser {
        return Parser()
    }

    private func internalHelper() {}
    func defaultAccessHelper() {}
}

/// An open base class for AST visitors.
open class ASTVisitor {
    /// Visit a node in the AST.
    open func visit(node: ASTNode) {}
}

/// All possible token types.
public enum TokenType {
    case identifier
    case keyword
    case literal
}

/// The parser protocol that all parsers conform to.
public protocol Parseable {
    func parse() -> ASTNode
}

/// A type alias for parse results.
public typealias ParseResult = Result<ASTNode, ParseError>

/// Maximum parse depth allowed.
public let maxParseDepth: Int = 256

/// Current parser version.
public static var parserVersion: String = "1.0"

public actor ParseCoordinator {
    public func coordinate() async {}
}
""")

    # File for blank-line association test
    blankline_swift = os.path.join(sources_dir, "BlankLine.swift")
    with open(blankline_swift, "w", encoding="utf-8") as f:
        f.write("""\
/// This comment is for the function below.
public func attached() {}

/// This comment is NOT for the function below.

public func detached() {}
""")

    # Struct-heavy file for table-schema tests
    config_swift = os.path.join(sources_dir, "Config.swift")
    with open(config_swift, "w", encoding="utf-8") as f:
        f.write("""\
/// Configuration for the parser system.
public struct ParserConfig {
    /// The maximum number of tokens to buffer.
    var bufferSize: Int = 1024
    /// Whether to enable strict mode.
    var strictMode: Bool = false
    /// The output format for results.
    var outputFormat: String = "json"
    let version: Int = 1
}

public struct NetworkConfig: Codable {
    var host: String = "localhost"
    var port: Int = 8080
    var timeout: Double = 30.0
}
""")

    # Package.swift marker file
    package_swift = os.path.join(tmp_path, "Package.swift")
    with open(package_swift, "w", encoding="utf-8") as f:
        f.write("// swift-tools-version: 5.9\n")

    return tmp_path


class TestDetection:
    def test_detect_with_package_swift(self, swift_project):
        ext = SwiftExtractor()
        assert ext.detect(str(swift_project)) is True

    def test_detect_without_package_swift(self, tmp_path):
        ext = SwiftExtractor()
        assert ext.detect(str(tmp_path)) is False


class TestFileExtensions:
    def test_file_extensions(self):
        ext = SwiftExtractor()
        assert ext.file_extensions() == [".swift"]


class TestPublicSymbols:
    def test_public_symbols_basic(self, swift_project):
        ext = SwiftExtractor()
        filepath = os.path.join(swift_project, "Sources", "Parser.swift")
        symbols = ext.public_symbols(filepath)
        # public class
        assert "Parser" in symbols
        # public enum
        assert "TokenType" in symbols
        # public protocol
        assert "Parseable" in symbols
        # public func
        assert "parse" in symbols

    def test_public_symbols_open(self, swift_project):
        ext = SwiftExtractor()
        filepath = os.path.join(swift_project, "Sources", "Parser.swift")
        symbols = ext.public_symbols(filepath)
        # open class
        assert "ASTVisitor" in symbols
        # open func
        assert "visit" in symbols

    def test_public_symbols_excludes_private(self, swift_project):
        ext = SwiftExtractor()
        filepath = os.path.join(swift_project, "Sources", "Parser.swift")
        symbols = ext.public_symbols(filepath)
        # private func should NOT appear
        assert "internalHelper" not in symbols
        # default access (no keyword) func should NOT appear
        assert "defaultAccessHelper" not in symbols

    def test_public_symbols_static_class_methods(self, tmp_path):
        swift_file = tmp_path / "Methods.swift"
        swift_file.write_text(
            "public static func staticMethod() {}\n"
            "public class func classMethod() {}\n",
            encoding="utf-8",
        )
        ext = SwiftExtractor()
        symbols = ext.public_symbols(str(swift_file))
        assert "staticMethod" in symbols
        assert "classMethod" in symbols


class TestDocCommentParsing:
    def test_doc_comment_basic(self):
        result = _parse_swift_doc_comment("A simple doc comment.")
        assert "A simple doc comment." in result

    def test_doc_comment_parameters(self):
        text = "- Parameter source: The source code to parse."
        result = _parse_swift_doc_comment(text)
        assert "**Parameters:**" in result
        assert "`source`" in result
        assert "The source code to parse." in result

    def test_doc_comment_parameters_block(self):
        text = (
            "- Parameters:\n"
            "  - mode: The parsing mode to use.\n"
            "  - flags: Additional compiler flags."
        )
        result = _parse_swift_doc_comment(text)
        assert "**Parameters:**" in result
        assert "`mode`" in result
        assert "The parsing mode to use." in result
        assert "`flags`" in result
        assert "Additional compiler flags." in result

    def test_doc_comment_returns_throws(self):
        text = (
            "- Returns: The parsed AST root node.\n"
            "- Throws: `ParseError` if the source is malformed."
        )
        result = _parse_swift_doc_comment(text)
        assert "**Returns:** The parsed AST root node." in result
        assert "**Throws:** `ParseError` if the source is malformed." in result

    def test_doc_comment_callout_keywords(self):
        text = (
            "- Note: Thread-safe for read operations only.\n"
            "- Warning: Do not use in production."
        )
        result = _parse_swift_doc_comment(text)
        assert "**Note:** Thread-safe for read operations only." in result
        assert "**Warning:** Do not use in production." in result

    def test_doc_comment_symbol_links(self):
        text = "Use ``Parser`` to parse source files."
        result = _parse_swift_doc_comment(text)
        assert "`Parser`" in result
        # Double backticks should be converted to single
        assert "``Parser``" not in result


class TestBlankLineAssociation:
    def test_doc_comment_no_blank_line_association(self, swift_project):
        ext = SwiftExtractor()
        result = ext.extract(
            "ref",
            {"path": "Sources/BlankLine.swift"},
            [],
            [],
            str(swift_project),
        )
        # "attached" should have the doc comment
        assert "This comment is for the function below" in result
        # "detached" should NOT have its doc comment because of the blank line
        assert "This comment is NOT for the function below" not in result


class TestRef:
    def test_ref_handler(self, swift_project):
        ext = SwiftExtractor()
        result = ext.extract(
            "ref",
            {"path": "Sources/Parser.swift"},
            [],
            [],
            str(swift_project),
        )
        # Module doc should be present
        assert "Parser module: handles source code parsing" in result
        assert "Supports incremental parsing and error recovery" in result

        # ## heading for the file
        assert "## Sources/Parser.swift" in result

        # ### headings for public/open symbols
        assert "### Parser" in result
        assert "### ASTVisitor" in result
        assert "### TokenType" in result
        assert "### Parseable" in result
        assert "### ParseResult" in result
        assert "### maxParseDepth" in result
        assert "### parserVersion" in result
        assert "### ParseCoordinator" in result
        assert "### parse" in result
        assert "### configure" in result
        assert "### visit" in result

        # Code blocks with swift syntax
        assert "```swift" in result

        # Doc comment text should appear
        assert "A source code parser with incremental support" in result
        assert "Parse the given source text into an AST" in result

        # Private/default-access methods should NOT appear
        assert "internalHelper" not in result
        assert "defaultAccessHelper" not in result

    def test_ref_with_target(self, tmp_path):
        """ref directive with target renders only the specified symbol."""
        swift_file = tmp_path / "Core.swift"
        swift_file.write_text(
            "/// Initializes the parser.\n"
            "public func initialize() {}\n\n"
            "/// Parses the input.\n"
            "public func parse(_ input: String) -> Bool {\n"
            "    return true\n"
            "}\n",
            encoding="utf-8",
        )
        result = SwiftExtractor().extract(
            "ref",
            {"path": "Core.swift", "target": "parse"},
            [],
            [],
            str(tmp_path),
        )
        assert "### parse" in result
        assert "Parses the input" in result
        assert "initialize" not in result

    def test_ref_with_target_not_found(self, tmp_path):
        swift_file = tmp_path / "Core.swift"
        swift_file.write_text("public func foo() {}\n", encoding="utf-8")
        result = SwiftExtractor().extract(
            "ref",
            {"path": "Core.swift", "target": "nonexistent"},
            [],
            [],
            str(tmp_path),
        )
        assert "not found" in result


class TestProseDesc:
    def test_prose_desc_handler(self, swift_project):
        ext = SwiftExtractor()
        result = ext.extract(
            "prose-desc",
            {"path": "Sources/Parser.swift"},
            [],
            [],
            str(swift_project),
        )
        # Module-level doc comment should be present
        assert "Parser module" in result
        assert "Supports incremental parsing and error recovery" in result
        # Declaration-level comments should NOT be present
        assert "### Parser" not in result
        assert "pub" not in result
        assert "A source code parser with incremental support" not in result


class TestTableSchema:
    def test_table_schema_struct_fields(self, swift_project):
        ext = SwiftExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "Sources/Config.swift", "target": "ParserConfig"},
            [],
            [],
            str(swift_project),
        )
        # Should produce a markdown table
        assert "| Field | Type | Default | Description |" in result
        # All fields should appear with correct types and defaults
        assert "`bufferSize`" in result
        assert "`Int`" in result
        assert "`1024`" in result
        assert "The maximum number of tokens to buffer" in result
        assert "`strictMode`" in result
        assert "`Bool`" in result
        assert "`false`" in result
        assert "`outputFormat`" in result
        assert "`String`" in result
        assert "`version`" in result

    def test_table_schema_specific_struct(self, swift_project):
        ext = SwiftExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "Sources/Config.swift", "target": "NetworkConfig"},
            [],
            [],
            str(swift_project),
        )
        # Only NetworkConfig fields should appear
        assert "`host`" in result
        assert "`port`" in result
        assert "`timeout`" in result
        assert "`8080`" in result
        assert "`30.0`" in result
        # ParserConfig fields should NOT appear
        assert "`bufferSize`" not in result
        assert "`strictMode`" not in result


# These tests verify registration done in __init__.py
class TestRegistry:
    def test_registry_includes_swift(self):
        from selfdoc.extractors import EXTRACTORS

        assert "swift" in EXTRACTORS

    def test_detection_order_includes_swift(self):
        from selfdoc.extractors import _DETECTION_ORDER

        names = [ext.name for ext in _DETECTION_ORDER]
        assert "swift" in names


class TestUnknownDirective:
    def test_unknown_directive_errors(self):
        ext = SwiftExtractor()
        result = ext.extract(
            "code-help",
            {"path": "test.swift"},
            [],
            [],
            "/tmp",
        )
        assert "selfdoc:" in result
        assert "unknown directive" in result


class TestResolvePath:
    def test_resolve_swift_file(self, swift_project):
        ext = SwiftExtractor()
        result = ext.resolve_path("Sources/Parser.swift", [], str(swift_project))
        assert result is not None
        assert result.endswith("Parser.swift")

    def test_resolve_swift_directory(self, swift_project):
        ext = SwiftExtractor()
        result = ext.resolve_path("Sources", [], str(swift_project))
        assert result is not None
        assert result.endswith("Sources")

    def test_resolve_swift_with_source_paths(self, swift_project):
        ext = SwiftExtractor()
        result = ext.resolve_path("Parser.swift", ["Sources/"], str(swift_project))
        assert result is not None
        assert result.endswith("Parser.swift")

    def test_resolve_swift_not_found(self, swift_project):
        ext = SwiftExtractor()
        result = ext.resolve_path("nonexistent.swift", [], str(swift_project))
        assert result is None

    def test_resolve_swift_implicit_extension(self, swift_project):
        ext = SwiftExtractor()
        result = ext.resolve_path("Sources/Parser", [], str(swift_project))
        assert result is not None
        assert result.endswith("Parser.swift")


class TestModuleDocstring:
    def test_module_docstring(self, tmp_path):
        swift_file = tmp_path / "Mod.swift"
        swift_file.write_text(
            "/// Parser module for source code.\n"
            "/// Handles incremental parsing.\n"
            "\n"
            "import Foundation\n",
            encoding="utf-8",
        )
        ext = SwiftExtractor()
        result = ext.module_docstring(str(swift_file))
        assert result == "Parser module for source code.\nHandles incremental parsing."


class TestSymbolDetails:
    def test_symbol_details_documented_params(self, swift_project):
        """Function with - Parameter doc tags reports params as documented."""
        ext = SwiftExtractor()
        filepath = os.path.join(swift_project, "Sources", "Parser.swift")
        result = ext.symbol_details(filepath, "parse")
        assert result is not None
        assert len(result["params"]) == 1
        p = result["params"][0]
        assert p["name"] == "source"
        assert p["type"] == "String"
        assert p["documented"] is True

    def test_symbol_details_undocumented_params(self, tmp_path):
        """Function without doc tags reports params as undocumented."""
        swift_file = tmp_path / "Funcs.swift"
        swift_file.write_text(
            "public func process(input: Data, count: Int) -> Bool {\n"
            "    return true\n"
            "}\n",
            encoding="utf-8",
        )
        ext = SwiftExtractor()
        result = ext.symbol_details(str(swift_file), "process")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0] == {"name": "input", "type": "Data", "documented": False}
        assert result["params"][1] == {"name": "count", "type": "Int", "documented": False}

    def test_symbol_details_no_params(self, tmp_path):
        """Function with no parameters returns empty params list."""
        swift_file = tmp_path / "Empty.swift"
        swift_file.write_text(
            "public func doSomething() {\n"
            "}\n",
            encoding="utf-8",
        )
        ext = SwiftExtractor()
        result = ext.symbol_details(str(swift_file), "doSomething")
        assert result is not None
        assert result["params"] == []
        assert result["return_type"] is None
        assert result["return_documented"] is False

    def test_symbol_details_unknown_symbol(self, swift_project):
        """Returns None for a symbol that doesn't exist."""
        ext = SwiftExtractor()
        filepath = os.path.join(swift_project, "Sources", "Parser.swift")
        result = ext.symbol_details(filepath, "nonexistent")
        assert result is None

    def test_symbol_details_return_type(self, swift_project):
        """Verifies return type extraction and return_documented flag."""
        ext = SwiftExtractor()
        filepath = os.path.join(swift_project, "Sources", "Parser.swift")
        result = ext.symbol_details(filepath, "parse")
        assert result is not None
        assert result["return_type"] == "ASTNode"
        assert result["return_documented"] is True

    def test_symbol_details_parameters_block_syntax(self, swift_project):
        """Function with - Parameters: block syntax documents params correctly."""
        ext = SwiftExtractor()
        filepath = os.path.join(swift_project, "Sources", "Parser.swift")
        result = ext.symbol_details(filepath, "configure")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0]["name"] == "mode"
        assert result["params"][0]["type"] == "ParseMode"
        assert result["params"][0]["documented"] is True
        assert result["params"][1]["name"] == "flags"
        assert result["params"][1]["type"] == "[String]"
        assert result["params"][1]["documented"] is True
        assert result["return_type"] == "Parser"
        assert result["return_documented"] is True

    def test_symbol_details_external_label(self, tmp_path):
        """External label and internal name: uses the internal name."""
        swift_file = tmp_path / "Labels.swift"
        swift_file.write_text(
            "/// - Parameter value: The value.\n"
            "public func set(for value: Int, _ name: String) -> Void {\n"
            "}\n",
            encoding="utf-8",
        )
        ext = SwiftExtractor()
        result = ext.symbol_details(str(swift_file), "set")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0]["name"] == "value"
        assert result["params"][0]["type"] == "Int"
        assert result["params"][0]["documented"] is True
        assert result["params"][1]["name"] == "name"
        assert result["params"][1]["type"] == "String"
        assert result["params"][1]["documented"] is False

    def test_symbol_details_dotted_type_method(self, tmp_path):
        """Dotted name resolves a method within a type declaration."""
        swift_file = tmp_path / "Router.swift"
        swift_file.write_text(
            "/// A network router.\n"
            "class Router {\n"
            "    /// Handle an incoming request.\n"
            "    ///\n"
            "    /// - Parameter request: The URL request to handle.\n"
            "    /// - Returns: The response for this request.\n"
            "    func handle(request: URLRequest) -> Response {\n"
            "        return Response()\n"
            "    }\n"
            "\n"
            "    func other() {}\n"
            "}\n",
            encoding="utf-8",
        )
        ext = SwiftExtractor()
        result = ext.symbol_details(str(swift_file), "Router.handle")
        assert result is not None
        assert len(result["params"]) == 1
        assert result["params"][0]["name"] == "request"
        assert result["params"][0]["type"] == "URLRequest"
        assert result["params"][0]["documented"] is True
        assert result["return_type"] == "Response"
        assert result["return_documented"] is True
