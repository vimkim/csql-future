# Show available commands.
default:
    @just --list

# Install or refresh both user-level commands.
sync:
    uv tool install --reinstall .
    @"$(uv tool dir --bin)/csql-future" --version
    @"$(uv tool dir --bin)/csqlf" --version

# Verify the packaged launcher through external processes and pseudo-terminals.
test:
    uv run python -m unittest discover -s tests -v

# Build standalone wheel and source distributions.
build:
    uv build
