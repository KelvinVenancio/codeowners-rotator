#!/usr/bin/env python3
"""
Script to notify CODEOWNERS about GitLab merge requests via Slack.

This script:
1. Reads the CODEOWNERS file from a GitLab repository
2. Maps GitLab users to Slack users using explicit mapping
3. Sends direct messages to reviewers
4. Falls back to a channel if direct messages fail
"""

import argparse
import os
import re
import sys
from typing import Dict, List, Optional

import gitlab
import yaml

# Import Slack SDK (try/except for graceful degradation)
try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    print("Warning: slack_sdk not installed. Run 'pip install slack_sdk' to enable Slack notifications.")


def resolve_env_vars(value):
    """Resolve environment variables in string values using ${VAR} syntax."""
    if isinstance(value, str):
        pattern = r'\${([A-Za-z0-9_]+)}'
        matches = re.findall(pattern, value)
        
        result = value
        for var_name in matches:
            env_value = os.environ.get(var_name, '')
            result = result.replace(f'${{{var_name}}}', env_value)
        
        return result
    elif isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_env_vars(item) for item in value]
    else:
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
    if 'SLACK_TOKEN' in os.environ:
        config.setdefault('notification', {})['slack_token'] = os.environ['SLACK_TOKEN']
    
    # Validate configuration
    if not config.get('gitlab', {}).get('token'):
        print("Error: GitLab token is required")
        sys.exit(1)
    
    if not config.get('notification', {}).get('slack_token') and SLACK_AVAILABLE:
        print("Error: Slack token is required for notifications")
        sys.exit(1)
        
    return config


def get_default_branch(project):
    """Get the default branch for a GitLab project."""
    try:
        return project.default_branch
    except:
        # Fall back to main or master if we can't get the default branch
        try:
            project.branches.get('main')
            return 'main'
        except:
            try:
                project.branches.get('master')
                return 'master'
            except:
                print("Could not determine default branch, using 'main'")
                return 'main'


def get_codeowners_from_repo(gl, repo_name, mr_info=None):
    """Get current CODEOWNERS information from the repository.
    
    Args:
        gl: GitLab client instance
        repo_name: Repository name (namespace/project)
        mr_info: Optional merge request info with 'source_branch' for MR-specific CODEOWNERS
        
    Returns:
        List of reviewer usernames
    """
    try:
        # Get the project
        project = gl.projects.get(repo_name)
        
        # Determine which branch to use
        branch = None
        if mr_info and mr_info.get('source_branch'):
            branch = mr_info.get('source_branch')
        
        # If no branch specified or branch doesn't exist, use default branch
        if not branch:
            branch = get_default_branch(project)
            
        print(f"Looking for CODEOWNERS in branch: {branch}")
        
        # Try to find CODEOWNERS file
        codeowners_content = None
        for path in ["CODEOWNERS", ".gitlab/CODEOWNERS", "docs/CODEOWNERS"]:
            try:
                file_info = project.files.get(path, ref=branch)
                codeowners_content = file_info.decode().decode('utf-8')
                print(f"Found CODEOWNERS at {path}")
                break
            except Exception as e:
                continue
        
        if not codeowners_content:
            print(f"No CODEOWNERS file found in {repo_name}")
            
            # Fall back to checking for rotation_state.json
            try:
                from rotate import load_rotation_state  # Import here to avoid circular dependency
                
                # Try to load the rotation state to get current reviewers
                config = load_config()
                state = load_rotation_state(config)
                if state and 'reviewers' in state and state['reviewers']:
                    print(f"Using reviewers from rotation state: {', '.join(state['reviewers'])}")
                    return state['reviewers']
            except Exception as e:
                print(f"Could not load reviewers from rotation state: {e}")
            
            return []
        
        # Extract reviewer usernames
        reviewers = []
        for line in codeowners_content.splitlines():
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            
            # Extract usernames (format: "* @user1 @user2")
            parts = line.split()
            for part in parts:
                if part.startswith("@"):
                    reviewers.append(part[1:])  # Remove @
        
        # Remove duplicates while preserving order
        unique_reviewers = []
        for reviewer in reviewers:
            if reviewer not in unique_reviewers:
                unique_reviewers.append(reviewer)
        
        return unique_reviewers
        
    except Exception as e:
        print(f"Error getting CODEOWNERS from {repo_name}: {e}")
        return []


def map_gitlab_to_slack(username, user_mapping):
    """Map a GitLab username to a Slack user ID using explicit mapping.
    
    Args:
        username: GitLab username
        user_mapping: Dictionary mapping GitLab usernames to Slack user IDs
        
    Returns:
        Slack user ID or None if not found in mapping
    """
    if not user_mapping:
        return None
        
    if username in user_mapping:
        slack_id = user_mapping[username]
        print(f"Found Slack user in mapping for {username}: {slack_id}")
        return slack_id
    
    print(f"No mapping found for GitLab user: {username}")
    return None


def notify_slack(slack_client, reviewers, mr_info, fallback_channel=None):
    """Send notification to reviewers via Slack.
    
    Args:
        slack_client: Slack WebClient instance
        reviewers: List of Slack user IDs to notify
        mr_info: Merge request information
        fallback_channel: Optional channel ID for fallback
        
    Returns:
        True if any notification was sent successfully
    """
    if not SLACK_AVAILABLE or not slack_client:
        print("Slack notifications not available")
        return False
    
    if not reviewers and not fallback_channel:
        print("No reviewers or fallback channel specified")
        return False
    
    # Format message blocks
    repo_name = mr_info.get('repo')
    mr_title = mr_info.get('title', 'Untitled merge request')
    mr_url = mr_info.get('url', '#')
    mr_author = mr_info.get('author', 'Unknown')
    mr_id = mr_info.get('id', 'Unknown')
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔄 Revisão Necessária",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Uma MR em *{repo_name}* requer sua revisão.\n\n*Título:* {mr_title}\n*Autor:* {mr_author}"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Ver MR",
                        "emoji": True
                    },
                    "url": mr_url,
                    "style": "primary",
                    "action_id": "view_mr"
                }
            ]
        }
    ]
    
    # Send to each reviewer
    successful = False
    notified_users = []
    
    for user_id in reviewers:
        try:
            # Open DM channel
            response = slack_client.conversations_open(users=user_id)
            if not response['ok']:
                print(f"Failed to open DM with user {user_id}: {response['error']}")
                continue
                
            channel_id = response['channel']['id']
            
            # Send message
            slack_client.chat_postMessage(
                channel=channel_id,
                text=f"Revisão necessária para MR em {repo_name}",
                blocks=blocks
            )
            
            print(f"Sent notification to Slack user {user_id}")
            successful = True
            notified_users.append(user_id)
            
        except SlackApiError as e:
            print(f"Error sending Slack notification to {user_id}: {e}")
    
    # Fall back to channel if no direct messages were sent
    if not successful and fallback_channel:
        try:
            # Add note about fallback
            fallback_blocks = blocks.copy()
            fallback_blocks.insert(1, {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚠️ *Não foi possível notificar os revisores diretamente.*"
                }
            })
            
            # Send to fallback channel
            try:
                # Send directly to the channel by name (with or without #)
                channel_name = fallback_channel
                if channel_name.startswith('#'):
                    channel_name = channel_name[1:]
                
                print(f"Sending to fallback channel: {channel_name}")
                
                # Try posting message
                slack_client.chat_postMessage(
                    channel=channel_name,
                    text=f"Revisão necessária para MR em {repo_name}",
                    blocks=fallback_blocks
                )
                
                print(f"Sent notification to fallback channel {fallback_channel}")
                successful = True
            except SlackApiError as e:
                error_message = e.response.get('error', 'unknown_error')
                print(f"Error sending to channel by name: {error_message}")
                
                # If channel name didn't work, try these fallbacks
                if error_message == "channel_not_found":
                    print("Trying to find channel by listing channels...")
                    try:
                        # Try to find channel ID from name
                        channels_response = slack_client.conversations_list(types="public_channel,private_channel")
                        for channel in channels_response.get('channels', []):
                            if channel['name'] == channel_name:
                                # Found the channel, try posting again
                                slack_client.chat_postMessage(
                                    channel=channel['id'],
                                    text=f"Revisão necessária para MR em {repo_name}",
                                    blocks=fallback_blocks
                                )
                                print(f"Sent notification to fallback channel {channel['name']} ({channel['id']})")
                                successful = True
                                break
                    except SlackApiError as e2:
                        print(f"Error listing channels: {e2}")
            
        except Exception as e:
            print(f"Error sending to fallback channel: {e}")
            print("IMPORTANT: Please ensure the fallback_channel name is correct and the bot is a member of the channel")
    
    return successful


def main():
    parser = argparse.ArgumentParser(description='Notify CODEOWNERS about merge requests via Slack')
    parser.add_argument('--config', '-c', help='Path to config file')
    parser.add_argument('--repo', '-r', required=True, help='Repository name (namespace/project)')
    parser.add_argument('--mr-id', '-m', required=True, help='Merge request ID')
    parser.add_argument('--mr-title', '-t', required=True, help='Merge request title')
    parser.add_argument('--mr-url', '-u', required=True, help='Merge request URL')
    parser.add_argument('--mr-author', '-a', required=True, help='Merge request author')
    parser.add_argument('--mr-source-branch', '-b', help='Merge request source branch')
    parser.add_argument('--force-notify', '-f', action='store_true', help='Force notification to fallback channel even if no reviewers found')
    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)
    
    # Prepare MR info
    mr_info = {
        'repo': args.repo,
        'id': args.mr_id,
        'title': args.mr_title,
        'url': args.mr_url,
        'author': args.mr_author,
        'source_branch': args.mr_source_branch
    }

    # Setup GitLab client
    try:
        gl = gitlab.Gitlab(url=config['gitlab']['url'], private_token=config['gitlab']['token'])
        gl.auth()
        print(f"Authenticated with GitLab at {config['gitlab']['url']}")
    except Exception as e:
        print(f"Error connecting to GitLab: {e}")
        sys.exit(1)
    
    # Setup Slack client
    slack_client = None
    if SLACK_AVAILABLE:
        try:
            slack_token = config.get('notification', {}).get('slack_token')
            if slack_token:
                slack_client = WebClient(token=slack_token)
                test = slack_client.auth_test()
                print(f"Authenticated with Slack as {test['user']}")
        except Exception as e:
            print(f"Error connecting to Slack: {e}")
    
    # Get CODEOWNERS from the repository
    codeowners = get_codeowners_from_repo(gl, args.repo, mr_info)
    
    if not codeowners and not args.force_notify:
        print("No reviewers found in CODEOWNERS")
        sys.exit(1)
    
    if codeowners:
        print(f"Found reviewers in CODEOWNERS: {', '.join(codeowners)}")
    
    # Map GitLab users to Slack users using explicit mapping
    slack_users = []
    user_mapping = config.get('notification', {}).get('user_mapping', {})
    fallback_channel = config.get('notification', {}).get('fallback_channel')
    
    if not user_mapping:
        print("Warning: No user_mapping configured in config.yaml")
        print("You must add a 'user_mapping' section to map GitLab users to Slack IDs")
    
    for username in codeowners:
        slack_id = map_gitlab_to_slack(username, user_mapping)
        if slack_id:
            slack_users.append(slack_id)
    
    # Send notification
    if slack_client and (slack_users or fallback_channel):
        if notify_slack(slack_client, slack_users, mr_info, fallback_channel):
            print("Notification sent successfully")
        else:
            print("Failed to send notification")
            sys.exit(1)
    else:
        print("No Slack users found to notify and no fallback channel configured")
        sys.exit(1)


if __name__ == "__main__":
    main()
