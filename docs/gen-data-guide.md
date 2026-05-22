---
title: Data Generation
description: "How to use selfdoc's gen-data command to run sandboxed scripts at build time, producing validated JSON or CSV data files for your documentation."
nav_group: "Guides"
nav_order: 17
---

# Data Generation

selfdoc can run scripts at build time to generate data files that your documentation pages reference. Scripts run inside a bubblewrap (bwrap) sandbox for isolation -- they get read-only access to specific directories and can only write to the output directory.

## When to Use This

Data generation is useful when your docs need to include information that comes from running code: benchmark results, schema dumps, configuration inventories, API endpoint listings, or anything else that would go stale if hardcoded in Markdown.

Instead of manually updating a table every release, write a script that produces the data and let `selfdoc gen-data` run it.

## Configuration

Add a `gen_data` section to your `selfdoc.json` with a `scripts` array. Each script needs three fields:

```json
{
  "gen_data": {
    "scripts": [
      {
        "command": "python3 scripts/dump_config_schema.py",
        "output": "config-schema.json",
        "mounts": ["mypackage/", "scripts/"]
      }
    ]
  }
}
```

| Field | Description |
| --- | --- |
| `command` | The shell command to run inside the sandbox |
| `output` | Filename written to `.selfdoc/data/` (must be JSON or CSV) |
| `mounts` | List of directories to mount read-only inside the sandbox |

All three fields are required for each script declaration.

## How the Sandbox Works

selfdoc uses [bubblewrap](https://github.com/containers/bubblewrap) (`bwrap`) on Linux to create a minimal sandbox for each script:

- **Read-only mounts**: directories listed in `mounts` are mounted read-only. The script can read your source code but cannot modify it.
- **System binaries**: `/usr`, `/lib`, `/bin`, and similar system paths are mounted read-only so the script can use standard tools (Python, bash, etc.).
- **Write access**: only the `.selfdoc/data/` output directory is writable.
- **No network**: `--unshare-all` isolates the process from the network and other namespaces.
- **Clean environment**: `--clearenv` starts with no environment variables.
- **Timeout**: scripts are killed after 60 seconds.

This means a misbehaving script cannot modify your source code, exfiltrate data over the network, or hang your build indefinitely.

## Output Validation

After a script finishes, selfdoc validates its output file:

- **JSON files** (`.json`) must parse as valid JSON
- **CSV files** (`.csv`) must parse as valid CSV

If validation fails, `selfdoc gen-data` reports the error and stops. This catches scripts that produce malformed output before it reaches your documentation.

Output files are written to `.selfdoc/data/`. Your documentation pages can then reference this data via custom directives or by reading the files at build time.

## Running It

Run data generation before building:

```bash
selfdoc gen-data
selfdoc build
```

Or just run `selfdoc build` -- if you have `gen_data` configured, the build pipeline handles it.

## Requirements

Bubblewrap must be installed on your system:

```bash
# Fedora
sudo dnf install bubblewrap

# Debian / Ubuntu
sudo apt install bubblewrap
```

If `bwrap` is not found, `selfdoc gen-data` exits with a clear error message and installation instructions. This feature is Linux-only since bwrap relies on Linux namespaces.

> [!NOTE]
> Scripts run with `--clearenv`, so they cannot access environment variables. If your script needs configuration, pass it via command-line arguments or read it from a mounted config file.

Next: [Staleness Detection](staleness/) -->
