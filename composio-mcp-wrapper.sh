#!/bin/bash
# Wrapper to start Composio MCP server with proper API key
export COMPOSIO_API_KEY="uak_zwBd4-GiasWKW7yedRYW"
export PATH="$HOME/.plumbus/node_modules/.bin:/usr/local/bin:/Users/jos/.local/degit-external/bin:$HOME/.composio:$PATH"
exec composio-mcp-server
