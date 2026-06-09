# SolarPro Secrets — Bootstrap Operations

**Phase 1b — owner-present operation.** Reference: `docs/SECRETS_ENGINE_PROPOSAL_v3.md` §2.3.

This document covers the *bootstrap* credential tier — the credential that proves the app to Vault. The Vault key-management ceremony documented here cannot be performed without owner attention, because the 5 Shamir unseal keys must be captured offline at init time.

---

## 1. Threat tier — why bootstrap is separate

Two credential layers exist in v3:

| Layer | Examples | Tier |
|---|---|---|
| **Bootstrap** | `VAULT_ADDR`, `VAULT_ROLE_ID`, `VAULT_SECRET_ID` | Permanent (rotated hourly, narrow scope) |
| **Application** | Paystack secret, Brevo key, Flask SECRET_KEY, seed passwords | CRITICAL / DEGRADED per `_TIER` |

The owner's literal "no permanent secret credential" requirement is met for the *application* layer (via Vault KV + dynamic DB engine in Phase 3.1). The *bootstrap* layer remains permanent — but is scoped narrowly (Vault login only, hourly rotation, AppRole revocable) and is documented as non-compliance against the literal spec.

---

## 2. One-time setup — Vault container + unseal ceremony

### 2.1 Prerequisites
- Docker Desktop running.
- This repo cloned and on the relevant branch.
- A working `.env` (this session already has the seed passphrases + SMTP creds).

### 2.2 Bring up the sealed container

```bash
# from C:\Users\USER\Desktop\solar-pv-designer-lite
docker compose -f docker-compose.vault.yml up -d
docker exec solarpro-vault vault status   # expect: Initialized=false, Sealed=true
```

### 2.3 Initialize — capture 5 unseal keys offline

**OWNER-PRESENT.** The output of this command contains the 5 Shamir keys + the initial root token. Owner must capture them into an offline store (password manager + paper + USB ideally). Do NOT save to any file in this repo. Do NOT echo into a shell whose history is persisted.

```bash
docker exec -it solarpro-vault vault operator init \
    -key-shares=5 -key-threshold=3
```

Output looks like:
```
Unseal Key 1: <base64...>
Unseal Key 2: <base64...>
Unseal Key 3: <base64...>
Unseal Key 4: <base64...>
Unseal Key 5: <base64...>

Initial Root Token: hvs.<...>
```

Owner copies all six values into offline storage. Closes the terminal that ran this command.

### 2.4 Unseal — feed 3 of 5 keys

```bash
docker exec -it solarpro-vault vault operator unseal <key1>
docker exec -it solarpro-vault vault operator unseal <key2>
docker exec -it solarpro-vault vault operator unseal <key3>
```

`vault status` now shows `Sealed=false`.

### 2.5 Audit devices — enable BOTH (v3 N4 satisfied)

```bash
export VAULT_TOKEN=<initial root token from §2.3>
docker exec -e VAULT_TOKEN solarpro-vault vault audit enable \
    -path=file file file_path=/vault/audit/audit.log
docker exec -e VAULT_TOKEN solarpro-vault vault audit enable \
    -path=socket socket address=127.0.0.1:9090 socket_type=tcp
```

If either of these fails, STOP and investigate — single-device Vault is the N4 trap we explicitly want to avoid.

### 2.6 KV v2 engine — `solarpro/` mount

```bash
docker exec -e VAULT_TOKEN solarpro-vault vault secrets enable \
    -path=kv -version=2 kv
```

---

## 3. Write the application secrets

Each line is one secret. Source values are in your local `.env` — the broker's `_ENV_MAP` matches this layout.

```bash
# Auth-critical seeds (CRITICAL tier)
vault kv put kv/solarpro/seed/admin     password="$SOLARPRO_ADMIN_PASSWORD"
vault kv put kv/solarpro/seed/marc667us password="$SOLARPRO_OWNER_PASSWORD"

# Flask SECRET_KEY (CRITICAL)
vault kv put kv/solarpro/flask/secret_key secret_key="$SECRET_KEY"

# Payment (CRITICAL)
vault kv put kv/solarpro/payment/paystack \
    secret="$PAYSTACK_SECRET_KEY" \
    public="$PAYSTACK_PUBLIC_KEY"

# Email — DEGRADED tier (Brevo, Resend, SMTP)
vault kv put kv/solarpro/email/brevo  api_key="$BREVO_API_KEY"
vault kv put kv/solarpro/email/resend api_key="$RESEND_API_KEY"
vault kv put kv/solarpro/email/smtp \
    host="$SMTP_HOST" port="$SMTP_PORT" \
    user="$SMTP_USER" pass="$SMTP_PASS" \
    from="$SMTP_FROM" tls="$SMTP_TLS"

# AI — DEGRADED
vault kv put kv/solarpro/ai/openrouter api_key="$OPENROUTER_API_KEY"
vault kv put kv/solarpro/ai/ollama url="$OLLAMA_URL" model="$OLLAMA_MODEL"
```

Excluded by design (v3 §2.4): `OLLAMA_URL` is itself a Cloudflare tunnel URL (rotates per machine restart); we still write it for now but it will be migrated to a named-tunnel workstream. `RENDER_API_KEY` stays in GitHub Secrets (deploy-time, not runtime).

---

## 4. AppRole — issue the app a bootstrap credential

```bash
# Enable AppRole auth
vault auth enable approle

# Policy that allows reading exactly the paths the app uses
cat <<'EOF' | docker exec -i -e VAULT_TOKEN solarpro-vault vault policy write solarpro-app -
path "kv/data/solarpro/*" { capabilities = ["read"] }
path "sys/leases/renew" { capabilities = ["update"] }
EOF

# Create the role with TTLs that match the broker's design
vault write auth/approle/role/solarpro-app \
    token_policies="solarpro-app" \
    token_ttl=1h token_max_ttl=24h \
    secret_id_ttl=1h secret_id_num_uses=0

# Pull role_id (stable) + a fresh secret_id (rotated hourly in Phase 2)
ROLE_ID=$(vault read -format=json auth/approle/role/solarpro-app/role-id | jq -r .data.role_id)
SECRET_ID=$(vault write -force -format=json auth/approle/role/solarpro-app/secret-id | jq -r .data.secret_id)
```

Add to local `.env`:

```
VAULT_ADDR=http://127.0.0.1:8200
VAULT_ROLE_ID=<from above>
VAULT_SECRET_ID=<from above>
```

DO NOT add `VAULT_TOKEN` to `.env`. The root token is only for setup; the app uses AppRole. After bootstrap, revoke or store the root token offline.

---

## 5. Verify

```bash
# Restart the app — it now picks up VAULT_ADDR + AppRole creds
python -u start.py > solar_start.log 2>&1 &

# Confirm broker is actually hitting Vault (not env warm-up)
sqlite3 solar.db \
    "SELECT operation, path, auth_method FROM secret_audit ORDER BY id DESC LIMIT 10"
# expect: operation='vault_read', auth_method='approle'
```

If `auth_method='env'` shows up, the broker is still falling through to `.env` — investigate `VAULT_ADDR` env propagation.

---

## 6. Rotation cadence (Phase 2 deliverable — documented here for completeness)

- `secret_id`: hourly via `scripts/vault_secret_id_rotator.py` (cron entry).
- `role_id`: never rotates without re-creating the role.
- Application KV values: per-secret cadence:
  - Paystack secret: per quarter or on demand.
  - Brevo / Resend keys: per provider rotation event.
  - `SOLARPRO_*_PASSWORD`: per existing `rotate-admin-password.yml` workflow — write to Vault AND keep `.env` synced until Phase 2 removes env fallthrough.

---

## 7. Disaster recovery — unseal key loss

- Loss of any one unseal key: tolerable — 3-of-5 threshold means 2 spares.
- Loss of three keys: **Vault unrecoverable.** Encrypted KV data on disk is gone. Recovery = reseed from `.env` + GitHub Secrets, re-init Vault from scratch.
- This is the primary reason for 5-share / 3-threshold + multi-location offline storage.

---

## 8. Rollback to pre-Vault (kill switch)

```bash
# Unset the broker's pointer
sed -i '/^VAULT_ADDR=/d;/^VAULT_ROLE_ID=/d;/^VAULT_SECRET_ID=/d' .env

# Restart the app — broker falls back to env warm-up via DEGRADED tier
python -u start.py > solar_start.log 2>&1 &
```

The app comes UP without Vault because Phase 1a's broker tier=DEGRADED honors env fallthrough. Vault container can be stopped:

```bash
docker compose -f docker-compose.vault.yml down
```

Total rollback time: ~2 minutes. Application secrets stay in `.env` as the source of truth for rollback scenarios.

---

**End of bootstrap doc.** Owner runs §2.1 through §4 to bring Vault online; broker takes over automatically once `VAULT_ADDR` is set.
