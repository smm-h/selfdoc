"""Tests for the Kotlin source extractor (selfdoc.extractors.kotlin)."""

import os

import pytest

from selfdoc.extractors.kotlin import KotlinExtractor, _parse_kdoc


@pytest.fixture()
def kotlin_project(tmp_path):
    """Create a sample Kotlin project structure for testing."""
    sources_dir = os.path.join(tmp_path, "src", "main", "kotlin")
    os.makedirs(sources_dir)

    # Main source file with module doc, public declarations, KDoc comments
    parser_kt = os.path.join(sources_dir, "Parser.kt")
    with open(parser_kt, "w", encoding="utf-8") as f:
        f.write("""\
/**
 * Parser module: handles source code parsing and AST construction.
 * Supports incremental parsing and error recovery.
 */

package com.example.parser

import java.io.File

/**
 * A source code parser with incremental support.
 *
 * Use [Parser] to parse source files into an AST.
 * @param source The source code to parse.
 * @return The parsed AST root node.
 * @constructor Creates a new parser instance.
 */
class Parser(val source: String) {
    fun parse(): ASTNode {
        return ASTNode()
    }
}

/** An AST node. */
data class ASTNode(val type: String = "root", val children: List<ASTNode> = emptyList())

sealed class ParseResult {
    data class Success(val node: ASTNode) : ParseResult()
    data class Error(val message: String) : ParseResult()
}

object ParserFactory {
    fun create(): Parser = Parser("")
}

data object EmptyNode

interface Parseable {
    fun parse(): ASTNode
}

enum class TokenType {
    IDENTIFIER,
    KEYWORD,
    LITERAL
}

/**
 * Parse the given source text into an AST.
 *
 * @param source The source code to parse.
 * @param mode The parsing mode.
 * @return The parsed AST root node.
 * @throws ParseException if the source is malformed.
 */
fun parseSource(source: String, mode: String = "default"): ASTNode {
    return ASTNode()
}

val maxParseDepth: Int = 256

var parserVersion: String = "1.0"

typealias ParseCallback = (ASTNode) -> Unit

private class InternalHelper {
    fun help() {}
}

internal fun internalSetup() {}

protected val protectedValue: Int = 42

@PublishedApi
internal fun publishedApiHelper(): String = "public"
""")

    # File for blank-line association test
    blankline_kt = os.path.join(sources_dir, "BlankLine.kt")
    with open(blankline_kt, "w", encoding="utf-8") as f:
        f.write("""\
/** This comment is for the function below. */
fun attached() {}

/** This comment is NOT for the function below. */

fun detached() {}
""")

    # Data class file for table-schema tests
    config_kt = os.path.join(sources_dir, "Config.kt")
    with open(config_kt, "w", encoding="utf-8") as f:
        f.write("""\
/**
 * Configuration for the parser system.
 *
 * @property bufferSize The maximum number of tokens to buffer.
 * @property strictMode Whether to enable strict mode.
 * @property outputFormat The output format for results.
 */
data class ParserConfig(
    val bufferSize: Int = 1024,
    val strictMode: Boolean = false,
    val outputFormat: String = "json"
)

data class NetworkConfig(
    val host: String = "localhost",
    val port: Int = 8080,
    val timeout: Double = 30.0
)
""")

    # build.gradle.kts marker file
    build_gradle = os.path.join(tmp_path, "build.gradle.kts")
    with open(build_gradle, "w", encoding="utf-8") as f:
        f.write("plugins { kotlin(\"jvm\") }\n")

    return tmp_path


class TestDetection:
    def test_detect_with_build_gradle_kts(self, kotlin_project):
        ext = KotlinExtractor()
        assert ext.detect(str(kotlin_project)) is True

    def test_detect_with_build_gradle(self, tmp_path):
        build_gradle = os.path.join(tmp_path, "build.gradle")
        with open(build_gradle, "w", encoding="utf-8") as f:
            f.write("apply plugin: 'kotlin'\n")
        ext = KotlinExtractor()
        assert ext.detect(str(tmp_path)) is True

    def test_detect_without_build_files(self, tmp_path):
        ext = KotlinExtractor()
        assert ext.detect(str(tmp_path)) is False


class TestFileExtensions:
    def test_file_extensions(self):
        ext = KotlinExtractor()
        assert ext.file_extensions() == [".kt"]


class TestPublicSymbols:
    def test_public_symbols_class(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "Parser" in symbols

    def test_public_symbols_data_class(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "ASTNode" in symbols

    def test_public_symbols_sealed_class(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "ParseResult" in symbols

    def test_public_symbols_object(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "ParserFactory" in symbols

    def test_public_symbols_data_object(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "EmptyNode" in symbols

    def test_public_symbols_interface(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "Parseable" in symbols

    def test_public_symbols_enum_class(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "TokenType" in symbols

    def test_public_symbols_fun(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "parseSource" in symbols

    def test_public_symbols_val_var(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "maxParseDepth" in symbols
        assert "parserVersion" in symbols

    def test_public_symbols_typealias(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "ParseCallback" in symbols

    def test_public_symbols_excludes_private(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "InternalHelper" not in symbols

    def test_public_symbols_excludes_internal(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "internalSetup" not in symbols

    def test_public_symbols_excludes_protected(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "protectedValue" not in symbols

    def test_public_symbols_includes_published_api(self, kotlin_project):
        ext = KotlinExtractor()
        filepath = os.path.join(
            kotlin_project, "src", "main", "kotlin", "Parser.kt"
        )
        symbols = ext.public_symbols(filepath)
        assert "publishedApiHelper" in symbols


class TestKDocParsing:
    def test_kdoc_basic(self):
        result = _parse_kdoc("A simple doc comment.")
        assert "A simple doc comment." in result

    def test_kdoc_param(self):
        text = "@param source The source code to parse."
        result = _parse_kdoc(text)
        assert "**Parameters:**" in result
        assert "`source`" in result
        assert "The source code to parse." in result

    def test_kdoc_param_bracket(self):
        text = "@param[source] The source code to parse."
        result = _parse_kdoc(text)
        assert "**Parameters:**" in result
        assert "`source`" in result
        assert "The source code to parse." in result

    def test_kdoc_return(self):
        text = "@return The parsed AST root node."
        result = _parse_kdoc(text)
        assert "**Returns:** The parsed AST root node." in result

    def test_kdoc_throws(self):
        text = "@throws ParseException if the source is malformed."
        result = _parse_kdoc(text)
        assert "**Throws:**" in result
        assert "`ParseException`" in result
        assert "if the source is malformed." in result

    def test_kdoc_exception_alias(self):
        text = "@exception IOException if the file cannot be read."
        result = _parse_kdoc(text)
        assert "**Throws:**" in result
        assert "`IOException`" in result

    def test_kdoc_property(self):
        text = "@property name The name of the entity."
        result = _parse_kdoc(text)
        assert "**Properties:**" in result
        assert "`name`" in result
        assert "The name of the entity." in result

    def test_kdoc_constructor(self):
        text = "@constructor Creates a new parser instance."
        result = _parse_kdoc(text)
        assert "**Constructor:** Creates a new parser instance." in result

    def test_kdoc_receiver(self):
        text = "@receiver The string to parse."
        result = _parse_kdoc(text)
        assert "**Receiver:** The string to parse." in result

    def test_kdoc_sample(self):
        text = "@sample com.example.parser.ParserTest.testParse"
        result = _parse_kdoc(text)
        assert "**Sample:**" in result
        assert "`com.example.parser.ParserTest.testParse`" in result

    def test_kdoc_see(self):
        text = "@see Parser"
        result = _parse_kdoc(text)
        assert "**See:**" in result
        assert "`Parser`" in result

    def test_kdoc_author_since(self):
        text = "@author Jane Doe\n@since 1.0"
        result = _parse_kdoc(text)
        assert "**Author:** Jane Doe" in result
        assert "**Since:** 1.0" in result

    def test_kdoc_suppress_ignored(self):
        text = "Some text.\n@suppress\nMore text."
        result = _parse_kdoc(text)
        assert "Some text." in result
        assert "@suppress" not in result

    def test_kdoc_square_bracket_link(self):
        text = "Use [Parser] to parse files."
        result = _parse_kdoc(text)
        assert "`Parser`" in result
        assert "[Parser]" not in result

    def test_kdoc_labeled_link(self):
        text = "See [the parser][Parser] for details."
        result = _parse_kdoc(text)
        assert "the parser (`Parser`)" in result
        assert "[the parser][Parser]" not in result


class TestBlankLineAssociation:
    def test_no_association_across_blank_lines(self, kotlin_project):
        ext = KotlinExtractor()
        result = ext.extract(
            "ref",
            {"path": "src/main/kotlin/BlankLine.kt"},
            [],
            [],
            str(kotlin_project),
        )
        # "attached" should have the doc comment
        assert "This comment is for the function below" in result
        # "detached" should NOT have its doc comment because of the blank line
        assert "This comment is NOT for the function below" not in result


class TestRef:
    def test_ref_handler(self, kotlin_project):
        ext = KotlinExtractor()
        result = ext.extract(
            "ref",
            {"path": "src/main/kotlin/Parser.kt"},
            [],
            [],
            str(kotlin_project),
        )
        # Module doc should be present
        assert "Parser module: handles source code parsing" in result
        assert "Supports incremental parsing and error recovery" in result

        # ## heading for the file
        assert "## src/main/kotlin/Parser.kt" in result

        # ### headings for public symbols
        assert "### Parser" in result
        assert "### ASTNode" in result
        assert "### ParseResult" in result
        assert "### ParserFactory" in result
        assert "### EmptyNode" in result
        assert "### Parseable" in result
        assert "### TokenType" in result
        assert "### parseSource" in result
        assert "### maxParseDepth" in result
        assert "### parserVersion" in result
        assert "### ParseCallback" in result
        assert "### publishedApiHelper" in result

        # Code blocks with kotlin syntax
        assert "```kotlin" in result

        # Doc comment text should appear
        assert "A source code parser with incremental support" in result
        assert "Parse the given source text into an AST" in result

        # Private/internal/protected should NOT appear
        assert "InternalHelper" not in result
        assert "internalSetup" not in result
        assert "protectedValue" not in result


class TestProseDesc:
    def test_prose_desc_handler(self, kotlin_project):
        ext = KotlinExtractor()
        result = ext.extract(
            "prose-desc",
            {"path": "src/main/kotlin/Parser.kt"},
            [],
            [],
            str(kotlin_project),
        )
        # Module-level doc comment should be present
        assert "Parser module" in result
        assert "Supports incremental parsing and error recovery" in result
        # Declaration-level comments should NOT be present
        assert "### Parser" not in result
        assert "A source code parser with incremental support" not in result


class TestTableSchema:
    def test_table_schema_data_class(self, kotlin_project):
        ext = KotlinExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "src/main/kotlin/Config.kt", "target": "ParserConfig"},
            [],
            [],
            str(kotlin_project),
        )
        # Should produce a markdown table
        assert "| Field | Type | Default | Description |" in result
        # All fields should appear with correct types and defaults
        assert "`bufferSize`" in result
        assert "`Int`" in result
        assert "`1024`" in result
        assert "The maximum number of tokens to buffer" in result
        assert "`strictMode`" in result
        assert "`Boolean`" in result
        assert "`false`" in result
        assert "`outputFormat`" in result
        assert "`String`" in result

    def test_table_schema_specific_class(self, kotlin_project):
        ext = KotlinExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "src/main/kotlin/Config.kt", "target": "NetworkConfig"},
            [],
            [],
            str(kotlin_project),
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


class TestRegistry:
    def test_registry_includes_kotlin(self):
        from selfdoc.extractors import EXTRACTORS

        assert "kotlin" in EXTRACTORS

    def test_detection_order_includes_kotlin(self):
        from selfdoc.extractors import _DETECTION_ORDER

        names = [ext.name for ext in _DETECTION_ORDER]
        assert "kotlin" in names


class TestUnknownDirective:
    def test_unknown_directive_errors(self):
        ext = KotlinExtractor()
        result = ext.extract(
            "code-help",
            {"path": "test.kt"},
            [],
            [],
            "/tmp",
        )
        assert "selfdoc:" in result
        assert "unknown directive" in result


class TestResolvePath:
    def test_resolve_kotlin_file(self, kotlin_project):
        ext = KotlinExtractor()
        result = ext.resolve_path(
            "src/main/kotlin/Parser.kt", [], str(kotlin_project)
        )
        assert result is not None
        assert result.endswith("Parser.kt")

    def test_resolve_kotlin_directory(self, kotlin_project):
        ext = KotlinExtractor()
        result = ext.resolve_path(
            "src/main/kotlin", [], str(kotlin_project)
        )
        assert result is not None
        assert result.endswith("kotlin")

    def test_resolve_kotlin_with_source_paths(self, kotlin_project):
        ext = KotlinExtractor()
        result = ext.resolve_path(
            "Parser.kt", ["src/main/kotlin/"], str(kotlin_project)
        )
        assert result is not None
        assert result.endswith("Parser.kt")

    def test_resolve_kotlin_not_found(self, kotlin_project):
        ext = KotlinExtractor()
        result = ext.resolve_path(
            "nonexistent.kt", [], str(kotlin_project)
        )
        assert result is None

    def test_resolve_kotlin_implicit_extension(self, kotlin_project):
        ext = KotlinExtractor()
        result = ext.resolve_path(
            "src/main/kotlin/Parser", [], str(kotlin_project)
        )
        assert result is not None
        assert result.endswith("Parser.kt")


class TestModuleDocstring:
    def test_module_docstring(self, tmp_path):
        kt_file = tmp_path / "Mod.kt"
        kt_file.write_text(
            "/**\n"
            " * Parser module for Kotlin sources.\n"
            " * Handles incremental parsing.\n"
            " */\n"
            "\n"
            "package com.example\n",
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.module_docstring(str(kt_file))
        assert result == "Parser module for Kotlin sources.\nHandles incremental parsing."


class TestSymbolDetails:
    def test_symbol_details_function_all_documented(self, tmp_path):
        kt_file = tmp_path / "Calc.kt"
        kt_file.write_text(
            '/**\n'
            ' * Calculate the sum.\n'
            ' * @param x First number\n'
            ' * @param y Second number\n'
            ' * @return The sum\n'
            ' */\n'
            'fun calculate(x: Int, y: Double): Double {\n'
            '    return x + y\n'
            '}\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "calculate")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0] == {"name": "x", "type": "Int", "documented": True}
        assert result["params"][1] == {"name": "y", "type": "Double", "documented": True}
        assert result["return_type"] == "Double"
        assert result["return_documented"] is True

    def test_symbol_details_function_some_undocumented(self, tmp_path):
        kt_file = tmp_path / "Proc.kt"
        kt_file.write_text(
            '/**\n'
            ' * Process items.\n'
            ' * @param items The list to process\n'
            ' */\n'
            'fun process(items: List<String>, verbose: Boolean = false): Int {\n'
            '    return items.size\n'
            '}\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "process")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0] == {"name": "items", "type": "List<String>", "documented": True}
        assert result["params"][1] == {"name": "verbose", "type": "Boolean", "documented": False}
        assert result["return_type"] == "Int"
        assert result["return_documented"] is False

    def test_symbol_details_data_class(self, tmp_path):
        kt_file = tmp_path / "User.kt"
        kt_file.write_text(
            '/**\n'
            ' * A user record.\n'
            ' * @property name The user\'s name\n'
            ' * @property age The user\'s age\n'
            ' */\n'
            'data class User(val name: String, val age: Int, val email: String)\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "User")
        assert result is not None
        assert len(result["params"]) == 3
        assert result["params"][0] == {"name": "name", "type": "String", "documented": True}
        assert result["params"][1] == {"name": "age", "type": "Int", "documented": True}
        assert result["params"][2] == {"name": "email", "type": "String", "documented": False}
        assert result["return_type"] is None
        assert result["return_documented"] is True

    def test_symbol_details_no_params(self, tmp_path):
        kt_file = tmp_path / "Time.kt"
        kt_file.write_text(
            '/** Get the current timestamp. */\n'
            'fun now(): Long = System.currentTimeMillis()\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "now")
        assert result is not None
        assert result["params"] == []
        assert result["return_type"] == "Long"
        assert result["return_documented"] is False

    def test_symbol_details_unknown_returns_none(self, tmp_path):
        kt_file = tmp_path / "Any.kt"
        kt_file.write_text(
            'fun something(): Unit {}\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "nonexistent")
        assert result is None

    def test_symbol_details_dotted_class_method(self, tmp_path):
        kt_file = tmp_path / "UserService.kt"
        kt_file.write_text(
            'class UserService {\n'
            '    /**\n'
            '     * Find a user by ID.\n'
            '     * @param id The user ID\n'
            '     * @return The user, or null if not found\n'
            '     */\n'
            '    fun findUser(id: Int): User? {\n'
            '        return null\n'
            '    }\n'
            '}\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "UserService.findUser")
        assert result is not None
        assert len(result["params"]) == 1
        assert result["params"][0] == {"name": "id", "type": "Int", "documented": True}
        assert result["return_type"] == "User?"
        assert result["return_documented"] is True

    def test_symbol_details_dotted_data_class(self, tmp_path):
        kt_file = tmp_path / "Repo.kt"
        kt_file.write_text(
            'data class Repo(val name: String) {\n'
            '    fun fullName(org: String): String {\n'
            '        return "$org/$name"\n'
            '    }\n'
            '}\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "Repo.fullName")
        assert result is not None
        assert len(result["params"]) == 1
        assert result["params"][0]["name"] == "org"
        assert result["return_type"] == "String"

    def test_symbol_details_dotted_object_method(self, tmp_path):
        kt_file = tmp_path / "Factory.kt"
        kt_file.write_text(
            'object Factory {\n'
            '    fun create(name: String): Item {\n'
            '        return Item(name)\n'
            '    }\n'
            '}\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "Factory.create")
        assert result is not None
        assert len(result["params"]) == 1
        assert result["params"][0]["name"] == "name"

    def test_symbol_details_dotted_interface_method(self, tmp_path):
        kt_file = tmp_path / "Service.kt"
        kt_file.write_text(
            'interface Service {\n'
            '    fun execute(command: String): Boolean\n'
            '}\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "Service.execute")
        assert result is not None
        assert len(result["params"]) == 1
        assert result["params"][0]["name"] == "command"
        assert result["return_type"] == "Boolean"

    def test_symbol_details_dotted_sealed_class(self, tmp_path):
        kt_file = tmp_path / "Result.kt"
        kt_file.write_text(
            'sealed class Result {\n'
            '    fun describe(): String {\n'
            '        return "result"\n'
            '    }\n'
            '}\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "Result.describe")
        assert result is not None
        assert result["return_type"] == "String"

    def test_symbol_details_dotted_not_found(self, tmp_path):
        kt_file = tmp_path / "Empty.kt"
        kt_file.write_text(
            'class Empty {\n'
            '}\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "Empty.missing")
        assert result is None

    def test_symbol_details_dotted_type_not_found(self, tmp_path):
        kt_file = tmp_path / "Other.kt"
        kt_file.write_text(
            'fun standalone(): Unit {}\n',
            encoding="utf-8",
        )
        ext = KotlinExtractor()
        result = ext.symbol_details(str(kt_file), "Missing.method")
        assert result is None
