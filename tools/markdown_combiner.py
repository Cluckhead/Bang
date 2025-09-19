#!/usr/bin/env python3
"""
Simple Data Checker - Markdown File Combiner

This script finds all markdown files in the workspace and combines them
into a single comprehensive markdown document.
"""

import os
import glob
from pathlib import Path
from datetime import datetime
import argparse

# Common directories to exclude by default
DEFAULT_EXCLUDE_DIRS = {
    'node_modules', '.git', '.vscode', '.cursor', '__pycache__', 
    '.pytest_cache', '.mypy_cache', 'venv', '.env', 'env',
    '.next', '.nuxt', 'dist', 'build', '.output', '.cache'
}

def should_exclude_path(file_path, exclude_dirs):
    """Check if a file path should be excluded based on directory rules."""
    path_parts = Path(file_path).parts
    return any(part in exclude_dirs for part in path_parts)

def find_markdown_files(root_dir=".", exclude_dirs=None, output_file="combined_documentation.md"):
    """Find all markdown files in the workspace, excluding specified directories."""
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS
    
    markdown_files = []
    
    # Common markdown extensions
    extensions = ["*.md", "*.mdc", "*.markdown", "*.mkd"]
    
    for ext in extensions:
        # Find files recursively
        pattern = os.path.join(root_dir, "**", ext)
        files = glob.glob(pattern, recursive=True)
        
        # Filter out excluded directories and output file
        filtered_files = [f for f in files if not should_exclude_path(f, exclude_dirs) 
                         and not f.endswith(output_file)]
        markdown_files.extend(filtered_files)
    
    # Sort files for consistent output
    markdown_files.sort()
    
    return markdown_files

def read_file_content(file_path):
    """Read and return file content with error handling."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        # Try with different encoding
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"
    except Exception as e:
        return f"Error reading file: {str(e)}"

def create_table_of_contents(files):
    """Create a table of contents for the combined document."""
    toc = ["# Table of Contents\n"]
    
    for i, file_path in enumerate(files, 1):
        # Convert file path to a readable name
        name = os.path.basename(file_path)
        # Create anchor link (GitHub-style)
        anchor = name.lower().replace('.', '').replace('_', '-').replace(' ', '-')
        relative_path = os.path.relpath(file_path)
        toc.append(f"{i}. [{name}](#{anchor}) - `{relative_path}`")
    
    return "\n".join(toc) + "\n\n"

def combine_markdown_files(files, output_file="combined_documentation.md"):
    """Combine all markdown files into a single document."""
    
    # Generate header
    header = f"""# Combined Documentation
Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total files combined: {len(files)}

This document combines all markdown files found in the workspace.

---

"""
    
    # Generate table of contents
    toc = create_table_of_contents(files)
    
    # Start building the combined content
    combined_content = [header, toc]
    
    for file_path in files:
        relative_path = os.path.relpath(file_path)
        file_name = os.path.basename(file_path)
        
        # Create section header
        section_header = f"""
---

## {file_name}

**File Path:** `{relative_path}`
**Size:** {os.path.getsize(file_path)} bytes

"""
        
        # Read file content
        content = read_file_content(file_path)
        
        # Add to combined content
        combined_content.append(section_header)
        combined_content.append(content)
        combined_content.append("\n\n")
    
    # Write combined file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("".join(combined_content))
        return True
    except Exception as e:
        print(f"Error writing output file: {str(e)}")
        return False

def main():
    """Main function to run the markdown combiner."""
    parser = argparse.ArgumentParser(description="Combine all markdown files in the workspace")
    parser.add_argument("--output", "-o", default="combined_documentation.md", 
                       help="Output file name (default: combined_documentation.md)")
    parser.add_argument("--root", "-r", default=".", 
                       help="Root directory to search (default: current directory)")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Verbose output")
    parser.add_argument("--include-all", action="store_true",
                       help="Include all directories (don't exclude node_modules, .git, etc.)")
    parser.add_argument("--exclude-dirs", nargs='+', 
                       help="Additional directories to exclude (space-separated)")
    
    args = parser.parse_args()
    
    # Set up exclude directories
    exclude_dirs = set()
    if not args.include_all:
        exclude_dirs.update(DEFAULT_EXCLUDE_DIRS)
    
    if args.exclude_dirs:
        exclude_dirs.update(args.exclude_dirs)
    
    print("🔍 Searching for markdown files...")
    if exclude_dirs:
        print(f"📁 Excluding directories: {', '.join(sorted(exclude_dirs))}")
    
    markdown_files = find_markdown_files(args.root, exclude_dirs, args.output)
    
    if not markdown_files:
        print("❌ No markdown files found in the workspace.")
        return 1
    
    print(f"✅ Found {len(markdown_files)} markdown files:")
    for file in markdown_files:
        if args.verbose:
            size = os.path.getsize(file)
            print(f"  - {file} ({size} bytes)")
        else:
            print(f"  - {file}")
    
    print(f"\n📝 Combining files into '{args.output}'...")
    success = combine_markdown_files(markdown_files, args.output)
    
    if success:
        output_size = os.path.getsize(args.output)
        print(f"✅ Successfully created '{args.output}' ({output_size} bytes)")
        print(f"📊 Combined {len(markdown_files)} files into one document.")
    else:
        print("❌ Failed to create combined document.")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())