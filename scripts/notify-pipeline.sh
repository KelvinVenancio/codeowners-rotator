#!/bin/bash
set -e

# This script is designed to be run in a GitLab CI pipeline
# It extracts MR information from CI variables and calls the notify.py script

# Check for required environment variables
if [ -z "$GITLAB_TOKEN" ]; then
  echo "Error: GITLAB_TOKEN environment variable is required"
  exit 1
fi

if [ -z "$SLACK_TOKEN" ]; then
  echo "Error: SLACK_TOKEN environment variable is required"
  exit 1
fi

# Default config path
CONFIG_PATH=${CONFIG_PATH:-/app/config/config.yaml}

# Extract GitLab CI environment variables
REPO_NAME=${CI_PROJECT_PATH}
MR_ID=${CI_MERGE_REQUEST_IID}
MR_TITLE=${CI_MERGE_REQUEST_TITLE}
MR_URL=${CI_MERGE_REQUEST_URL}
MR_AUTHOR=${GITLAB_USER_LOGIN}
MR_SOURCE_BRANCH=${CI_MERGE_REQUEST_SOURCE_BRANCH_NAME}

# Check for required MR information
if [ -z "$REPO_NAME" ] || [ -z "$MR_ID" ] || [ -z "$MR_TITLE" ] || [ -z "$MR_URL" ] || [ -z "$MR_AUTHOR" ]; then
  echo "Error: Missing required merge request information"
  echo "This script should be run in a merge request pipeline"
  exit 1
fi

echo "Sending notification for MR #${MR_ID} in ${REPO_NAME}"
echo "Title: ${MR_TITLE}"
echo "Author: ${MR_AUTHOR}"
echo "Source Branch: ${MR_SOURCE_BRANCH}"

# Run the notification script
python3 notify.py \
  --config "$CONFIG_PATH" \
  --repo "$REPO_NAME" \
  --mr-id "$MR_ID" \
  --mr-title "$MR_TITLE" \
  --mr-url "$MR_URL" \
  --mr-author "$MR_AUTHOR" \
  --mr-source-branch "$MR_SOURCE_BRANCH"

echo "Notification sent successfully"
