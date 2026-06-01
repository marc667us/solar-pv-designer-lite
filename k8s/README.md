# SolarPro Global — Kubernetes Infrastructure

## Environment Strategy

| Environment | Namespace | Backend Pods | Max Pods | Neon Branch |
|-------------|-----------|-------------|----------|-------------|
| Development | `solar-dev` | 1 | 2 | `solar-dev` |
| Staging | `solar-staging` | 2 | 5 | `solar-staging` |
| Production | `solar-production` | 3 minimum | 20 | `solar-production` |

## Directory Structure

```
k8s/
├── base/                        # Shared base manifests
│   ├── namespace.yaml           # All 3 namespaces
│   ├── configmap.yaml           # Non-secret env settings
│   ├── secret-template.yaml     # Secret key reference (no real values)
│   ├── backend-deployment.yaml  # Flask/gunicorn backend
│   ├── backend-service.yaml     # ClusterIP service (load balancer)
│   ├── redis-deployment.yaml    # Redis cache + queue broker
│   ├── celery-deployment.yaml   # Celery background worker
│   ├── ingress.yaml             # Nginx ingress + TLS
│   ├── hpa.yaml                 # Horizontal Pod Autoscaler
│   └── network-policy.yaml      # Zero-trust pod networking
├── dev/
│   └── kustomization.yaml       # Dev overlay: 1 pod, debug logs, dev domain
├── staging/
│   └── kustomization.yaml       # Staging overlay: 2 pods, HPA max 5
└── production/
    ├── kustomization.yaml       # Production overlay: 3 pods, HPA max 20
    └── poddisruptionbudget.yaml # Min 2 backend pods during maintenance
```

## Quick Deploy

### Prerequisites
- `kubectl` configured for your cluster
- `kustomize` installed (or `kubectl` v1.14+ with `-k` flag)
- Secrets populated in cluster (see below)

### 1. Create Namespaces
```bash
kubectl apply -f k8s/base/namespace.yaml
```

### 2. Create Secrets (production example)
```bash
# Copy and fill in real values
cp k8s/base/secret-template.yaml /tmp/secrets-prod.yaml
# Edit /tmp/secrets-prod.yaml with real values
kubectl apply -f /tmp/secrets-prod.yaml -n solar-production
# NEVER commit secrets-prod.yaml to git
```

### 3. Deploy to Development
```bash
kubectl apply -k k8s/dev/
```

### 4. Deploy to Staging
```bash
kubectl apply -k k8s/staging/
```

### 5. Deploy to Production (from CI/CD only — requires manual approval)
```bash
# This runs automatically via GitHub Actions on tagged release
# Manual trigger:
kubectl apply -k k8s/production/
```

## Scaling

### Manual scale (emergency)
```bash
kubectl scale deployment solarpro-backend -n solar-production --replicas=10
```

### Check HPA status
```bash
kubectl get hpa -n solar-production
```

### Check pod distribution
```bash
kubectl get pods -n solar-production -o wide
```

## Rollback
```bash
# Roll back to previous deployment
kubectl rollout undo deployment/solarpro-backend -n solar-production

# Roll back to specific revision
kubectl rollout history deployment/solarpro-backend -n solar-production
kubectl rollout undo deployment/solarpro-backend -n solar-production --to-revision=2
```

## Health Checks
```bash
# Check backend health via cluster
kubectl port-forward service/solarpro-backend-service 8080:80 -n solar-production
curl http://localhost:8080/api/health

# Check all pods are healthy
kubectl get pods -n solar-production -l app=solarpro-backend
```

## Logs
```bash
# Stream backend logs
kubectl logs -f deployment/solarpro-backend -n solar-production

# Stream specific pod
kubectl logs -f <pod-name> -n solar-production

# Celery worker logs
kubectl logs -f deployment/solarpro-celery-worker -n solar-production
```

## Request Flow

```
Internet
    ↓
solarpro.aiappinvent.com (DNS)
    ↓
Nginx Ingress Controller (TLS termination, rate limiting, security headers)
    ↓
solarpro-backend-service (ClusterIP, distributes to all healthy pods)
    ↓
solarpro-backend pods (Flask/gunicorn, stateless, 3-20 replicas)
    ↓ (heavy tasks)
Redis Queue → Celery Workers → Neon PostgreSQL
    ↓ (external APIs)
Paystack / Stripe / Anthropic / OpenRouter / Resend
```
