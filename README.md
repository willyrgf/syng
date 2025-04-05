# Syng

Syng is a synchronization tool that maintains a persistent layer a source directory and a git repository.

## Features

- **Forward-only sync**: Watches for new files in the source directory and commits them to the git repository
- **Automatic pull**: Keeps the git repository updated, avoiding conflicts
- **Per-file commits**: Option to create a separate commit for each file
- **Configurable directories**: Supports syncing between different source and git directories

## Usage

```
nix run .#syng -- --source_dir /path/to/source --git_dir /path/to/repo [options]
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
