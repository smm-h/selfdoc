package build

import (
	"bytes"
	"compress/gzip"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/andybalholm/brotli"
	"github.com/smm-h/selfdoc/internal/effects"
)

// compressibleExtensions are the file kinds a compressed companion is written
// for. Everything else in the output tree is already compressed, or is not
// text.
var compressibleExtensions = map[string]bool{
	".html": true, ".css": true, ".js": true, ".json": true,
	".xml": true, ".txt": true, ".svg": true,
}

// CompressOutput writes a gzip and a brotli companion beside every
// compressible file under outputDir, and returns how many files it compressed
// and whether brotli was available.
//
// brotli is compiled into this binary, so the second return value is always
// true -- it stays in the signature because the caller prints a different line
// for each case and the Python it replaces really could be installed without
// it.
//
// The tree is walked in sorted order, so a preview names the companions in the
// same order on every run.
func CompressOutput(outputDir string, h *effects.Handle) (count int, hasBrotli bool, err error) {
	paths, err := compressibleFiles(outputDir)
	if err != nil {
		return 0, true, err
	}
	for _, path := range paths {
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			return count, true, readErr
		}

		var gzipped bytes.Buffer
		writer, levelErr := gzip.NewWriterLevel(&gzipped, gzip.BestCompression)
		if levelErr != nil {
			return count, true, levelErr
		}
		if _, writeErr := writer.Write(data); writeErr != nil {
			return count, true, writeErr
		}
		if closeErr := writer.Close(); closeErr != nil {
			return count, true, closeErr
		}
		if writeErr := h.Write(path+".gz", gzipped.Bytes(), effects.ModeDefault); writeErr != nil {
			return count, true, writeErr
		}

		var brotlied bytes.Buffer
		brotliWriter := brotli.NewWriter(&brotlied)
		if _, writeErr := brotliWriter.Write(data); writeErr != nil {
			return count, true, writeErr
		}
		if closeErr := brotliWriter.Close(); closeErr != nil {
			return count, true, closeErr
		}
		if writeErr := h.Write(path+".br", brotlied.Bytes(), effects.ModeDefault); writeErr != nil {
			return count, true, writeErr
		}

		count++
	}
	return count, true, nil
}

// compressibleFiles lists every compressible file under root, sorted.
func compressibleFiles(root string) ([]string, error) {
	var paths []string
	err := filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			return nil
		}
		if !compressibleExtensions[strings.ToLower(filepath.Ext(path))] {
			return nil
		}
		paths = append(paths, path)
		return nil
	})
	if err != nil {
		return nil, err
	}
	sort.Strings(paths)
	return paths, nil
}
