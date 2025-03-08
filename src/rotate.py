#!/usr/bin/env python3
"""
Simple script to rotate CODEOWNERS in GitLab repositories.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Union

import gitlab
import yaml
import requests

# Import GCS library (only if needed)
try:
    from google.cloud import storage
    from google.cloud.exceptions import GoogleCloudError
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False


def resolve_env_vars(value: Any) -> Any:
    """
    Resolve environment variables in string values using ${VAR} syntax.

    Args:
        value: Value to process (can be string, dict, list, or other types)

    Returns:
        Value with environment variables resolved
    """
    if isinstance(value, str):
        # Define pattern for ${VAR} syntax
        pattern = r'\${([A-Za-z0-9_]+)}'

        # Find all environment variable references
        matches = re.findall(pattern, value)

        # Replace each match with the environment variable value
        result = value
        for var_name in matches:
            env_value = os.environ.get(var_name, '')
            result = result.replace(f'${{{var_name}}}', env_value)

        return result
    elif isinstance(value, dict):
        # Process recursively for dictionaries
        return {k: resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        # Process recursively for lists
        return [resolve_env_vars(item) for item in value]
    else:
        # Return other types as is
        return value


def load_config(config_path=None):
    """Load configuration from file and resolve environment variables."""
    config = {}

    # Try to load from file if provided
    if config_path:
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config file: {e}")
            sys.exit(1)

    # Resolve environment variables in the config
    config = resolve_env_vars(config)

    # Override with explicit environment variables
    if 'GITLAB_URL' in os.environ:
        config.setdefault('gitlab', {})['url'] = os.environ['GITLAB_URL']
    if 'GITLAB_TOKEN' in os.environ:
        config.setdefault('gitlab', {})['token'] = os.environ['GITLAB_TOKEN']
    if 'REPOSITORIES' in os.environ:
        config['repositories'] = os.environ['REPOSITORIES'].split(',')
    if 'REVIEWERS' in os.environ:
        config['reviewers'] = os.environ['REVIEWERS'].split(',')
    if 'NUM_REVIEWERS' in os.environ:
        config['num_reviewers'] = int(os.environ['NUM_REVIEWERS'])
    if 'GCS_BUCKET' in os.environ:
        config.setdefault('storage', {})['type'] = 'gcs'
        config.setdefault('storage', {})['bucket'] = os.environ['GCS_BUCKET']

    # Basic validation
    required = ['gitlab', 'repositories', 'reviewers']
    missing = [key for key in required if key not in config]
    if missing:
        print(f"Missing required configuration: {', '.join(missing)}")
        sys.exit(1)

    # Check if gitlab token is set
    if not config.get('gitlab', {}).get('token'):
        print("Error: GitLab token is required. Set it in config file using ${GITLAB_TOKEN} syntax or set GITLAB_TOKEN environment variable.")
        sys.exit(1)

    return config


def load_rotation_state(config):
    """Load rotation state from either local file or GCS."""
    storage_config = config.get('storage', {})
    storage_type = storage_config.get('type', 'local')

    # Default state if nothing is found
    default_state = {
        "timestamp": datetime.now().isoformat(),
        "reviewers": [],
        "successful_repos": [],
        "failed_repos": [],
        "rotation_queue": config['reviewers'].copy()
    }

    if storage_type == 'gcs':
        if not GCS_AVAILABLE:
            print("Warning: GCS storage configured but google-cloud-storage package not installed.")
            return default_state

        bucket_name = storage_config.get('bucket')
        prefix = storage_config.get('prefix', 'codeowners/')
        state_object = f"{prefix.rstrip('/')}/rotation_state.json"

        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(state_object)

            if blob.exists():
                content = blob.download_as_text()
                state = json.loads(content)
                print(f"Loaded rotation state from GCS: {bucket_name}/{state_object}")
                return state
            else:
                print(f"No rotation state found in GCS: {bucket_name}/{state_object}")
                return default_state
        except Exception as e:
            print(f"Warning: Could not load rotation state from GCS: {e}")
            return default_state
    else:
        # Local file storage
        state_file = storage_config.get('state_file', 'rotation_state.json')
        if Path(state_file).exists():
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                print(f"Loaded rotation state from file: {state_file}")
                return state
            except Exception as e:
                print(f"Warning: Could not load rotation state file: {e}")
                return default_state
        else:
            print(f"No rotation state file found at: {state_file}")
            return default_state


def save_rotation_state(config, state):
    """Save rotation state to either local file or GCS."""
    storage_config = config.get('storage', {})
    storage_type = storage_config.get('type', 'local')

    if storage_type == 'gcs':
        if not GCS_AVAILABLE:
            print("Warning: GCS storage configured but google-cloud-storage package not installed.")
            return

        bucket_name = storage_config.get('bucket')
        prefix = storage_config.get('prefix', 'codeowners/')
        state_object = f"{prefix.rstrip('/')}/rotation_state.json"

        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(state_object)

            # Convert to JSON and upload
            state_json = json.dumps(state, indent=2)
            blob.upload_from_string(state_json, content_type='application/json')
            print(f"Saved rotation state to GCS: {bucket_name}/{state_object}")
        except Exception as e:
            print(f"Warning: Could not save rotation state to GCS: {e}")
    else:
        # Local file storage
        state_file = storage_config.get('state_file', 'rotation_state.json')
        state_dir = os.path.dirname(state_file)
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)

        try:
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
            print(f"Saved rotation state to file: {state_file}")
        except Exception as e:
            print(f"Warning: Could not save rotation state file: {e}")


def get_next_reviewers(config):
    """Determine the next set of reviewers based on rotation state.

    This function implements a fair rotation system that:
    1. Tracks which reviewers have been assigned in a complete rotation cycle
    2. Won't repeat a reviewer until all reviewers have been assigned
    3. Ensures even distribution of assignments over time
    """
    all_reviewers = config['reviewers']
    num_reviewers = config.get('num_reviewers', 2)

    if len(all_reviewers) < num_reviewers:
        print(f"Not enough reviewers. Need {num_reviewers}, but only have {len(all_reviewers)}")
        sys.exit(1)

    # Load current state
    current_state = load_rotation_state(config)
    rotation_queue = current_state.get('rotation_queue', [])

    # If no rotation queue or empty, initialize with all reviewers
    if not rotation_queue:
        rotation_queue = all_reviewers.copy()
        print(f"Initialized new rotation queue with all reviewers")
    else:
        print(f"Current rotation queue: {', '.join(rotation_queue)}")

    # Check if we need to account for new reviewers that weren't in the original queue
    for reviewer in all_reviewers:
        if reviewer not in rotation_queue:
            rotation_queue.append(reviewer)
            print(f"Added new reviewer to queue: {reviewer}")

    # Remove reviewers that are no longer in the list of all reviewers
    rotation_queue = [r for r in rotation_queue if r in all_reviewers]

    # Select the next N reviewers from the queue
    next_reviewers = rotation_queue[:num_reviewers]

    # Update the queue by moving the selected reviewers to the end
    rotation_queue = rotation_queue[num_reviewers:] + next_reviewers

    print(f"Updated rotation queue: {', '.join(rotation_queue)}")

    # Store the updated queue for later
    config['_updated_rotation_queue'] = rotation_queue

    return next_reviewers


def generate_codeowners_content(reviewers):
    """Generate content for the CODEOWNERS file."""
    # Create a header with information about the rotation
    header = [
        "# CODEOWNERS file managed by CodeOwners Rotator",
        f"# Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Current reviewers: {', '.join(reviewers)}",
        ""
    ]

    # Default rule assigning all files to the reviewers
    rule = f"* {' '.join('@' + reviewer for reviewer in reviewers)}"

    # Combine the header and rule
    return "\n".join(header + [rule])


def get_default_branch(project):
    """Get the default branch for a GitLab project."""
    return project.default_branch


def update_repositories(gl, repo_names, reviewers):
    """Update CODEOWNERS files in multiple repositories."""
    # Generate new CODEOWNERS content
    content = generate_codeowners_content(reviewers)

    successful = []
    failed = []

    for repo_name in repo_names:
        try:
            # Get the project
            project = gl.projects.get(repo_name)

            # Get the default branch for this repository
            default_branch = get_default_branch(project)
            print(f"Default branch for {repo_name} is: {default_branch}")

            # Try to find existing CODEOWNERS file
            codeowners_path = None
            for path in ["CODEOWNERS", ".gitlab/CODEOWNERS", "docs/CODEOWNERS"]:
                try:
                    project.files.get(path, ref=default_branch)
                    codeowners_path = path
                    break
                except:
                    continue

            # Default path if not found
            if not codeowners_path:
                codeowners_path = "CODEOWNERS"

            # Commit message (conventional commit format, all lowercase)
            message = f"chore: update codeowners with new reviewer rotation"

            try:
                # Try to update existing file using the raw API endpoints
                # This approach bypasses the automatic base64 encoding
                headers = {'PRIVATE-TOKEN': project.manager.gitlab.private_token}
                url = f"{project.manager.gitlab.url}/api/v4/projects/{project.id}/repository/files/{codeowners_path}"

                data = {
                    'branch': default_branch,
                    'content': content,
                    'commit_message': message
                }

                # Check if file exists
                try:
                    project.files.get(codeowners_path, ref=default_branch)
                    # Update existing file
                    response = requests.put(url, headers=headers, json=data)
                    print(f"Updated existing CODEOWNERS in {repo_name}")
                except gitlab.exceptions.GitlabGetError:
                    # Create new file
                    response = requests.post(url, headers=headers, json=data)
                    print(f"Created new CODEOWNERS in {repo_name}")

                if response.status_code >= 400:
                    print(f"API error: {response.status_code} - {response.text}")
                    failed.append(repo_name)
                    continue

            except Exception as e:
                print(f"Error in API request: {e}")
                failed.append(repo_name)
                continue

            successful.append(repo_name)
        except Exception as e:
            print(f"Error updating {repo_name}: {e}")
            failed.append(repo_name)

    return successful, failed


def main():
    parser = argparse.ArgumentParser(description='Rotate CODEOWNERS in GitLab repositories')
    parser.add_argument('--config', '-c', help='Path to config file')
    parser.add_argument('--dry-run', '-d', action='store_true', help='Show what would be done without making changes')
    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Setup GitLab client
    try:
        gl = gitlab.Gitlab(url=config['gitlab']['url'], private_token=config['gitlab']['token'])
        gl.auth()
        print(f"Authenticated with GitLab at {config['gitlab']['url']}")
    except Exception as e:
        print(f"Error connecting to GitLab: {e}")
        sys.exit(1)

    # Determine next reviewers
    next_reviewers = get_next_reviewers(config)
    print(f"Next reviewers: {', '.join(next_reviewers)}")

    # Dry run or update repositories
    if args.dry_run:
        print("DRY RUN - would update these repositories:")
        for repo in config['repositories']:
            print(f"  - {repo}")
    else:
        # Update repositories
        successful, failed = update_repositories(gl, config['repositories'], next_reviewers)

        print(f"Updated {len(successful)} repositories successfully")
        if failed:
            print(f"Failed to update {len(failed)} repositories:")
            for repo in failed:
                print(f"  - {repo}")

        # Create single state record with the updated rotation queue
        state = {
            "timestamp": datetime.now().isoformat(),
            "reviewers": next_reviewers,
            "successful_repos": successful,
            "failed_repos": failed,
            "rotation_queue": config.get('_updated_rotation_queue', [])  # Store the updated queue
        }

        # Save state
        save_rotation_state(config, state)


if __name__ == "__main__":
    main()
