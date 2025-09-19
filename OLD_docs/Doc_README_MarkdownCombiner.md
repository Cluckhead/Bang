# Markdown Combiner - Simple Data Checker

A Python script that combines all markdown files in a workspace into a single comprehensive document.

## Features

- 🔍 **Automatic Discovery**: Finds all markdown files (`.md`, `.mdc`, `.markdown`, `.mkd`) in the workspace
- 📁 **Smart Filtering**: Excludes common directories like `node_modules`, `.git`, `.vscode`, etc.
- 📝 **Organized Output**: Creates a well-structured document with:
  - Header with generation timestamp
  - Table of contents with clickable links
  - Individual sections for each file with metadata
- 🛠️ **Flexible Options**: Configurable output file, directory exclusions, and verbosity
- 🔧 **Error Handling**: Robust file reading with encoding fallback

## Usage

### Basic Usage
```bash
python3 markdown_combiner.py
```

This will:
- Search for all markdown files in the current directory
- Exclude common directories (node_modules, .git, etc.)
- Create `combined_documentation.md` with all files combined

### Advanced Usage

```bash
# Custom output file
python3 markdown_combiner.py --output my_docs.md

# Verbose output showing file details
python3 markdown_combiner.py --verbose

# Include all directories (don't exclude node_modules, etc.)
python3 markdown_combiner.py --include-all

# Exclude additional directories
python3 markdown_combiner.py --exclude-dirs temp logs cache

# Search from specific root directory
python3 markdown_combiner.py --root ./docs

# Combine multiple options
python3 markdown_combiner.py --output combined.md --verbose --exclude-dirs temp
```

## Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Output file name (default: `combined_documentation.md`) |
| `--root` | `-r` | Root directory to search (default: current directory) |
| `--verbose` | `-v` | Show detailed output including file sizes |
| `--include-all` | | Include all directories (don't exclude common ones) |
| `--exclude-dirs` | | Additional directories to exclude (space-separated) |

## Default Excluded Directories

The script automatically excludes these common directories:
- `node_modules` - Node.js packages
- `.git` - Git repository files
- `.vscode`, `.cursor` - Editor configuration
- `__pycache__`, `.pytest_cache`, `.mypy_cache` - Python cache
- `venv`, `.env`, `env` - Python virtual environments
- `.next`, `.nuxt` - JavaScript framework build outputs
- `dist`, `build`, `.output` - Build artifacts
- `.cache` - General cache directories

## Output Format

The generated document includes:

1. **Header**: Generation timestamp and file count
2. **Table of Contents**: Clickable links to each section
3. **Individual Sections**: Each markdown file as a separate section with:
   - File name as heading
   - File path and size metadata
   - Complete file content

## Example Output Structure

```markdown
# Combined Documentation
Generated on: 2024-01-15 10:30:45
Total files combined: 9

# Table of Contents
1. [README.md](#readmemd) - `./README.md`
2. [docs/api.md](#apimd) - `./docs/api.md`
...

---

## README.md
**File Path:** `./README.md`
**Size:** 1234 bytes

[Original file content here]

---

## api.md
**File Path:** `./docs/api.md`
**Size:** 5678 bytes

[Original file content here]
```

## Use Cases

- **Documentation Consolidation**: Combine all project docs into one file
- **Content Review**: Get an overview of all documentation
- **Backup Creation**: Create a single backup of all markdown content
- **Content Analysis**: Analyze total documentation size and structure
- **Migration Prep**: Prepare content for moving to different documentation systems

## Requirements

- Python 3.6+
- No external dependencies (uses only standard library)

## Error Handling

The script includes robust error handling:
- **Encoding Issues**: Automatically tries UTF-8, then falls back to latin-1
- **File Access**: Gracefully handles permission errors
- **Missing Files**: Continues processing if individual files can't be read
- **Directory Access**: Skips inaccessible directories

## Exit Codes

- `0`: Success
- `1`: Error (no files found, write error, etc.)