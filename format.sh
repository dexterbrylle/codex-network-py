#!/bin/bash

# Format code with black
echo "Running black formatter..."
black .

# Run flake8 for additional checks
echo "Running flake8 linter..."
flake8 .

# Exit with flake8's exit code
exit $? 