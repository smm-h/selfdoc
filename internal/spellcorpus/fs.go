package spellcorpus

import "os"

// isDir reports whether path is an existing directory, the question Python's
// os.path.isdir answers.
func isDir(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}
