#!/bin/bash

# Read JSON and generate markdown
cat rpcs.json | jq -r '
  # Separate into mainnet and testnet
  (["## Supported Mainnet Networks", "", "| Network ID | Chain | Name |", "|------------|-------|------|"] + 
  ([.[] | select(.isTestnet == false) | 
  "| \(.networkId // .chainId) | \(.chain) | \(.name) |"]) + 
  ["", "## Supported Testnet Networks", "", "| Network ID | Chain | Name |", "|------------|-------|------|"] + 
  ([.[] | select(.isTestnet == true) | 
  "| \(.networkId // .chainId) | \(.chain) | \(.name) |"])) | .[]
' > chainlist.md

echo "Generated chainlist.md with $(grep -c "^|" chainlist.md) networks"
