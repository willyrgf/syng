#!/usr/bin/env python3

import unittest
import tempfile
import shutil
import os
from pathlib import Path
import sys
import time
import threading
import git
import logging

# Set logging level to reduce output
logging.getLogger('syng').setLevel(logging.DEBUG)

# Import the GitSyncer class directly from the syng.py script in the root
from syng import GitSyncer

class TestGitSyncer(unittest.TestCase):
    def setUp(self):
        # Create temporary directories for the test
        self.source_dir = tempfile.mkdtemp()
        self.git_dir = tempfile.mkdtemp()
        
        # Initialize git repo in git_dir
        self.repo = git.Repo.init(self.git_dir)
        
        # Configure git user for testing
        self.repo.config_writer().set_value("user", "name", "Test User").release()
        self.repo.config_writer().set_value("user", "email", "test@example.com").release()
        
        # Create initial commit
        readme_path = os.path.join(self.git_dir, "README.md")
        with open(readme_path, "w") as f:
            f.write("# Test Repository")
        self.repo.git.add("README.md")
        self.repo.git.commit("-m", "Initial commit")
    
    def tearDown(self):
        # Clean up temporary directories
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.git_dir, ignore_errors=True)
    
    def test_find_new_files(self):
        # Create a new file in the source directory
        test_file = os.path.join(self.source_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Test content")
        
        # Initialize GitSyncer
        syncer = GitSyncer(
            source_dir=self.source_dir,
            git_dir=self.git_dir,
            commit_push=False,
            auto_pull=False,
            per_file=True
        )
        
        # Find new files
        new_files = syncer.find_new_files()
        
        # Verify that the new file was found
        self.assertEqual(len(new_files), 1)
        # Use resolve() on both sides to handle symlinks (like /tmp vs /private/tmp) correctly
        self.assertEqual(Path(test_file).resolve(), list(new_files)[0].resolve())
    
    def test_commit_file(self):
        # Create a new file in the source directory
        test_file = os.path.join(self.source_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Test content")
        
        # Initialize GitSyncer
        syncer = GitSyncer(
            source_dir=self.source_dir,
            git_dir=self.git_dir,
            commit_push=False,
            auto_pull=False,
            per_file=True
        )
        
        # Commit the file
        result = syncer.commit_file(Path(test_file).resolve())
        
        # Verify that the commit was successful
        self.assertTrue(result)
        
        # Check if the file exists in the git directory
        git_file = os.path.join(self.git_dir, "test.txt")
        self.assertTrue(os.path.exists(git_file))
        
        # Check if the file is in the git history
        commit_message = syncer.repo.head.commit.message
        self.assertIn("Add test.txt", commit_message)
    
    def test_relative_path_source_dir(self):
        """Test handling of relative paths for source directory"""
        # Save current working directory
        original_cwd = os.getcwd()

        try:
            # Create a temporary directory structure
            base_dir = tempfile.mkdtemp()
            source_dir = os.path.join(base_dir, "source")
            git_dir = os.path.join(base_dir, "git_repo")
            
            # Create the directories
            os.makedirs(source_dir)
            os.makedirs(git_dir)
            
            # Initialize git repo
            repo = git.Repo.init(git_dir)
            repo.config_writer().set_value("user", "name", "Test User").release()
            repo.config_writer().set_value("user", "email", "test@example.com").release()
            
            # Create initial commit
            readme_path = os.path.join(git_dir, "README.md")
            with open(readme_path, "w") as f:
                f.write("# Test Repository")
            repo.git.add("README.md")
            repo.git.commit("-m", "Initial commit")
            
            # Create a test file in the source directory
            test_file = os.path.join(source_dir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Test content")
            
            # Change working directory to base_dir
            os.chdir(base_dir)
            
            # Initialize GitSyncer with relative paths
            syncer = GitSyncer(
                source_dir="./source",  # Relative path
                git_dir=git_dir,  # Absolute path
                commit_push=False,
                auto_pull=False,
                per_file=True
            )
            
            # Process new files
            syncer.process_new_files()
            
            # Check if the file was copied to the git directory
            git_file = os.path.join(git_dir, "test.txt")
            self.assertTrue(os.path.exists(git_file))
            
            # Check the content
            with open(git_file, "r") as f:
                content = f.read()
            self.assertEqual(content, "Test content")
            
            # Verify the absolute path correctly resolved from relative path
            self.assertEqual(syncer.source_dir, Path(source_dir).resolve())
            
        finally:
            # Restore original working directory and clean up
            os.chdir(original_cwd)
            shutil.rmtree(base_dir, ignore_errors=True)
    
    def test_relative_path_git_dir(self):
        """Test handling of relative paths for git directory"""
        # Save current working directory
        original_cwd = os.getcwd()

        try:
            # Create a temporary directory structure
            base_dir = tempfile.mkdtemp()
            source_dir = os.path.join(base_dir, "source")
            git_dir = os.path.join(base_dir, "git_repo")
            
            # Create the directories
            os.makedirs(source_dir)
            os.makedirs(git_dir)
            
            # Initialize git repo
            repo = git.Repo.init(git_dir)
            repo.config_writer().set_value("user", "name", "Test User").release()
            repo.config_writer().set_value("user", "email", "test@example.com").release()
            
            # Create initial commit
            readme_path = os.path.join(git_dir, "README.md")
            with open(readme_path, "w") as f:
                f.write("# Test Repository")
            repo.git.add("README.md")
            repo.git.commit("-m", "Initial commit")
            
            # Create a test file in the source directory
            test_file = os.path.join(source_dir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Test content")
            
            # Change working directory to base_dir
            os.chdir(base_dir)
            
            # Initialize GitSyncer with relative paths
            syncer = GitSyncer(
                source_dir=source_dir,  # Absolute path
                git_dir="./git_repo",  # Relative path
                commit_push=False,
                auto_pull=False,
                per_file=True
            )
            
            # Process new files
            syncer.process_new_files()
            
            # Check if the file was copied to the git directory
            git_file = os.path.join(git_dir, "test.txt")
            self.assertTrue(os.path.exists(git_file))
            
            # Verify the absolute path correctly resolved from relative path
            self.assertEqual(syncer.repo_root, Path(git_dir).resolve())
            
        finally:
            # Restore original working directory and clean up
            os.chdir(original_cwd)
            shutil.rmtree(base_dir, ignore_errors=True)
    
    def test_both_relative_paths(self):
        """Test handling when both source and git directories are specified as relative paths"""
        # Save current working directory
        original_cwd = os.getcwd()

        try:
            # Create a temporary directory structure
            base_dir = tempfile.mkdtemp()
            source_dir = os.path.join(base_dir, "source")
            git_dir = os.path.join(base_dir, "git_repo")
            
            # Create the directories
            os.makedirs(source_dir)
            os.makedirs(git_dir)
            
            # Initialize git repo
            repo = git.Repo.init(git_dir)
            repo.config_writer().set_value("user", "name", "Test User").release()
            repo.config_writer().set_value("user", "email", "test@example.com").release()
            
            # Create initial commit
            readme_path = os.path.join(git_dir, "README.md")
            with open(readme_path, "w") as f:
                f.write("# Test Repository")
            repo.git.add("README.md")
            repo.git.commit("-m", "Initial commit")
            
            # Create a test file in the source directory
            test_file = os.path.join(source_dir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Test content")
            
            # Change working directory to base_dir
            os.chdir(base_dir)
            
            # Initialize GitSyncer with relative paths for both directories
            syncer = GitSyncer(
                source_dir="./source",  # Relative path
                git_dir="./git_repo",   # Relative path
                commit_push=False,
                auto_pull=False,
                per_file=True
            )
            
            # Process new files
            syncer.process_new_files()
            
            # Check if the file was copied to the git directory
            git_file = os.path.join(git_dir, "test.txt")
            self.assertTrue(os.path.exists(git_file))
            
            # Verify the absolute paths correctly resolved from relative paths
            self.assertEqual(syncer.source_dir, Path(source_dir).resolve())
            self.assertEqual(syncer.repo_root, Path(git_dir).resolve())
            
        finally:
            # Restore original working directory and clean up
            os.chdir(original_cwd)
            shutil.rmtree(base_dir, ignore_errors=True)
    
    def test_parent_relative_path(self):
        """Test handling of parent directory notation in relative paths (../)"""
        # Save current working directory
        original_cwd = os.getcwd()

        try:
            # Create a temporary directory structure
            base_dir = tempfile.mkdtemp()
            parent_dir = os.path.join(base_dir, "parent")
            child_dir = os.path.join(parent_dir, "child")
            git_dir = os.path.join(parent_dir, "git_repo")
            
            # Create the directories
            os.makedirs(parent_dir)
            os.makedirs(child_dir)
            os.makedirs(git_dir)
            
            # Initialize git repo
            repo = git.Repo.init(git_dir)
            repo.config_writer().set_value("user", "name", "Test User").release()
            repo.config_writer().set_value("user", "email", "test@example.com").release()
            
            # Create initial commit
            readme_path = os.path.join(git_dir, "README.md")
            with open(readme_path, "w") as f:
                f.write("# Test Repository")
            repo.git.add("README.md")
            repo.git.commit("-m", "Initial commit")
            
            # Create a test file in the parent directory
            test_file = os.path.join(parent_dir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Test content")
            
            # Change working directory to child_dir
            os.chdir(child_dir)
            
            # Initialize GitSyncer with relative path that goes up one level
            syncer = GitSyncer(
                source_dir="..",  # Parent directory
                git_dir="../git_repo",
                commit_push=False,
                auto_pull=False,
                per_file=True
            )
            
            # Process new files
            syncer.process_new_files()
            
            # Check if the file was copied to the git directory
            git_file = os.path.join(git_dir, "test.txt")
            self.assertTrue(os.path.exists(git_file))
            
            # Verify the absolute paths correctly resolved from relative paths
            self.assertEqual(syncer.source_dir, Path(parent_dir).resolve())
            self.assertEqual(syncer.repo_root, Path(git_dir).resolve())
            
        finally:
            # Restore original working directory and clean up
            os.chdir(original_cwd)
            shutil.rmtree(base_dir, ignore_errors=True)
    
    def test_same_directory(self):
        # Initialize git repo in a new directory for this test
        test_dir = tempfile.mkdtemp()
        repo = git.Repo.init(test_dir)
        repo.config_writer().set_value("user", "name", "Test User").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()
        
        # Create initial commit
        readme_path = os.path.join(test_dir, "README.md")
        with open(readme_path, "w") as f:
            f.write("# Test Repository")
        repo.git.add("README.md")
        repo.git.commit("-m", "Initial commit")
        
        # Create a new file in the directory
        test_file = os.path.join(test_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Test content")
        
        # Initialize GitSyncer with the same directory for source and git
        syncer = GitSyncer(
            source_dir=test_dir,
            git_dir=test_dir,
            commit_push=False,
            auto_pull=False,
            per_file=True
        )
        
        # Process new files
        syncer.process_new_files()
        
        # Check if the file is in the git history
        commit_message = repo.head.commit.message
        self.assertIn("Add test.txt", commit_message)
        
        # Clean up
        shutil.rmtree(test_dir, ignore_errors=True)
    
    def test_auto_pull_same_directory(self):
        """Test that changes pushed to remote are pulled when source_dir equals git_dir."""
        # Create "local" and "remote" repositories for testing
        local_repo_path = tempfile.mkdtemp()
        remote_repo_path = tempfile.mkdtemp()
        
        # Initialize the remote repo as bare
        remote_repo = git.Repo.init(remote_repo_path, bare=True)
        
        # Initialize the local repo
        local_repo = git.Repo.init(local_repo_path)
        local_repo.config_writer().set_value("user", "name", "Local User").release()
        local_repo.config_writer().set_value("user", "email", "local@example.com").release()
        
        # Add remote to local repo
        local_repo.create_remote('origin', remote_repo_path)
        
        # Create initial commit in local repo
        readme_path = os.path.join(local_repo_path, "README.md")
        with open(readme_path, "w") as f:
            f.write("# Test Repository")
        local_repo.git.add("README.md")
        local_repo.git.commit("-m", "Initial commit")
        
        # Push to remote
        local_repo.git.push('--set-upstream', 'origin', local_repo.active_branch.name)
        
        # Clone the remote to create a second local repo (simulating external agent)
        external_repo_path = tempfile.mkdtemp()
        external_repo = git.Repo.clone_from(remote_repo_path, external_repo_path)
        external_repo.config_writer().set_value("user", "name", "External User").release()
        external_repo.config_writer().set_value("user", "email", "external@example.com").release()
        
        # Create a new file in the external repo
        external_file = os.path.join(external_repo_path, "external.txt")
        with open(external_file, "w") as f:
            f.write("This file was created externally")
        
        # Commit and push from external repo
        external_repo.git.add("external.txt")
        external_repo.git.commit("-m", "Add external file")
        external_repo.git.push()
        
        # Initialize GitSyncer with auto-pull enabled
        syncer = GitSyncer(
            source_dir=local_repo_path,
            git_dir=local_repo_path,
            commit_push=False,
            auto_pull=True,
            per_file=True
        )
        
        # Directly call process_new_files a few times instead of using a thread
        for _ in range(3):
            syncer.process_new_files()
        
        # Check if the external file exists in the local repo (pulled from remote)
        local_external_file = os.path.join(local_repo_path, "external.txt")
        self.assertTrue(os.path.exists(local_external_file), "External file was not pulled to local repo")
        
        # Check the content
        with open(local_external_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "This file was created externally")
        
        # Clean up
        shutil.rmtree(local_repo_path, ignore_errors=True)
        shutil.rmtree(remote_repo_path, ignore_errors=True)
        shutil.rmtree(external_repo_path, ignore_errors=True)
        
    def test_nested_directories(self):
        """Test syncing files in nested directories"""
        # Create a nested directory structure in source
        nested_dir = os.path.join(self.source_dir, "level1", "level2")
        os.makedirs(nested_dir)
        
        # Create a file in the nested directory
        nested_file = os.path.join(nested_dir, "nested.txt")
        with open(nested_file, "w") as f:
            f.write("Nested file content")
        
        # Initialize GitSyncer
        syncer = GitSyncer(
            source_dir=self.source_dir,
            git_dir=self.git_dir,
            commit_push=False,
            auto_pull=False,
            per_file=True
        )
        
        # Process new files
        syncer.process_new_files()
        
        # Check if the nested file exists in the git directory
        git_nested_file = os.path.join(self.git_dir, "level1", "level2", "nested.txt")
        self.assertTrue(os.path.exists(git_nested_file))
        
        # Check the content
        with open(git_nested_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "Nested file content")
    
    def test_batch_commits(self):
        """Test committing multiple files in a single batch"""
        # Create multiple files in the source directory
        for i in range(5):
            file_path = os.path.join(self.source_dir, f"file{i}.txt")
            with open(file_path, "w") as f:
                f.write(f"Content of file {i}")
        
        # Initialize GitSyncer with per_file=False for batch commits
        syncer = GitSyncer(
            source_dir=self.source_dir,
            git_dir=self.git_dir,
            commit_push=False,
            auto_pull=False,
            per_file=False  # Batch mode
        )
        
        # Process new files
        syncer.process_new_files()
        
        # Check if all files were added in a single commit
        # Verify each file exists in git_dir
        for i in range(5):
            git_file = os.path.join(self.git_dir, f"file{i}.txt")
            self.assertTrue(os.path.exists(git_file))
        
        # Verify there's only one commit (plus the initial one)
        commit_count = sum(1 for _ in syncer.repo.iter_commits())
        self.assertEqual(commit_count, 2)  # Initial commit + our batch commit
    
    def test_commit_push(self):
        """Test commit and push functionality"""
        # Set up remote repo
        remote_path = tempfile.mkdtemp()
        remote_repo = git.Repo.init(remote_path, bare=True)
        
        # Add remote to our test repo
        self.repo.create_remote('origin', remote_path)
        
        # Create a test file
        test_file = os.path.join(self.source_dir, "push_test.txt")
        with open(test_file, "w") as f:
            f.write("Testing commit and push")
        
        # Initialize GitSyncer with commit_push=True
        syncer = GitSyncer(
            source_dir=self.source_dir,
            git_dir=self.git_dir,
            commit_push=True,  # Enable pushing
            auto_pull=False,
            per_file=True
        )
        
        # Set up the upstream branch explicitly before processing files
        self.repo.git.push('--set-upstream', 'origin', self.repo.active_branch.name)
        
        # Process new files
        syncer.process_new_files()
        
        # Clone the remote repo to verify the push worked
        clone_path = tempfile.mkdtemp()
        cloned_repo = git.Repo.clone_from(remote_path, clone_path)
        
        # Check if the file exists in the cloned repo
        cloned_file = os.path.join(clone_path, "push_test.txt")
        self.assertTrue(os.path.exists(cloned_file))
        
        # Clean up
        shutil.rmtree(remote_path, ignore_errors=True)
        shutil.rmtree(clone_path, ignore_errors=True)
    
    def test_batch_commits_same_directory(self):
        """Test batch commits when source_dir and git_dir are the same."""
        test_dir = tempfile.mkdtemp()
        try:
            # Initialize git repo
            repo = git.Repo.init(test_dir)
            repo.config_writer().set_value("user", "name", "Test User").release()
            repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create initial commit
            readme_path = os.path.join(test_dir, "README.md")
            with open(readme_path, "w") as f:
                f.write("# Test Repo")
            repo.git.add("README.md")
            repo.git.commit("-m", "Initial commit")

            # Create multiple files directly in the repo directory
            for i in range(3):
                file_path = os.path.join(test_dir, f"batch_file{i}.txt")
                with open(file_path, "w") as f:
                    f.write(f"Batch content {i}")

            # Initialize GitSyncer with same directory and batch mode
            syncer = GitSyncer(
                source_dir=test_dir,
                git_dir=test_dir,
                commit_push=False,
                auto_pull=False,
                per_file=False # Batch mode
            )

            # Process new files
            syncer.process_new_files()

            # Check if all files were added in a single commit
            for i in range(3):
                git_file = os.path.join(test_dir, f"batch_file{i}.txt")
                self.assertTrue(os.path.exists(git_file))

            # Verify there's only one commit (plus the initial one)
            commit_count = sum(1 for _ in repo.iter_commits())
            self.assertEqual(commit_count, 2) # Initial + Batch commit

        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_commit_push_same_directory(self):
        """Test commit and push when source_dir and git_dir are the same."""
        local_repo_path = tempfile.mkdtemp()
        remote_path = tempfile.mkdtemp()
        clone_path = tempfile.mkdtemp()

        try:
            # Initialize remote bare repo
            remote_repo = git.Repo.init(remote_path, bare=True)

            # Initialize local repo
            local_repo = git.Repo.init(local_repo_path)
            local_repo.config_writer().set_value("user", "name", "Local User").release()
            local_repo.config_writer().set_value("user", "email", "local@example.com").release()

            # Add remote
            local_repo.create_remote('origin', remote_path)

            # Initial commit and push to set upstream
            readme_path = os.path.join(local_repo_path, "README.md")
            with open(readme_path, "w") as f:
                f.write("# Local Repo")
            local_repo.git.add("README.md")
            local_repo.git.commit("-m", "Initial commit")
            local_repo.git.push('--set-upstream', 'origin', local_repo.active_branch.name)

            # Create a test file directly in the local repo directory
            test_file = os.path.join(local_repo_path, "push_same_dir_test.txt")
            with open(test_file, "w") as f:
                f.write("Testing commit and push in same directory")

            # Initialize GitSyncer with same directory and commit_push=True
            syncer = GitSyncer(
                source_dir=local_repo_path,
                git_dir=local_repo_path,
                commit_push=True, # Enable pushing
                auto_pull=False,
                per_file=True
            )

            # Process new files (which should commit and push)
            syncer.process_new_files()

            # Clone the remote repo to verify the push worked
            cloned_repo = git.Repo.clone_from(remote_path, clone_path)

            # Check if the file exists in the cloned repo
            cloned_file = os.path.join(clone_path, "push_same_dir_test.txt")
            self.assertTrue(os.path.exists(cloned_file))

        finally:
            # Clean up
            shutil.rmtree(local_repo_path, ignore_errors=True)
            shutil.rmtree(remote_path, ignore_errors=True)
            shutil.rmtree(clone_path, ignore_errors=True)
    
    def test_error_handling(self):
        """Test error handling for invalid directories"""
        with self.assertRaises(FileNotFoundError):
            GitSyncer(
                source_dir="/nonexistent/path",
                git_dir=self.git_dir,
                commit_push=False,
                auto_pull=False,
                per_file=True
            )
        
        with self.assertRaises(FileNotFoundError):
            GitSyncer(
                source_dir=self.source_dir,
                git_dir="/nonexistent/path",
                commit_push=False,
                auto_pull=False,
                per_file=True
            )
    
    def test_nonrepo_git_dir(self):
        """Test handling of a non-repository git directory"""
        non_repo_dir = tempfile.mkdtemp()
        
        with self.assertRaises(ValueError):
            GitSyncer(
                source_dir=self.source_dir,
                git_dir=non_repo_dir,  # Not a git repository
                commit_push=False,
                auto_pull=False,
                per_file=True
            )
        
        # Clean up
        shutil.rmtree(non_repo_dir, ignore_errors=True)
    
    def test_git_dir_is_subdir(self):
        """Test handling when git_dir is a subdirectory of the actual git repository."""
        # Create base directory and subdirectory structure
        base_dir = tempfile.mkdtemp()
        repo_root = os.path.join(base_dir, "repo_root")
        subdir = os.path.join(repo_root, "data", "subdir")
        os.makedirs(subdir)

        # Initialize git repo in repo_root
        repo = git.Repo.init(repo_root)
        repo.config_writer().set_value("user", "name", "Test User").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()

        # Create initial commit in repo_root
        readme_path = os.path.join(repo_root, "README.md")
        with open(readme_path, "w") as f:
            f.write("# Main Repo")
        repo.git.add("README.md")
        repo.git.commit("-m", "Initial commit in root")

        # Create a test file in the subdirectory
        test_file_path = os.path.join(subdir, "sub_test.txt")
        with open(test_file_path, "w") as f:
            f.write("Content in subdirectory")

        # Initialize GitSyncer pointing git_dir to the subdirectory
        # This should ideally discover the repo at repo_root
        syncer = GitSyncer(
            source_dir=subdir,  # Source is the subdir
            git_dir=subdir,     # Git dir points to the subdir too
            commit_push=False,
            auto_pull=False,
            per_file=True
        )

        # Assert that the syncer found the correct repository root
        self.assertEqual(Path(syncer.repo.working_dir), Path(repo_root).resolve())

        # Process new files
        syncer.process_new_files()

        # Verify the file was committed correctly relative to the repo root
        git_file_rel_path = os.path.join("data", "subdir", "sub_test.txt")
        git_file_abs_path = os.path.join(repo_root, git_file_rel_path)

        self.assertTrue(os.path.exists(git_file_abs_path))

        # Check commit history for the file addition relative to root
        commit_messages = [commit.message for commit in repo.iter_commits()]
        expected_commit_message = f"Add {Path(git_file_rel_path)}" # Path ensures correct separators
        self.assertIn(expected_commit_message, commit_messages[0]) # Check latest commit

        # Clean up
        shutil.rmtree(base_dir, ignore_errors=True)
    
    def test_file_modifications(self):
        """Test syncing modified files"""
        # Create initial file
        test_file = os.path.join(self.source_dir, "modify_test.txt")
        with open(test_file, "w") as f:
            f.write("Initial content")
            
        # Initialize syncer and process the file
        syncer = GitSyncer(
            source_dir=self.source_dir,
            git_dir=self.git_dir,
            commit_push=False,
            auto_pull=False,
            per_file=True
        )
        syncer.process_new_files()
        
        # Mark the file as processed before modification
        initial_processed = set(syncer.processed_files)
        
        # Modify the file
        with open(test_file, "w") as f:
            f.write("Modified content")
        
        # Process the file again
        syncer.processed_files = set()  # Reset to simulate a new run
        syncer.process_new_files()
        
        # Check if the file was processed again
        git_file = os.path.join(self.git_dir, "modify_test.txt")
        with open(git_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "Modified content")

if __name__ == "__main__":
    # Run all tests
    unittest.main() 