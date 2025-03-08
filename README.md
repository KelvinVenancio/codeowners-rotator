# CodeOwners Rotator

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Version](https://img.shields.io/badge/version-0.1.0--alpha-orange)

**CodeOwners Rotator** is an automated tool to simplify reviewer management in your projects. It performs automatic rotation of CODEOWNERS across multiple repositories and notifies designated reviewers when new merge requests are created.

## 🚀 Features

- ✅ Automatic daily CODEOWNERS rotation
- ✅ Support for multiple GitLab repositories
- ✅ Slack notifications for designated reviewers when merge pipelines are executed
- ✅ Fair distribution of review load (everyone reviews before repeating)
- ✅ Automatic detection of default branch in each repository
- ✅ Containerized for easy deployment
- ✅ GitLab CI integration for automation

## 🔜 In Development (Coming Soon)

- 🚧 Support for GitHub and Bitbucket
- 🚧 Microsoft Teams notifications
- 🚧 Integration with Amazon S3 for storage

## 📋 Prerequisites

- Docker and Docker Compose
- GitLab access tokens (with API permissions)
- Slack API token (for notifications)
- GCS bucket or local storage for persistence (optional)

## ⚙️ Quick Setup

### 1. Clone this repository

```bash
git clone git@github.com:KelvinVenancio/codeowners-rotator.git
cd codeowners-rotator
```

### 2. Configure the config.yaml file

```yaml
# GitLab configuration
gitlab:
  url: https://gitlab.com/
  token: ${GITLAB_TOKEN}

# List of repositories to manage
repositories:
  - group/project1
  - group/project2

# List of eligible reviewers
reviewers:
  - user1
  - user2
  - user3
  - user4

# Number of reviewers to assign in each rotation
num_reviewers: 2

# Storage options
storage:
  type: local
  state_file: rotation_state.json

# Notification configuration
notification:
  slack_token: ${SLACK_TOKEN}
  fallback_channel: "fallback-channel"

  # Explicit mapping of GitLab users to Slack IDs
  user_mapping:
    user1: "U01ABC123D"  # Slack ID for user1
    user2: "U02DEF456E"  # Slack ID for user2
    user3: "U01ABC678D"  # Slack ID for user3
    user4: "U02DE5426E"  # Slack ID for user4
```

### 3. Run with Docker

```bash
# Export tokens as environment variables
export GITLAB_TOKEN=your_gitlab_token
export SLACK_TOKEN=your_slack_token

# Run rotation
docker-compose run rotate

# Simulation (without changes)
docker-compose run dry-run
```

## 🔄 Usage

### Manual CODEOWNERS Rotation

```bash
python rotate.py --config config.yaml
```

### Sending Notifications

```bash
python notify.py --config config.yaml \
  --repo group/project \
  --mr-id 123 \
  --mr-title "Implement feature X" \
  --mr-url "https://gitlab.com/group/project/-/merge_requests/123" \
  --mr-author "developer"
```

### Usage for Pipeline Notifications

To notify reviewers when a MR needs approval, add the following stage to your pipeline:

```yaml
include:
  - project: 'group/codeowners-rotator'
    file: '.gitlab-ci/notify-template.yml'

notify:
  extends: .notify-reviewers
```

This step will read the current CODEOWNERS file and send notifications directly to designated reviewers via Slack when the pipeline is executed.

## 📝 How to Obtain Slack IDs

To fill out the `user_mapping` in the configuration:

1. In Slack, click on the user's profile
2. Select "View profile"
3. Click on the three dots (⋮)
4. Select "Copy Member ID"

## 🔍 Troubleshooting

### Common Errors

- **GitLab Authentication Error**: Verify that the token has correct permissions
- **Slack Authentication Error**: Ensure the bot has been added to the channels
- **CODEOWNERS Not Found**: Check paths and default branches

### Required Permissions

- GitLab Token: api, read_repository, write_repository
- Slack Token: chat:write, im:write, users:read

## 📄 License

This project is licensed under the [Apache License 2.0](LICENSE).

## 🙏 Acknowledgments

- My colleagues from my SRE team
- Open source community
