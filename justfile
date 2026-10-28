# Show available commands.
default:
    @just --list

# Install or refresh an independent user-level command.
sync:
    uv tool install --reinstall .
    @"$(uv tool dir --bin)/csql-with-history" --version

# Verify the packaged launcher through external processes and pseudo-terminals.
test:
    uv run python -m unittest discover -s tests -v

# Build standalone wheel and source distributions.
build:
    uv build
