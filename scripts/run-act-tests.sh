#!/bin/bash

# This script runs GitHub Actions tests locally using 'act'
# Usage: ./scripts/run-act-tests.sh [job-name]
# Example: ./scripts/run-act-tests.sh mypy-3.12

# Create scripts directory if it doesn't exist
mkdir -p scripts

JOB_NAME=${1:-"mypy-3.12"}  # Default to mypy-3.12 if no job specified

echo "Running GitHub Actions job locally: $JOB_NAME"
echo "This helps debug CI/CD issues faster than waiting for GitHub Actions"

# Check if gh act is installed
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is not installed"
    echo "Install with: brew install gh (macOS) or apt install gh (Ubuntu)"
    exit 1
fi

if ! gh extension list | grep -q "act"; then
    echo "Installing gh act extension..."
    gh extension install https://github.com/nektos/gh-act
fi

# Run the specific job from our workflow
# Using pull_request event since that's what our tests run on
echo "Running job: $JOB_NAME"
gh act pull_request -j "$JOB_NAME" \
  --verbose \
  --platform ubuntu-latest=nektos/act-environments-ubuntu:18.04 \
  --platform macos-latest=nektos/act-environments-ubuntu:18.04 \
  --platform windows-latest=nektos/act-environments-ubuntu:18.04

echo "Job completed. Check output above for results."