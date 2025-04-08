#!/usr/bin/env python3

import argparse
import os
import time
import sys
import logging
import threading
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
        per_file: bool = False,
        pull_interval: Optional[int] = None
    ):
        self.source_dir = Path(source_dir).resolve()
        # Store the original git_dir path for comparison and copy logic
        self._original_git_dir = Path(git_dir).resolve() 
        self.commit_push = commit_push
        self.auto_pull = auto_pull
        self.per_file = per_file
        self.pull_interval = pull_interval
        self._stop_event: Optional[threading.Event] = None
        self.processed_files: Set[Path] = set()
        self._git_lock = threading.Lock() # Add lock for git operations
        
        logger.info(f"Initializing GitSyncer with source_dir={self.source_dir}, git_dir={self._original_git_dir}")
        logger.info(f"Options: commit_push={commit_push}, auto_pull={auto_pull}, per_file={per_file}, pull_interval={pull_interval}")
        
        # Ensure directories exist
        if not self.source_dir.exists():
            raise FileNotFoundError(f"Source directory does not exist: {self.source_dir}")
        
        # Use the original path for the existence check
        if not self._original_git_dir.exists(): 
            raise FileNotFoundError(f"Git directory does not exist: {self._original_git_dir}")
            
        # Initialize git repository, searching parent directories
        try:
            # Search upwards from the original git_dir path
            self.repo = git.Repo(self._original_git_dir, search_parent_directories=True) 
            # Store the actual git directory found (.git folder)
            self.git_dir = Path(self.repo.git_dir).resolve() 
            # Store the working tree directory (repo root)
            self.repo_root = Path(self.repo.working_dir).resolve() 
            logger.info(f"Opened repository at {self.repo_root} (found via {self._original_git_dir})")

            # Start periodic pull thread if needed
            if self.auto_pull and self.pull_interval is not None and self.pull_interval > 0:
                self._stop_event = threading.Event()
                self._pull_thread = threading.Thread(
                    target=self._periodic_pull_worker,
                    args=(self._stop_event,),
                    daemon=True # Exit automatically when main thread exits
                )
                self._pull_thread.start()
                logger.info(f"Started periodic pull thread with interval {self.pull_interval}s")
        except git.InvalidGitRepositoryError:
            # If search fails, raise the error referring to the original path
            raise ValueError(f"Could not find a git repository at or above: {self._original_git_dir}")
    
    def pull(self) -> bool:
        """Pull changes from remote repository, handling CWD changes."""
        if not self.auto_pull:
            return True

        # Acquire lock before interacting with the repo
        logger.debug("Attempting to acquire git lock for pull...")
        with self._git_lock:
            logger.debug("Acquired git lock for pull.")
            original_cwd = os.getcwd()
            success = False # Track success within the locked block
            try:
                # Change CWD to repo root before pulling
                os.chdir(self.repo_root)
                logger.info(f"Temporarily changed CWD to {self.repo_root} for pull")

                for remote in self.repo.remotes:
                    logger.info(f"Pulling from remote: {remote.name}")
                    # Using repo.git.pull directly for potentially better error handling/info
                    # and ensures it runs within the correct CWD context
                    pull_output = self.repo.git.pull(remote.name, self.repo.active_branch.name, '-v', '--ff-only')
                    logger.info(f"Pull result for {remote.name}: {pull_output}")
                success = True
            except git.GitCommandError as e:
                logger.error(f"Failed to pull changes: {e}")
                success = False
            except Exception as e:
                logger.error(f"An unexpected error occurred during pull: {e}")
                success = False
            finally:
                # Ensure CWD is restored
                os.chdir(original_cwd)
                logger.info(f"Restored CWD to {original_cwd}")
                logger.debug("Released git lock after pull.")
        return success
    
    def find_new_files(self) -> Set[Path]:
        """Find new files in source_dir that haven't been processed yet."""
        current_files = set()
        for root, _, files in os.walk(self.source_dir):
            root_path = Path(root).resolve()
            # Skip .git directory belonging to the discovered repo
            # Also skip if source_dir itself is inside the .git dir (edge case)
            if self.git_dir == root_path or self.git_dir in root_path.parents:
                continue
                
            for file in files:
                file_path = (root_path / file).resolve()
                if file_path.is_file():
                    # Check if the file is within the source directory (redundant check removed)
                    # Determine if we need to copy the file or if it's already in the repo
                    if self.source_dir == self.repo_root or self.source_dir in self.repo_root.parents:
                         # If source is the repo root or a parent, we treat files as directly in the repo
                         # (This case simplifies if source == original_git_dir and original_git_dir was a subdir)
                         current_files.add(file_path)
                    elif self.repo_root in self.source_dir.parents:
                        # If source is a subdirectory of the repo root (common case)
                        current_files.add(file_path)
                    else:
                         # If source is completely outside the repo (needs copying)
                         current_files.add(file_path)
        
        # Return files that haven't been processed yet or have been modified
        # Note: Modification check isn't explicitly here, relies on reprocessing logic later
        return current_files - self.processed_files
    
    def commit_file(self, file_path: Path) -> bool:
        """Commit a single file to the git repository."""
        # Acquire lock before interacting with the repo
        logger.debug(f"Attempting to acquire git lock for commit_file: {file_path.name}")
        with self._git_lock:
            logger.debug(f"Acquired git lock for commit_file: {file_path.name}")
            try:
                # Resolve the file path to handle symlinks
                file_path = file_path.resolve()

                # Determine if the file is inside the repo or needs copying
                is_inside_repo = self.repo_root in file_path.parents or self.repo_root == file_path.parent

                if not is_inside_repo:
                    # File is outside the repo, calculate destination path
                    rel_path_from_source = file_path.relative_to(self.source_dir)
                    dest_path = (self.repo_root / rel_path_from_source).resolve()
                    git_file_path_rel_repo = dest_path.relative_to(self.repo_root)

                    # Create parent directories if they don't exist
                    dest_path.parent.mkdir(parents=True, exist_ok=True)

                    # Copy the file
                    shutil.copy2(file_path, dest_path)
                    logger.debug(f"Copied {file_path} to {dest_path}")
                else:
                    # File is already inside the repo structure
                    git_file_path_rel_repo = file_path.relative_to(self.repo_root)

                # Add the file to git using path relative to repo root
                self.repo.git.add(str(git_file_path_rel_repo))

                # Check if there are changes to commit (index differs from HEAD)
                # Use the relative path for diff check as well
                if not self.repo.index.diff("HEAD", paths=[str(git_file_path_rel_repo)]):
                     logger.info(f"No staged changes to commit for {git_file_path_rel_repo}")
                     # Even if no staged changes, check if untracked (newly added file)
                     if str(git_file_path_rel_repo) in self.repo.untracked_files:
                         logger.info(f"File {git_file_path_rel_repo} is untracked, proceeding with commit.")
                     else:
                         return True # Assume already committed or no changes


                # Commit the file
                commit_message = f"Add {git_file_path_rel_repo}"
                self.repo.git.commit('-m', commit_message)

                logger.info(f"Committed file: {git_file_path_rel_repo}")
                
                # Push changes if requested
                if self.commit_push:
                    self._push() # _push is called within the locked block

                return True

            except git.GitCommandError as e:
                logger.error(f"Git error processing {file_path.name}: {e}")
                return False
            except Exception as e:
                logger.error(f"Error committing file {file_path.name}: {e}")
                return False
            finally:
                logger.debug(f"Released git lock after commit_file: {file_path.name}")
    
    def _push(self) -> bool:
        """Push changes to remote repositories."""
        # This method should only be called when the git lock is already held
        # by the calling method (commit_file or process_new_files)
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
        
        if self.per_file:
            # Commit each file individually
            for file_path in new_files:
                if self.commit_file(file_path):
                    self.processed_files.add(file_path)
        else:
            # --- Batch commit mode ---
            files_to_add_rel: list[str] = []
            copy_operations: list[tuple[Path, Path]] = []
            commit_needed = False

            # First pass: Identify files needing copy/add (no git interaction yet)
            for file_path in new_files:
                try:
                    file_path = file_path.resolve()
                    is_inside_repo = self.repo_root in file_path.parents or self.repo_root == file_path.parent

                    if not is_inside_repo:
                        rel_path_from_source = file_path.relative_to(self.source_dir)
                        dest_path = (self.repo_root / rel_path_from_source).resolve()
                        git_file_path_rel_repo = dest_path.relative_to(self.repo_root)
                        copy_operations.append((file_path, dest_path))
                    else:
                        git_file_path_rel_repo = file_path.relative_to(self.repo_root)

                    files_to_add_rel.append(str(git_file_path_rel_repo))
                    commit_needed = True # Assume add/commit needed if files found
                except Exception as e:
                     logger.error(f"Error preparing file {file_path} for batch commit: {e}")
                     # Skip this file but continue with others

            if not commit_needed:
                 logger.info("No new files identified for batch commit after preparation.")
                 # Mark all original new_files as processed even if prep failed for some
                 # This prevents reprocessing files that caused prep errors repeatedly
                 self.processed_files.update(new_files)
                 return # Exit process_new_files

            # Acquire lock before performing git operations for the batch
            logger.debug("Attempting to acquire git lock for batch commit...")
            with self._git_lock:
                logger.debug("Acquired git lock for batch commit.")
                batch_success = False
                processed_in_batch = set() # Track files successfully processed in this batch
                try:
                    # Perform copy operations
                    for src, dest in copy_operations:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dest)
                        logger.debug(f"Copied {src} to {dest}")

                    # Add all prepared files at once
                    if files_to_add_rel:
                        self.repo.git.add(files_to_add_rel)
                        logger.info(f"Staged {len(files_to_add_rel)} files for batch commit.")

                    # Check if there are staged changes before committing
                    # (is_dirty is expensive, use diff check)
                    # Check index vs HEAD or if untracked files were added
                    staged_changes = self.repo.index.diff("HEAD", paths=files_to_add_rel)
                    added_untracked = any(f in self.repo.untracked_files for f in files_to_add_rel)

                    if staged_changes or added_untracked:
                        # Commit all added files
                        self.repo.git.commit('-m', f"Add batch of {len(files_to_add_rel)} files")
                        logger.info(f"Committed batch of {len(files_to_add_rel)} files.")

                        # Push changes if requested
                        if self.commit_push:
                           self._push() # Called within lock

                        batch_success = True # Commit/push successful
                        processed_in_batch = new_files # Mark all as processed if batch commit worked

                    else:
                         logger.info("No changes staged for batch commit (files might already exist/be identical).")
                         batch_success = True # No error, considered success
                         processed_in_batch = new_files # Mark as processed


                except git.GitCommandError as e:
                    logger.error(f"Git error during batch processing: {e}")
                    # Keep batch_success = False
                except Exception as e:
                    logger.error(f"Error during batch processing: {e}")
                    # Keep batch_success = False
                finally:
                    # Mark files as processed ONLY if the git operations for the batch succeeded
                    if batch_success and processed_in_batch:
                         self.processed_files.update(processed_in_batch)
                         logger.info(f"Successfully processed batch, marked {len(processed_in_batch)} files.")
                    else:
                         logger.warning("Batch processing failed or had no effect. Files will be retried.")
                    logger.debug("Released git lock after batch commit.")
    
    def run(self) -> None:
        """Run the syncer in an infinite loop."""
        try:
            while True:
                self.process_new_files()
                # Sleep to avoid high CPU usage
                time.sleep(5) # Keep the existing sleep for file checking
        except KeyboardInterrupt:
            logger.info("Syncer stopped by user")
            if self._stop_event:
                logger.info("Signaling pull thread to stop...")
                self._stop_event.set()
        except Exception as e:
            logger.exception(f"Syncer stopped due to error: {e}")
            if self._stop_event:
                self._stop_event.set() # Also signal stop on other errors
            sys.exit(1)

    def _periodic_pull_worker(self, stop_event: threading.Event) -> None:
        """Worker function for the background pull thread."""
        # Perform an initial pull immediately if desired (optional)
        # self.pull() 
        while not stop_event.wait(timeout=self.pull_interval): # Wait for interval or stop signal
            logger.info("Pull interval elapsed, attempting to pull changes...")
            if not self.pull():
                logger.warning("Pull failed, will retry next interval.")
            # Loop continues until stop_event is set
        logger.info("Periodic pull worker stopping.")

def main():
    parser = argparse.ArgumentParser(description="Sync files between a source directory and a git repository")
    parser.add_argument("--source_dir", required=True, help="Source directory to monitor for new files")
    parser.add_argument("--git_dir", required=True, help="Git repository directory")
    parser.add_argument("--commit-push", action="store_true", help="Commit and push new files")
    parser.add_argument("--auto-pull", action="store_true", help="Automatically pull changes from remote")
    parser.add_argument("--per-file", action="store_true", help="Create a separate commit for each new file")
    parser.add_argument("--pull-interval", type=int, default=60, help="Interval in seconds to automatically pull changes (requires --auto-pull). Default: 60")
    
    args = parser.parse_args()
    
    # Ensure auto_pull is enabled if a pull_interval is used effectively
    pull_interval_value = args.pull_interval if args.auto_pull else None

    syncer = GitSyncer(
        source_dir=args.source_dir,
        git_dir=args.git_dir,
        commit_push=args.commit_push,
        auto_pull=args.auto_pull,
        per_file=args.per_file,
        pull_interval=pull_interval_value
    )
    
    syncer.run()

if __name__ == "__main__":
    main() 