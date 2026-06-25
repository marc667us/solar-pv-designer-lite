# Architecture Diagrams (SOC 2 M1.9)

This directory carries the Mermaid diagrams referenced by the SOC 2 readiness
plan and the upcoming Type I audit narrative. Each file is a single concern:

| File | Concern | Audience |
|---|---|---|
| `logical.md` | Logical components, departments, services | architects + auditors |
| `network.md` | Trust boundaries, ingress, perimeters | network reviewers |
| `auth_flow.md` | OIDC PKCE end-to-end (login + logout + refresh) | security reviewers |
| `rls_layer.md` | Tenant context → GUC → RLS policy enforcement | DB reviewers |
| `cicd.md` | Source → CI → Render deploy pipeline | DevOps |

Update whenever the live topology changes (new component, new trust boundary,
new auth flow). Mermaid renders inline on GitHub.
