# Vault server config — production-style, sealed at boot.
# Referenced by docker-compose.vault.yml as /vault/config/vault.hcl

storage "file" {
  path = "/vault/data"
}

# UI is convenient for owner-driven KV writes during Phase 1b setup.
# Lives behind localhost-only listener; never exposed to LAN.
ui = true

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = "true"
}

# Two audit devices satisfy SECRETS_ENGINE_PROPOSAL_v3 §2.2 (N4).
# Vault BLOCKS all requests if every audit device fails to write;
# two devices is the redundancy that keeps the gate open if one fails.
#
# IMPORTANT: audit devices are not auto-enabled by the config file.
# After unseal, owner must run:
#   vault audit enable -path=file file file_path=/vault/audit/audit.log
#   vault audit enable -path=socket socket address=127.0.0.1:9090 socket_type=tcp
# See docs/SECRETS_BOOTSTRAP.md §3 for the full sequence.

api_addr     = "http://127.0.0.1:8200"
cluster_addr = "http://127.0.0.1:8201"
disable_mlock = false
