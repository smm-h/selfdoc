"""Tests for the Zig source extractor (selfdoc.extractors.zig)."""

import os

import pytest

from selfdoc.extractors.zig import ZigExtractor


@pytest.fixture()
def zig_project(tmp_path):
    """Create a sample Zig project structure for testing."""
    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir)

    # Main source file with module doc, pub declarations, doc comments
    main_zig = os.path.join(src_dir, "audio.zig")
    with open(main_zig, "w", encoding="utf-8") as f:
        f.write("""\
//! Audio system: 16-channel mixing, sound cache, music playback.
//! Self-contained SDL3 audio module.

const std = @import("std");

pub const NUM_CHANNELS = 16;
pub const MUSIC_CHANNEL = 0;

const AudioChannel = struct {
    stream: ?*anyopaque = null,
    is_playing: bool = false,
};

var g_audio_device: u32 = 0;

/// Open the audio device and create streams for all channels.
/// Call once after SDL_Init.
pub fn init() void {}

/// Destroy all streams, close the audio device, free music data.
pub fn deinit() void {}

/// Add a pre-synthesized PCM buffer to the sound cache.
/// Returns true on success, false if the cache is full.
pub fn cacheSoundEntry(name: []const u8, data: []f32) bool {
    _ = name;
    _ = data;
    return false;
}

pub fn lookupSoundCache(name: []const u8) ?[]f32 {
    _ = name;
    return null;
}

pub var sound_cache_count: usize = 0;

fn privateHelper() void {}
""")

    # Struct-heavy file for table-schema tests
    types_zig = os.path.join(src_dir, "types.zig")
    with open(types_zig, "w", encoding="utf-8") as f:
        f.write("""\
//! Type definitions for the persistence layer.

const std = @import("std");

/// Queue entry for the persistence ring buffer.
pub const QueueEntry = struct {
    /// Type of database operation.
    entry_type: u8 = 0,
    session_id_len: usize = 0,
    player_id_len: usize = 0,
    /// JSON payload for the operation.
    payload_len: usize = 0,
    sequence_num: u64 = 0,
};

/// Configuration for the writer thread.
pub const WriterConfig = struct {
    conninfo: []const u8,
    batch_size: u32 = 64,
    backoff_ms: u64 = 100,
    max_backoff_ms: u64 = 30000,
};
""")

    # File with test blocks
    test_zig = os.path.join(src_dir, "math.zig")
    with open(test_zig, "w", encoding="utf-8") as f:
        f.write("""\
const std = @import("std");

pub fn add(a: u32, b: u32) u32 {
    return a + b;
}

pub fn multiply(a: u32, b: u32) u32 {
    return a * b;
}

test "add works" {
    try std.testing.expectEqual(@as(u32, 5), add(2, 3));
}

test "multiply works" {
    try std.testing.expectEqual(@as(u32, 6), multiply(2, 3));
}
""")

    # build.zig marker
    build_zig = os.path.join(tmp_path, "build.zig")
    with open(build_zig, "w", encoding="utf-8") as f:
        f.write("const std = @import(\"std\");\n")

    return tmp_path


class TestRef:
    def test_ref_extracts_module_doc_and_declarations(self, zig_project):
        ext = ZigExtractor()
        result = ext.extract(
            "ref",
            {"path": "src/audio.zig"},
            [],
            [],
            str(zig_project),
        )
        # Module doc should be present
        assert "Audio system: 16-channel mixing" in result
        assert "Self-contained SDL3 audio module" in result
        # Pub declarations should be present
        assert "### `NUM_CHANNELS`" in result
        assert "### `MUSIC_CHANNEL`" in result
        assert "### `init`" in result
        assert "### `deinit`" in result
        assert "### `cacheSoundEntry`" in result
        assert "### `lookupSoundCache`" in result
        assert "### `sound_cache_count`" in result
        # Private declarations should NOT be present
        assert "privateHelper" not in result
        assert "AudioChannel" not in result
        assert "g_audio_device" not in result

    def test_ref_no_arg_errors(self):
        ext = ZigExtractor()
        result = ext.extract("ref", {"path": ""}, [], [], "/tmp")
        assert "selfdoc:" in result
        assert "requires" in result

    def test_ref_file_not_found_errors(self, tmp_path):
        ext = ZigExtractor()
        result = ext.extract(
            "ref",
            {"path": "nonexistent.zig"},
            [],
            [],
            str(tmp_path),
        )
        assert "selfdoc:" in result
        assert "not found" in result

    def test_ref_with_target(self, tmp_path):
        """ref directive with target renders only the specified symbol."""
        zig_file = tmp_path / "core.zig"
        zig_file.write_text(
            "/// Initializes the system.\n"
            "pub fn init() void {}\n\n"
            "/// Shuts down the system.\n"
            "pub fn deinit() void {}\n",
            encoding="utf-8",
        )
        result = ZigExtractor().extract(
            "ref",
            {"path": "core.zig", "target": "deinit"},
            [],
            [],
            str(tmp_path),
        )
        assert "### `deinit`" in result
        assert "Shuts down" in result
        assert "init" not in result.split("deinit")[0]  # "init" shouldn't appear before "deinit"

    def test_ref_with_target_not_found(self, tmp_path):
        zig_file = tmp_path / "core.zig"
        zig_file.write_text("pub fn init() void {}\n", encoding="utf-8")
        result = ZigExtractor().extract(
            "ref",
            {"path": "core.zig", "target": "nonexistent"},
            [],
            [],
            str(tmp_path),
        )
        assert "not found" in result


class TestProseDesc:
    def test_prose_desc_extracts_module_doc_only(self, zig_project):
        ext = ZigExtractor()
        result = ext.extract(
            "prose-desc",
            {"path": "src/audio.zig"},
            [],
            [],
            str(zig_project),
        )
        # Module doc should be present
        assert "Audio system" in result
        assert "Self-contained SDL3 audio module" in result
        # Declarations should NOT be present
        assert "### `init`" not in result
        assert "pub fn" not in result

    def test_prose_desc_no_module_doc(self, zig_project):
        ext = ZigExtractor()
        result = ext.extract(
            "prose-desc",
            {"path": "src/math.zig"},
            [],
            [],
            str(zig_project),
        )
        assert "selfdoc:" in result
        assert "no module doc" in result


class TestTableSchema:
    def test_table_schema_extracts_struct_fields(self, zig_project):
        ext = ZigExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "src/types.zig", "target": "QueueEntry"},
            [],
            [],
            str(zig_project),
        )
        assert "| Field | Type | Default | Description |" in result
        assert "`entry_type`" in result
        assert "`u8`" in result
        assert "`0`" in result
        assert "Type of database operation" in result
        assert "`session_id_len`" in result
        assert "`sequence_num`" in result
        assert "`u64`" in result

    def test_table_schema_all_structs(self, zig_project):
        ext = ZigExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "src/types.zig"},
            [],
            [],
            str(zig_project),
        )
        assert "### `QueueEntry`" in result
        assert "### `WriterConfig`" in result
        assert "`batch_size`" in result
        assert "`conninfo`" in result

    def test_table_schema_struct_not_found(self, zig_project):
        ext = ZigExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "src/types.zig", "target": "NonExistent"},
            [],
            [],
            str(zig_project),
        )
        assert "selfdoc:" in result
        assert "not found" in result


class TestCodeTest:
    def test_code_test_extracts_test_blocks(self, zig_project):
        ext = ZigExtractor()
        result = ext.extract(
            "code-test",
            {"path": "src/math.zig"},
            [],
            [],
            str(zig_project),
        )
        assert "```zig" in result
        assert 'test "add works"' in result
        assert 'test "multiply works"' in result

    def test_code_test_specific_block(self, zig_project):
        ext = ZigExtractor()
        result = ext.extract(
            "code-test",
            {"path": "src/math.zig", "target": "add works"},
            [],
            [],
            str(zig_project),
        )
        assert "```zig" in result
        assert 'test "add works"' in result
        assert 'test "multiply works"' not in result

    def test_code_test_not_found(self, zig_project):
        ext = ZigExtractor()
        result = ext.extract(
            "code-test",
            {"path": "src/math.zig", "target": "nonexistent test"},
            [],
            [],
            str(zig_project),
        )
        assert "selfdoc:" in result
        assert "not found" in result


class TestDocComments:
    def test_doc_comments_attached_to_declarations(self, zig_project):
        ext = ZigExtractor()
        result = ext.extract(
            "ref",
            {"path": "src/audio.zig"},
            [],
            [],
            str(zig_project),
        )
        # Doc comments should be rendered as prose
        assert "Open the audio device" in result
        assert "Destroy all streams" in result
        assert "Add a pre-synthesized PCM buffer" in result

    def test_doc_comments_on_struct_fields(self, zig_project):
        ext = ZigExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "src/types.zig", "target": "QueueEntry"},
            [],
            [],
            str(zig_project),
        )
        assert "Type of database operation" in result
        assert "JSON payload for the operation" in result


class TestDetection:
    def test_zig_detection(self, zig_project):
        ext = ZigExtractor()
        assert ext.detect(str(zig_project)) is True

    def test_zig_detection_build_zig_zon(self, tmp_path):
        (tmp_path / "build.zig.zon").touch()
        ext = ZigExtractor()
        assert ext.detect(str(tmp_path)) is True

    def test_zig_no_detection(self, tmp_path):
        ext = ZigExtractor()
        assert ext.detect(str(tmp_path)) is False


class TestResolvePath:
    def test_resolve_zig_file(self, zig_project):
        ext = ZigExtractor()
        result = ext.resolve_path("src/audio.zig", [], str(zig_project))
        assert result is not None
        assert result.endswith("audio.zig")

    def test_resolve_zig_directory(self, zig_project):
        ext = ZigExtractor()
        result = ext.resolve_path("src", [], str(zig_project))
        assert result is not None
        assert result.endswith("src")

    def test_resolve_zig_with_source_paths(self, zig_project):
        ext = ZigExtractor()
        result = ext.resolve_path("audio.zig", ["src/"], str(zig_project))
        assert result is not None
        assert result.endswith("audio.zig")

    def test_resolve_zig_not_found(self, zig_project):
        ext = ZigExtractor()
        result = ext.resolve_path("nonexistent.zig", [], str(zig_project))
        assert result is None

    def test_resolve_zig_implicit_extension(self, zig_project):
        ext = ZigExtractor()
        result = ext.resolve_path("src/audio", [], str(zig_project))
        assert result is not None
        assert result.endswith("audio.zig")


class TestUnknownDirective:
    def test_unknown_directive_errors(self):
        ext = ZigExtractor()
        result = ext.extract(
            "code-help",
            {"path": "test.zig"},
            [],
            [],
            "/tmp",
        )
        assert "selfdoc:" in result
        assert "unknown directive" in result


class TestErrorSet:
    def test_error_set_detected_as_const(self, tmp_path):
        zig_file = tmp_path / "errors.zig"
        zig_file.write_text(
            "pub const FileError = error {\n"
            "    NotFound,\n"
            "    AccessDenied,\n"
            "};\n",
            encoding="utf-8",
        )
        symbols = ZigExtractor().public_symbols(str(zig_file))
        assert symbols == ["FileError"]


class TestTaggedEnum:
    def test_tagged_enum_detected_as_const(self, tmp_path):
        zig_file = tmp_path / "tagged.zig"
        zig_file.write_text(
            "pub const EntryType = enum(u8) {\n"
            "    session_create,\n"
            "    action,\n"
            "    snapshot,\n"
            "};\n",
            encoding="utf-8",
        )
        symbols = ZigExtractor().public_symbols(str(zig_file))
        assert symbols == ["EntryType"]


class TestModuleDocstring:
    def test_module_docstring(self, tmp_path):
        zig_file = tmp_path / "mod.zig"
        zig_file.write_text(
            "//! Audio system for mixing.\n"
            "//! Supports 16 channels.\n"
            "\n"
            "const std = @import(\"std\");\n",
            encoding="utf-8",
        )
        ext = ZigExtractor()
        result = ext.module_docstring(str(zig_file))
        assert result == "Audio system for mixing.\nSupports 16 channels."


class TestSymbolDetails:
    def test_symbol_details_with_params(self, tmp_path):
        zig_file = tmp_path / "audio.zig"
        zig_file.write_text(
            "/// Initialize the audio system with the given config.\n"
            "/// The sample_rate controls audio quality.\n"
            "/// Returns an error if the device cannot be opened.\n"
            "pub fn init(sample_rate: u32, channels: u8) !void {\n"
            "    // ...\n"
            "}\n",
            encoding="utf-8",
        )
        ext = ZigExtractor()
        result = ext.symbol_details(str(zig_file), "init")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0]["name"] == "sample_rate"
        assert result["params"][0]["type"] == "u32"
        assert result["params"][0]["documented"] is True
        assert result["params"][1]["name"] == "channels"
        assert result["params"][1]["type"] == "u8"
        assert result["params"][1]["documented"] is False
        assert result["return_type"] == "!void"
        assert result["return_documented"] is True

    def test_symbol_details_comptime(self, tmp_path):
        zig_file = tmp_path / "container.zig"
        zig_file.write_text(
            "/// Generic container type.\n"
            "/// The type T determines element storage.\n"
            "pub fn Container(comptime T: type, allocator: std.mem.Allocator) !*Self {\n"
            "    // ...\n"
            "}\n",
            encoding="utf-8",
        )
        ext = ZigExtractor()
        result = ext.symbol_details(str(zig_file), "Container")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0]["name"] == "T"
        assert result["params"][0]["type"] == "type"
        assert result["params"][0]["documented"] is True
        assert result["params"][1]["name"] == "allocator"
        assert result["params"][1]["type"] == "std.mem.Allocator"
        assert result["params"][1]["documented"] is False
        assert result["return_type"] == "!*Self"
        assert result["return_documented"] is False

    def test_symbol_details_error_union_return(self, tmp_path):
        zig_file = tmp_path / "stream.zig"
        zig_file.write_text(
            "/// Read bytes from the stream.\n"
            "/// Returns the number of bytes actually read.\n"
            "pub fn read(buffer: []u8, flags: u32) anyerror!usize {\n"
            "    return 0;\n"
            "}\n",
            encoding="utf-8",
        )
        ext = ZigExtractor()
        result = ext.symbol_details(str(zig_file), "read")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["return_type"] == "anyerror!usize"
        assert result["return_documented"] is True

    def test_symbol_details_unknown(self, tmp_path):
        zig_file = tmp_path / "simple.zig"
        zig_file.write_text(
            "pub fn exists(x: u32) u32 {\n"
            "    return x;\n"
            "}\n",
            encoding="utf-8",
        )
        ext = ZigExtractor()
        result = ext.symbol_details(str(zig_file), "nonexistent")
        assert result is None

    def test_symbol_details_no_doc(self, tmp_path):
        zig_file = tmp_path / "nodoc.zig"
        zig_file.write_text(
            "pub fn noDoc(x: u32, y: u32) u32 {\n"
            "    return x + y;\n"
            "}\n",
            encoding="utf-8",
        )
        ext = ZigExtractor()
        result = ext.symbol_details(str(zig_file), "noDoc")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0]["name"] == "x"
        assert result["params"][0]["type"] == "u32"
        assert result["params"][0]["documented"] is False
        assert result["params"][1]["name"] == "y"
        assert result["params"][1]["type"] == "u32"
        assert result["params"][1]["documented"] is False
        assert result["return_type"] == "u32"
        assert result["return_documented"] is False

    def test_symbol_details_dotted_struct_method(self, tmp_path):
        zig_file = tmp_path / "config.zig"
        zig_file.write_text(
            "const std = @import(\"std\");\n"
            "\n"
            "pub const Config = struct {\n"
            "    width: u32 = 800,\n"
            "    height: u32 = 600,\n"
            "\n"
            "    /// Initialize config with default values.\n"
            "    /// Returns a new Config instance.\n"
            "    pub fn init(self: *Config, allocator: std.mem.Allocator) !void {\n"
            "        _ = self;\n"
            "        _ = allocator;\n"
            "    }\n"
            "\n"
            "    pub fn deinit(self: *Config) void {\n"
            "        _ = self;\n"
            "    }\n"
            "};\n",
            encoding="utf-8",
        )
        ext = ZigExtractor()
        result = ext.symbol_details(str(zig_file), "Config.init")
        assert result is not None
        # self is skipped by _parse_zig_params
        assert len(result["params"]) == 1
        assert result["params"][0]["name"] == "allocator"
        assert result["params"][0]["type"] == "std.mem.Allocator"
        assert result["return_type"] == "!void"
        assert result["return_documented"] is True

    def test_symbol_details_dotted_not_found(self, tmp_path):
        zig_file = tmp_path / "config2.zig"
        zig_file.write_text(
            "pub const Config = struct {\n"
            "    pub fn init(self: *Config) void {\n"
            "        _ = self;\n"
            "    }\n"
            "};\n",
            encoding="utf-8",
        )
        ext = ZigExtractor()
        # Member not found
        result = ext.symbol_details(str(zig_file), "Config.nonexistent")
        assert result is None
        # Type not found
        result = ext.symbol_details(str(zig_file), "Other.init")
        assert result is None

    def test_symbol_details_dotted_enum_method(self, tmp_path):
        zig_file = tmp_path / "state.zig"
        zig_file.write_text(
            "pub const State = enum(u8) {\n"
            "    idle,\n"
            "    running,\n"
            "    stopped,\n"
            "\n"
            "    pub fn isActive(self: State) bool {\n"
            "        return self == .running;\n"
            "    }\n"
            "};\n",
            encoding="utf-8",
        )
        ext = ZigExtractor()
        result = ext.symbol_details(str(zig_file), "State.isActive")
        assert result is not None
        assert len(result["params"]) == 0  # self is skipped
        assert result["return_type"] == "bool"

    def test_symbol_details_anytype(self, tmp_path):
        zig_file = tmp_path / "generic.zig"
        zig_file.write_text(
            "pub fn print(value: anytype) void {\n"
            "    _ = value;\n"
            "}\n",
            encoding="utf-8",
        )
        ext = ZigExtractor()
        result = ext.symbol_details(str(zig_file), "print")
        assert result is not None
        assert len(result["params"]) == 1
        assert result["params"][0]["name"] == "value"
        assert result["params"][0]["type"] == "anytype"
        assert result["params"][0]["documented"] is False
