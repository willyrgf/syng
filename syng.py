#!/usr/bin/env python3
import argparse
import os
import time
import sys
import logging
import threading
from pathlib import Path
from typing import Set, Optional, List, Tuple
import git
import shutil

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('syng')

# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# + GitManager: Handles direct Git interactions and state     +
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
class GitManager:
    """Manages Git repository interactions."""
    def __init__(self, repo_path_hint: str):
        self.repo_path_hint = Path(repo_path_hint).resolve()
        self._lock = threading.Lock()
        self.repo: Optional[git.Repo] = None
        self.git_dir: Optional[Path] = None
        self.repo_root: Optional[Path] = None

        logger.info(f"Initializing GitManager with hint path: {self.repo_path_hint}")
        self._find_and_init_repo()

    def _find_and_init_repo(self):
        """Finds the git repository and initializes core attributes."""
        try:
            # Search upwards from the hint path
            self.repo = git.Repo(self.repo_path_hint, search_parent_directories=True)
            self.git_dir = Path(self.repo.git_dir).resolve()
            self.repo_root = Path(self.repo.working_dir).resolve()
            logger.info(f"Opened repository at {self.repo_root} (found via {self.repo_path_hint})")
        except git.InvalidGitRepositoryError:
            logger.error(f"Could not find a git repository at or above: {self.repo_path_hint}")
            raise # Re-raise after logging

    def pull(self) -> bool:
        """Pull changes from remote repository, handling CWD changes."""
        if not self.repo or not self.repo_root:
            logger.error("Repository not initialized, cannot pull.")
            return False

        logger.debug("Attempting to acquire git lock for pull...")
        with self._lock:
            logger.debug("Acquired git lock for pull.")
            original_cwd = os.getcwd()
            success = False
            try:
                os.chdir(self.repo_root)
                logger.info(f"Temporarily changed CWD to {self.repo_root} for pull")
                for remote in self.repo.remotes:
                    logger.info(f"Pulling from remote: {remote.name}")
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
                os.chdir(original_cwd)
                logger.info(f"Restored CWD to {original_cwd}")
                logger.debug("Released git lock after pull.")
        return success

    def push(self) -> bool:
        """Push changes to remote repositories."""
        if not self.repo:
             logger.error("Repository not initialized, cannot push.")
             return False

        logger.debug("Attempting to acquire git lock for push...")
        # Assuming push might be called directly or from commit, acquire lock
        with self._lock:
            logger.debug("Acquired git lock for push.")
            success = False
            try:
                for remote in self.repo.remotes:
                    logger.info(f"Pushing to remote: {remote.name}")
                    branch = self.repo.active_branch
                    tracking_branch = branch.tracking_branch()

                    if tracking_branch is None and len(self.repo.remotes) > 0:
                        try:
                            logger.info(f"Setting upstream branch for {branch} to {remote.name}/{branch}")
                            self.repo.git.push('--set-upstream', remote.name, branch.name)
                            # Push successful after setting upstream
                        except git.GitCommandError as e:
                            logger.error(f"Failed to set upstream branch: {e}")
                            # Continue to try normal push below if setting upstream failed?
                            # Or maybe return False here? Let's try continuing.
                    
                    # Try normal push (either upstream was set, already existed, or setting failed)
                    # We access push_info like a list, as it returns a list of PushInfo objects
                    push_info_list = remote.push() 
                    for info in push_info_list:
                        # Log summary and flags for each push operation
                        logger.info(f"Push summary for {remote.name}/{branch.name}: {info.summary}")
                        if info.flags & git.PushInfo.ERROR:
                             logger.error(f"Push error flags set: {info.flags}")
                        elif info.flags & git.PushInfo.REJECTED:
                             logger.warning(f"Push rejected flags set: {info.flags}")
                        # Consider other flags like DELETED, NEW_HEAD, etc. if needed

                success = True # Assume success if no exceptions
                # More robust check: inspect push_info_list flags
                if any(info.flags & (git.PushInfo.ERROR | git.PushInfo.REJECTED) for info in push_info_list):
                    logger.warning("Push operation encountered errors or rejections.")
                    success = False # Mark as failed if any error/rejection

            except git.GitCommandError as e:
                logger.error(f"Failed to push changes: {e}")
                success = False
            except Exception as e:
                 logger.error(f"An unexpected error occurred during push: {e}")
                 success = False
            finally:
                logger.debug("Released git lock after push.")
        return success
        
    def add_files(self, file_paths_rel_repo: List[str]) -> bool:
        """Adds a list of files (relative to repo root) to the git index."""
        if not self.repo:
            logger.error("Repository not initialized, cannot add files.")
            return False
        if not file_paths_rel_repo:
            logger.debug("No files provided to add.")
            return True # Nothing to do is a success

        logger.debug(f"Attempting to acquire git lock for add_files: {len(file_paths_rel_repo)} files")
        with self._lock:
            logger.debug("Acquired git lock for add_files.")
            success = False
            try:
                # Ensure paths are strings
                str_paths = [str(p) for p in file_paths_rel_repo]
                self.repo.git.add(str_paths)
                logger.info(f"Staged {len(str_paths)} files.")
                success = True
            except git.GitCommandError as e:
                logger.error(f"Git error adding files: {e}")
                success = False
            except Exception as e:
                logger.error(f"Error adding files: {e}")
                success = False
            finally:
                logger.debug("Released git lock after add_files.")
        return success

    def commit(self, message: str, files_rel_repo: Optional[List[str]] = None) -> bool:
        """Commits staged changes. Optionally checks specific files for changes first."""
        if not self.repo:
            logger.error("Repository not initialized, cannot commit.")
            return False

        logger.debug("Attempting to acquire git lock for commit...")
        with self._lock:
            logger.debug("Acquired git lock for commit.")
            success = False
            try:
                # Check if there are changes to commit
                staged_changes = self.repo.index.diff("HEAD", paths=files_rel_repo)
                # Also check untracked files, especially if files_rel_repo represents newly added files
                untracked = set(self.repo.untracked_files)
                added_untracked_in_scope = False
                if files_rel_repo:
                    added_untracked_in_scope = any(f in untracked for f in files_rel_repo)
                else:
                    # If no specific files given, commit any staged changes or untracked files
                    # Note: Untracked files need 'git add' first, so this primarily relies on staged_changes
                    # However, if add_files was called just before, untracked might be relevant
                    # A simpler check might be just `self.repo.is_dirty(index=True, untracked_files=True)`
                    # Let's stick to diff + untracked check for now
                    pass # Commit will proceed if anything is staged

                if not staged_changes and not added_untracked_in_scope and files_rel_repo is not None:
                    # If specific files were given, and none are staged or newly untracked (after add), then nothing to commit for *them*
                     logger.info(f"No staged changes or relevant untracked files detected to commit for the specified list.")
                     # Check if *any* untracked files exist, maybe log a warning if committing anyway?
                     if not staged_changes and not untracked:
                         logger.info("Index matches HEAD and no untracked files. Commit skipped.")
                         return True # Success, as nothing needed committing.

                # Proceed with commit
                self.repo.git.commit('-m', message)
                logger.info(f"Committed changes with message: {message}")
                success = True

            except git.GitCommandError as e:
                # Handle specific case of "nothing to commit" which isn't really an error
                if "nothing to commit" in str(e) or "no changes added to commit" in str(e):
                    logger.info("Commit attempted, but no changes were staged.")
                    success = True # Considered success
                else:
                    logger.error(f"Git error during commit: {e}")
                    success = False
            except Exception as e:
                logger.error(f"Error committing changes: {e}")
                success = False
            finally:
                logger.debug("Released git lock after commit.")
        return success

# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# + GitSyncer: Handles file discovery, processing, and orchestration +
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
class GitSyncer:
    def __init__(
        self,
        source_dir: str,
        git_manager: GitManager, # Use GitManager instance
        commit_push: bool = False,
        auto_pull: bool = False,
        per_file: bool = False,
        pull_interval: Optional[int] = None
    ):
        self.source_dir = Path(source_dir).resolve()
        self.git_manager = git_manager # Store the manager
        self.commit_push = commit_push
        self.auto_pull = auto_pull
        self.per_file = per_file
        self.pull_interval = pull_interval
        self._stop_event: Optional[threading.Event] = None
        self._pull_thread: Optional[threading.Thread] = None
        self.processed_files: Set[Path] = set()

        # Determine if file watching is needed (commit_push implies watching)
        # Note: per_file without commit_push doesn't strictly *require* watching,
        # but the current run loop implies it. Let's keep it simple for now.
        self._should_watch_files = self.commit_push or self.per_file

        logger.info(f"Initializing GitSyncer with source_dir={self.source_dir}")
        logger.info(f"Options: commit_push={commit_push}, auto_pull={auto_pull}, per_file={per_file}, pull_interval={pull_interval}, watch_files={self._should_watch_files}")
        logger.info(f"Using GitManager for repo at: {self.git_manager.repo_root}")

        # Ensure source directory exists
        if not self.source_dir.exists():
            raise FileNotFoundError(f"Source directory does not exist: {self.source_dir}")

        # Start periodic pull thread if needed
        if self.auto_pull and self.pull_interval is not None and self.pull_interval > 0:
            self._stop_event = threading.Event()
            self._pull_thread = threading.Thread(
                target=self._periodic_pull_worker,
                args=(self._stop_event,),
                daemon=True
            )
            self._pull_thread.start()
            logger.info(f"Started periodic pull thread with interval {self.pull_interval}s")

    def pull(self) -> bool:
        """Delegates pull operation to GitManager."""
        if not self.auto_pull:
            return True
        return self.git_manager.pull()

    def find_new_files(self) -> Set[Path]:
        """Find new files in source_dir that haven't been processed yet."""
        # Needs git_manager.repo_root and git_manager.git_dir for checks
        if not self.git_manager.repo_root or not self.git_manager.git_dir:
             logger.error("Git repository path not available in GitManager. Cannot find files.")
             return set()

        current_files = set()
        for root, _, files in os.walk(self.source_dir):
            root_path = Path(root).resolve()
            # Skip .git directory
            if self.git_manager.git_dir == root_path or self.git_manager.git_dir in root_path.parents:
                continue

            for file in files:
                file_path = (root_path / file).resolve()
                # Basic check if it's a file (avoids processing directories accidentally)
                if file_path.is_file():
                     # All files found within source_dir are candidates initially
                    current_files.add(file_path)

        # Return files not previously processed
        newly_found = current_files - self.processed_files
        # Check if any processed files were modified? (Optional enhancement)
        # For now, only return truly new files based on path.
        return newly_found


    def _determine_paths_and_copy(self, file_path: Path) -> Tuple[Optional[Path], Optional[str]]:
        """
        Determines the destination path in the repo and copies the file if necessary.
        Returns (destination_path, path_relative_to_repo) or (None, None) on error.
        """
        if not self.git_manager.repo_root: return None, None
        try:
            file_path = file_path.resolve()
            repo_root = self.git_manager.repo_root

            is_inside_repo = repo_root in file_path.parents or repo_root == file_path.parent

            if not is_inside_repo:
                # File is outside the repo, calculate destination path
                if not file_path.is_relative_to(self.source_dir):
                     logger.warning(f"File {file_path} is outside the source directory {self.source_dir}. Skipping.")
                     return None, None # Should not happen with current find_new_files logic, but safety check
                rel_path_from_source = file_path.relative_to(self.source_dir)
                dest_path = (repo_root / rel_path_from_source).resolve()
                git_file_path_rel_repo = str(dest_path.relative_to(repo_root))

                # Create parent directories if they don't exist
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Copy the file
                shutil.copy2(file_path, dest_path)
                logger.debug(f"Copied {file_path} to {dest_path}")
                return dest_path, git_file_path_rel_repo
            else:
                # File is already inside the repo structure
                git_file_path_rel_repo = str(file_path.relative_to(repo_root))
                return file_path, git_file_path_rel_repo # Return original path and relative path
        except Exception as e:
            logger.error(f"Error determining paths or copying for {file_path}: {e}")
            return None, None


    def _process_single_file(self, file_path: Path) -> bool:
        """Handles copying (if needed), adding, committing, and pushing a single file."""
        dest_path, git_rel_path = self._determine_paths_and_copy(file_path)

        if not dest_path or not git_rel_path:
             return False # Error during copy/path determination

        # Add the file
        if not self.git_manager.add_files([git_rel_path]):
             logger.error(f"Failed to add file {git_rel_path} via GitManager.")
             return False

        # Commit the file
        commit_message = f"Add {git_rel_path}"
        if not self.git_manager.commit(commit_message, files_rel_repo=[git_rel_path]):
             # Check if commit failed or just reported "nothing to commit"
             # The commit method logs this, so we just check the return value
             logger.warning(f"Commit command for {git_rel_path} did not succeed or had no effect.")
             # Decide if this is a failure - if the goal is to ensure the file is tracked,
             # even 'nothing to commit' might be acceptable if it was already tracked/identical.
             # Let's assume non-True means we should not mark as processed / push.
             # However, if commit returns True for "nothing to commit", this logic works.
             # Let's refine GitManager.commit to return True in that case. (Done above)
             if not self.git_manager.commit(commit_message, files_rel_repo=[git_rel_path]): # Re-check needed? No, use the result.
                  logger.error(f"Failed to commit file {git_rel_path} via GitManager.")
                  return False # Treat actual commit failure as failure

        logger.info(f"Committed file: {git_rel_path}")

        # Push changes if requested
        if self.commit_push:
             if not self.git_manager.push():
                  logger.error(f"Failed to push changes after committing {git_rel_path}.")
                  return False # Failed push means overall failure for this file

        return True


    def _process_batch(self, file_paths: Set[Path]) -> Tuple[bool, Set[Path]]:
        """Handles copying, adding, committing, and pushing a batch of files."""
        files_to_add_rel: List[str] = []
        copy_operations: List[Tuple[Path, Path]] = []
        processed_in_batch: Set[Path] = set()
        commit_needed = False # Only commit if add is successful and changes are detected

        # 1. Determine paths, perform copies, collect relative paths for git add
        for file_path in file_paths:
            dest_path, git_rel_path = self._determine_paths_and_copy(file_path)
            if dest_path and git_rel_path:
                 files_to_add_rel.append(git_rel_path)
                 # Store original path for marking as processed later
                 processed_in_batch.add(file_path)
                 # Keep track of copy src->dest if needed (not currently, copy happens in _determine_paths)
            else:
                 logger.warning(f"Skipping file {file_path} due to error in path determination/copy.")
                 # Don't add to processed_in_batch if prep failed

        if not files_to_add_rel:
             logger.info("No files successfully prepared for batch processing.")
             # Return True (no error) but empty processed set
             return True, set()

        # 2. Add all files at once
        if not self.git_manager.add_files(files_to_add_rel):
             logger.error("Failed to add files for batch commit via GitManager.")
             return False, set() # Add failed, return False and empty processed set

        commit_needed = True # If add succeeded, we intend to commit

        # 3. Commit the batch
        commit_message = f"Add batch of {len(files_to_add_rel)} files"
        # Pass the list of added files to commit for change detection scope
        commit_successful = self.git_manager.commit(commit_message, files_rel_repo=files_to_add_rel)

        if not commit_successful:
            logger.error("Failed to commit batch via GitManager or no changes detected.")
            # If commit returned True for "no changes", it's still a success in terms of processing.
            # Assume commit returns True if no error OR no changes needed.
            # So if it returns False, it's a real error.
            return False, set() # Commit failed, return False

        logger.info(f"Committed batch of {len(files_to_add_rel)} files.")

        # 4. Push the batch if requested
        push_successful = True
        if self.commit_push:
             push_successful = self.git_manager.push()
             if not push_successful:
                  logger.error("Failed to push changes after batch commit.")
                  # If push fails, should we still count the commit as success?
                  # Let's say the batch processing failed if push failed.
                  return False, set()

        # If we got here, all steps (add, commit, maybe push) succeeded
        return True, processed_in_batch


    def process_new_files(self) -> None:
        """Process new files found in the source directory."""
        new_files = self.find_new_files()
        if not new_files:
            return

        logger.info(f"Found {len(new_files)} new files to process")

        if self.per_file:
            # Commit each file individually
            for file_path in new_files:
                 logger.info(f"Processing file individually: {file_path.name}")
                 if self._process_single_file(file_path):
                     self.processed_files.add(file_path)
                 else:
                     logger.warning(f"Failed to process file {file_path.name}. Will retry later.")
        else:
            # Process files as a batch
            logger.info("Processing new files in batch mode...")
            batch_success, processed_paths = self._process_batch(new_files)
            if batch_success:
                 self.processed_files.update(processed_paths)
                 logger.info(f"Successfully processed batch, marked {len(processed_paths)} files.")
            else:
                 logger.warning("Batch processing failed. Files will be retried.")


    def run(self) -> None:
        """Run the syncer based on configuration."""
        try:
            if self._should_watch_files:
                logger.info("Starting file watching loop...")
                while True:
                    if self._stop_event and self._stop_event.is_set():
                        logger.info("Stop event detected during file watching.")
                        break
                    self.process_new_files()
                    # Use stop_event.wait for sleeping to allow faster shutdown
                    if self._stop_event:
                         # Wait for 5 seconds or until stop event is set
                         interrupted = self._stop_event.wait(timeout=5)
                         if interrupted:
                             logger.info("Stop event detected while sleeping.")
                             break
                    else:
                        # Fallback sleep if stop event somehow not created
                        time.sleep(5)

            elif self.auto_pull and self._pull_thread and self._pull_thread.is_alive():
                logger.info("Auto-pull enabled, file watching disabled. Keeping main thread alive.")
                if self._stop_event:
                    self._stop_event.wait() # Wait indefinitely for stop signal
                else:
                    # Fallback wait
                    while self._pull_thread.is_alive(): time.sleep(1) # pragma: no cover
                logger.info("Pull thread finished or stop signal received.")
            else:
                logger.info("No watch/pull tasks configured or active. Exiting.")
                return # Explicitly return

        except KeyboardInterrupt:
            logger.info("Syncer interrupted by user.")
        except Exception as e:
            logger.exception(f"Syncer stopped due to error: {e}")
            # Ensure stop event is set even on unexpected errors
            if self._stop_event and not self._stop_event.is_set():
                self._stop_event.set()
            sys.exit(1) # Exit with error code
        finally:
            logger.info("Syncer shutting down...")
            # Signal the pull thread to stop if it exists and is running
            if self._stop_event and not self._stop_event.is_set():
                logger.info("Signaling background threads to stop...")
                self._stop_event.set()

             # Wait for the pull thread to actually finish
            if self.auto_pull and self._pull_thread and self._pull_thread.is_alive():
                 logger.info("Waiting for pull thread to terminate...")
                 # Check if the current thread is the pull thread itself before joining
                 if threading.current_thread() != self._pull_thread:
                     self._pull_thread.join(timeout=10) # Increased timeout slightly
                     if self._pull_thread.is_alive():
                         logger.warning("Pull thread did not terminate gracefully.")
                 else: # pragma: no cover
                      logger.info("Main thread is the pull thread, cannot join itself.")

            logger.info("Syncer finished.")


    def _periodic_pull_worker(self, stop_event: threading.Event) -> None:
        """Worker function for the background pull thread."""
        logger.info("Periodic pull worker started.")
        # Perform an initial pull immediately? Optional, currently no.
        while not stop_event.wait(timeout=self.pull_interval):
            logger.info("Pull interval elapsed, attempting to pull changes...")
            if not self.pull(): # Delegates to git_manager.pull
                logger.warning("Pull failed, will retry next interval.")
            # Loop continues until stop_event is set or wait times out
        logger.info("Periodic pull worker stopping.")


def main():
    parser = argparse.ArgumentParser(description="Sync files between a source directory and a git repository")
    parser.add_argument("--source_dir", required=True, help="Source directory to monitor for new files")
    parser.add_argument("--git_dir", required=True, help="Path within the Git repository (e.g., repo root or subdirectory)")
    parser.add_argument("--commit-push", action="store_true", help="Commit and push new files")
    parser.add_argument("--auto-pull", action="store_true", help="Automatically pull changes from remote")
    parser.add_argument("--per-file", action="store_true", help="Create a separate commit for each new file")
    parser.add_argument("--pull-interval", type=int, default=60, help="Interval in seconds to automatically pull changes (requires --auto-pull). Default: 60")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Setup logging level
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.getLogger('syng').setLevel(log_level)
    # Optionally set GitPython logging level
    # logging.getLogger('git').setLevel(logging.INFO) # Or DEBUG

    try:
        # 1. Initialize GitManager
        git_manager = GitManager(repo_path_hint=args.git_dir)

        # Ensure repo was found before proceeding
        if not git_manager.repo:
             sys.exit(1) # GitManager init logs the error

        # 2. Initialize GitSyncer with the manager
        pull_interval_value = args.pull_interval if args.auto_pull else None
        syncer = GitSyncer(
            source_dir=args.source_dir,
            git_manager=git_manager,
            commit_push=args.commit_push,
            auto_pull=args.auto_pull,
            per_file=args.per_file,
            pull_interval=pull_interval_value
        )

        # 3. Run the syncer
        syncer.run()

    except FileNotFoundError as e:
         logger.error(f"Initialization failed: {e}")
         sys.exit(1)
    except ValueError as e: # Catch potential repo finding errors if not caught earlier
         logger.error(f"Initialization failed: {e}")
         sys.exit(1)
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()