# Syng

A lightweight, flexible tool for synchronizing files between directories and git repositories. Syng automates the process of monitoring directories for changes and committing them to a git repository, with configurable behaviors for committing, pushing, and pulling changes.

## Key Features
- Bi-directional sync between directories and git repositories
- Per-file or batch commit options
- Automatic pull capabilities to stay in sync with remote changes
- Optional push on commit for immediate synchronization
- Support for nested directory structures
- Non-invasive monitoring with low CPU usage


## Usage

```
nix run github:willyrgf/syng -- --source_dir /path/to/source --git_dir /path/to/repo [options]
```

## Installation

Syng is packaged using Nix flakes:

```
nix profile install github:willyrgf/syng
syng --help
```

### Options

- `--source_dir`: Source directory to monitor for new files
- `--git_dir`: Git repository directory
- `--commit-push`: Commit and push new files to remote repository
- `--auto-pull`: Automatically pull changes from remote repository
- `--per-file`: Create a separate commit for each new file

### Examples

```
# Monitor a directory and sync changes to a git repository, committing and pushing each file separately
nix run .#syng -- --source_dir /path/to/data --git_dir /path/to/repo --commit-push --auto-pull --per-file

# Use the same directory for both source and git repository
nix run .#syng -- --source_dir /path/to/repo --git_dir /path/to/repo --commit-push --auto-pull
```

## Development

To set up a development environment:

```
nix develop
```

This will provide you with all the dependencies needed for development.

To run the tests:

```
nix develop -c python3 test_syng.py
```

## License

MIT
