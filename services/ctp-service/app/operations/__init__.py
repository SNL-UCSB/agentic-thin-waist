# app/operations — CTP pipeline operation modules.
#
# Modules in this package implement the six pipeline steps:
#   pcap_split   — Step 1: split gateway PCAPs by internal IP address
#   window_split — Step 2: split per-user PCAPs into fixed time windows
#   metrics      — Step 3 helper: compute statistical descriptors
#   extract      — Steps 1-5 orchestrator (PCAP → PostgreSQL)
#   select       — Select operation: query CTP corpus
#   transform    — Transform operation: adapt CTP to target capacity
#   merge        — Merge operation: concatenate windows / compose CTPs
#   export       — Export operation: replay-ready PCAP for Substrate Worker
