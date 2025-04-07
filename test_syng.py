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
        self.assertEqual(Path(test_file), list(new_files)[0])
    
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
        result = syncer.commit_file(Path(test_file))
        
        # Verify that the commit was successful
        self.assertTrue(result)
        
        # Check if the file exists in the git directory
        git_file = os.path.join(self.git_dir, "test.txt")
        self.assertTrue(os.path.exists(git_file))
        
        # Check if the file is in the git history
        commit_message = syncer.repo.head.commit.message
        self.assertIn("Add test.txt", commit_message)
    
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