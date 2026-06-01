# Cloudflare Load Balancer & GeoDNS Configuration

## Step-by-Step Setup

### Prerequisites
- Cloudflare Pro or Business plan (Load Balancing requires paid plan)
- Domain: aiappinvent.com managed by Cloudflare
- Regional backend IPs/hostnames ready

---

## 1. Create Origin Pools

In Cloudflare Dashboard → Traffic → Load Balancing → Origin Pools:

**Pool: solarpro-af-west**
```
Name: solarpro-af-west
Origins:
  - Name: af-primary
    Address: [Your Africa West server IP or hostname]
    Weight: 1
Health Check: solarpro-health-check (defined below)
```

**Pool: solarpro-eu-west**
```
Name: solarpro-eu-west  
Origins:
  - Name: eu-primary
    Address: [Your EU server IP or Render domain]
    Weight: 1
Health Check: solarpro-health-check
```

**Pool: solarpro-us-east**
```
Name: solarpro-us-east
Origins:
  - Name: us-primary
    Address: [Your US server IP]
    Weight: 1
```

**Pool: solarpro-me-central**
```
Name: solarpro-me-central
Origins:
  - Name: me-primary
    Address: [Your Middle East server IP]
    Weight: 1
```

---

## 2. Create Health Monitor

```
Name: solarpro-health-check
Type: HTTPS
Port: 443
Path: /api/ping
Expected Status: 200
Expected Body (contains): pong
Interval: 60 seconds
Timeout: 10 seconds
Retries: 2
Follow Redirects: Yes
```

---

## 3. Create Load Balancer

```
Hostname: solarpro.aiappinvent.com
Proxied: Yes (orange cloud)
Session Affinity: None (stateless backend)
Steering Policy: Geo Steering
TTL: Auto
```

**Geo Steering Rules:**
```
Africa:        Primary: solarpro-af-west    Fallback: solarpro-eu-west
Europe:        Primary: solarpro-eu-west    Fallback: solarpro-us-east
Middle East:   Primary: solarpro-me-central Fallback: solarpro-eu-west
North America: Primary: solarpro-us-east    Fallback: solarpro-eu-west
South America: Primary: solarpro-us-east    Fallback: solarpro-eu-west
Oceania:       Primary: solarpro-eu-west    Fallback: solarpro-us-east
Default:       Primary: solarpro-eu-west    Fallback: solarpro-us-east
```

---

## 4. Cloudflare WAF Rules

In Cloudflare Dashboard → Security → WAF:

**Rule 1: Block aggressive bots**
```
(cf.client.bot) and not (cf.verified_bot_category in {"Search Engine Crawlers"})
→ Block
```

**Rule 2: Challenge login page**
```
(http.request.uri.path eq "/login" and http.request.method eq "POST" and 
 ip.src.country not in {"GH" "NG" "KE" "ZA" "GB" "DE" "US" "AE" "SA"})
→ Managed Challenge
```

**Rule 3: Rate limit AI endpoints**
```
(http.request.uri.path contains "/api/assistant" or 
 http.request.uri.path contains "/admin/agent/run")
→ Rate limit: 10 req/5min per IP
```

**Rule 4: Protect admin routes**
```
(http.request.uri.path starts_with "/admin" and 
 not ip.src in {YOUR_ADMIN_IP_ALLOWLIST})
→ Managed Challenge
```

---

## 5. Cloudflare Workers (optional — edge caching for solar data)

```javascript
// worker.js — Cache solar location data at the edge
addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  const url = new URL(request.url);
  
  // Cache solar country/region data for 24 hours at edge
  if (url.pathname.startsWith('/api/solar-data/')) {
    const cacheKey = new Request(url.toString());
    const cache = caches.default;
    let response = await cache.match(cacheKey);
    
    if (!response) {
      response = await fetch(request);
      const headers = new Headers(response.headers);
      headers.set('Cache-Control', 'public, max-age=86400');
      response = new Response(response.body, { ...response, headers });
      event.waitUntil(cache.put(cacheKey, response.clone()));
    }
    return response;
  }
  
  return fetch(request);
}
```

---

## 6. Monitoring Cloudflare Health

Check pool health in real-time:
```
Cloudflare Dashboard → Traffic → Load Balancing → [Your LB] → Pool Health
```

Set up alerting:
```
Dashboard → Notifications → Add Notification
Type: Load Balancing - Health Check status change
Notification channels: Email to marc667us@yahoo.com
```
