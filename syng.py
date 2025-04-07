#!/usr/bin/env python3

import argparse
import os
import time
import sys
import logging
from pathlib import Path
from typing import Set, Optional
import git
import shutil

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('syng')

class GitSyncer:
    def __init__(
        self,
        source_dir: str,
        git_dir: str,
        commit_push: bool = False,
        auto_pull: bool = False,
        per_file: bool = False
    ):
        self.source_dir = Path(source_dir).absolute()
        self.git_dir = Path(git_dir).absolute()
        self.commit_push = commit_push
        self.auto_pull = auto_pull
        self.per_file = per_file
        self.processed_files: Set[Path] = set()
        
        logger.info(f"Initializing GitSyncer with source_dir={self.source_dir}, git_dir={self.git_dir}")
        logger.info(f"Options: commit_push={commit_push}, auto_pull={auto_pull}, per_file={per_file}")
        
        # Ensure directories exist
        if not self.source_dir.exists():
            raise FileNotFoundError(f"Source directory does not exist: {self.source_dir}")
        
        if not self.git_dir.exists():
            raise FileNotFoundError(f"Git directory does not exist: {self.git_dir}")
            
        # Initialize git repository
        try:
            self.repo = git.Repo(self.git_dir)
            logger.info(f"Opened existing repository at {self.git_dir}")
        except git.InvalidGitRepositoryError:
            raise ValueError(f"Git directory is not a git repository: {self.git_dir}")
    
    def pull(self) -> bool:
        """Pull changes from remote repository."""
        if not self.auto_pull:
            return True
            
        try:
            for remote in self.repo.remotes:
                logger.info(f"Pulling from remote: {remote.name}")
                fetch_info = remote.pull(ff_only=True)
                logger.info(f"Pull result: {fetch_info}")
            return True
        except git.GitCommandError as e:
            logger.error(f"Failed to pull changes: {e}")
            return False
    
    def find_new_files(self) -> Set[Path]:
        """Find new files in source_dir that haven't been processed yet."""
        current_files = set()
        for root, _, files in os.walk(self.source_dir):
            root_path = Path(root)
            # Skip .git directory if source_dir is same as git_dir
            if ".git" in root_path.parts:
                continue
                
            for file in files:
                file_path = root_path / file
                if file_path.is_file():
                    # Get path relative to source_dir
                    if self.source_dir == self.git_dir:
                        # If source_dir is the same as git_dir, process all files
                        rel_path = file_path.relative_to(self.source_dir)
                        current_files.add(file_path)
                    else:
                        # Handle files from source_dir that need to be copied to git_dir
                        rel_path = file_path.relative_to(self.source_dir)
                        dest_path = self.git_dir / rel_path
                        current_files.add(file_path)
        
        # Return files that haven't been processed yet
        return current_files - self.processed_files
    
    def commit_file(self, file_path: Path) -> bool:
        """Commit a single file to the git repository."""
        try:
            if self.source_dir != self.git_dir:
                # Copy file to git_dir if source_dir is different
                rel_path = file_path.relative_to(self.source_dir)
                dest_path = self.git_dir / rel_path
                
                # Create parent directories if they don't exist
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy the file
                shutil.copy2(file_path, dest_path)
                
                # Use the destination path for git operations
                git_file_path = rel_path
            else:
                # Use relative path for git operations if source_dir is the same as git_dir
                git_file_path = file_path.relative_to(self.git_dir)
            
            # Add the file to git
            self.repo.git.add(str(git_file_path))
            
            # Check if there are changes to commit
            if not self.repo.is_dirty():
                logger.info(f"No changes to commit for {git_file_path}")
                return True
            
            # Commit the file
            commit_message = f"Add {git_file_path}"
            self.repo.git.commit('-m', commit_message)
            
            logger.info(f"Committed file: {git_file_path}")
            
            # Push changes if requested
            if self.commit_push:
                self._push()
                
            return True
            
        except git.GitCommandError as e:
            logger.error(f"Git error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error committing file {file_path}: {e}")
            return False
    
    def _push(self) -> bool:
        """Push changes to remote repositories."""
        try:
            for remote in self.repo.remotes:
                logger.info(f"Pushing to remote: {remote.name}")
                
                # Check if current branch has an upstream branch
                branch = self.repo.active_branch
                tracking_branch = branch.tracking_branch()
                
                if tracking_branch is None and len(self.repo.remotes) > 0:
                    # Set upstream branch for the current branch if not set
                    try:
                        logger.info(f"Setting upstream branch for {branch} to {remote.name}/{branch}")
                        self.repo.git.push('--set-upstream', remote.name, branch.name)
                        # Return after setting upstream - this push already sent our changes
                        return True
                    except git.GitCommandError as e:
                        logger.error(f"Failed to set upstream branch: {e}")
                        # Continue to try normal push
                
                # Normal push if upstream is already set
                push_info = remote.push()
                logger.info(f"Push result: {push_info}")
            return True
        except git.GitCommandError as e:
            logger.error(f"Failed to push changes: {e}")
            return False
    
    def process_new_files(self) -> None:
        """Process new files found in the source directory."""
        new_files = self.find_new_files()
        if not new_files:
            return
            
        logger.info(f"Found {len(new_files)} new files to process")
        
        # Pull changes first if auto_pull is enabled
        if self.auto_pull and not self.pull():
            logger.warning("Skipping processing due to pull failure")
            return
        
        if self.per_file:
            # Commit each file individually
            for file_path in new_files:
                if self.commit_file(file_path):
                    self.processed_files.add(file_path)
        else:
            try:
                # Add all files at once
                for file_path in new_files:
                    if self.source_dir != self.git_dir:
                        # Copy file to git_dir if source_dir is different
                        rel_path = file_path.relative_to(self.source_dir)
                        dest_path = self.git_dir / rel_path
                        
                        # Create parent directories if they don't exist
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Copy the file
                        shutil.copy2(file_path, dest_path)
                        
                        # Add the file to git
                        self.repo.git.add(str(rel_path))
                    else:
                        # Add file directly in git_dir
                        rel_path = file_path.relative_to(self.git_dir)
                        self.repo.git.add(str(rel_path))
                
                # Check if there are changes to commit
                if self.repo.is_dirty() or self.repo.untracked_files:
                    # Commit all added files
                    self.repo.git.commit('-m', "Add new files")
                    
                    # Push changes if requested
                    if self.commit_push:
                        self._push()
                    
                # Mark all files as processed
                self.processed_files.update(new_files)
                
            except git.GitCommandError as e:
                logger.error(f"Git error: {e}")
            except Exception as e:
                logger.error(f"Error processing files: {e}")
    
    def run(self) -> None:
        """Run the syncer in an infinite loop."""
        try:
            while True:
                self.process_new_files()
                # Sleep to avoid high CPU usage
                time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Syncer stopped by user")
        except Exception as e:
            logger.exception(f"Syncer stopped due to error: {e}")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Sync files between a source directory and a git repository")
    parser.add_argument("--source_dir", required=True, help="Source directory to monitor for new files")
    parser.add_argument("--git_dir", required=True, help="Git repository directory")
    parser.add_argument("--commit-push", action="store_true", help="Commit and push new files")
    parser.add_argument("--auto-pull", action="store_true", help="Automatically pull changes from remote")
    parser.add_argument("--per-file", action="store_true", help="Create a separate commit for each new file")
    
    args = parser.parse_args()
    
    syncer = GitSyncer(
        source_dir=args.source_dir,
        git_dir=args.git_dir,
        commit_push=args.commit_push,
        auto_pull=args.auto_pull,
        per_file=args.per_file
    )
    
    syncer.run()

if __name__ == "__main__":
    main() 