// Q-gate 3.6 — k6 load test for SolarPro login + dashboard fetch.
//
// Run: k6 run --vus 1000 --duration 5m tests/load/k6_login.js
//
// Thresholds (per Q-gate work-schedule):
//   - p95 latency < 800 ms
//   - error rate < 0.5 %
//   - DB pool < 80 % saturation (verify via /metrics during run)
//
// Defaults assume the live Render URL; override with --env BASE_URL=... .
//
// Phase 3.6 scaffolding — add /project/create + /project/<pid>/results +
// /paystack/verify scenarios in follow-up commits.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Phase 2.4 guardrails (2026-06-08): refuse to run unless BASE_URL/TEST_EMAIL/
// TEST_PASSWORD are explicitly supplied, and refuse known prod URLs. Without
// these the script could (a) DoS production at 1000 VUs and (b) silently
// fail every login on the rate-limited /login endpoint (20/hr/IP).
const BASE_URL = __ENV.BASE_URL;
const TEST_EMAIL = __ENV.TEST_EMAIL;
const TEST_PASSWORD = __ENV.TEST_PASSWORD;

const PROD_HOSTS = [
    'solarpro-global.onrender.com',
    'solarpro.aiappinvent.com',
    'web-production-744af.up.railway.app',
];

if (!BASE_URL || !TEST_EMAIL || !TEST_PASSWORD) {
    throw new Error(
        'k6_login.js refuses to start: BASE_URL, TEST_EMAIL, TEST_PASSWORD must all be set via --env. ' +
        'Example: k6 run --env BASE_URL=https://staging.example.com --env TEST_EMAIL=loadtest@example.com --env TEST_PASSWORD=... tests/load/k6_login.js'
    );
}
if (PROD_HOSTS.some(h => BASE_URL.includes(h))) {
    throw new Error(
        `k6_login.js refuses to run against known production host (${BASE_URL}). ` +
        'Either point at a staging host, or set k6 to use the same loadtest user the rate limiter exempts. ' +
        'See Phase 2.4 of SolarPro_Schedule_2026-06-08.md for context.'
    );
}

const errorRate = new Rate('errors');
const loginTime = new Trend('login_duration', true);
const dashboardTime = new Trend('dashboard_duration', true);

export const options = {
    scenarios: {
        steady_login: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '30s', target: 100  },  // ramp to 100
                { duration: '1m',  target: 500  },  // ramp to 500
                { duration: '1m',  target: 1000 },  // ramp to 1000
                { duration: '2m',  target: 1000 },  // steady at 1000
                { duration: '30s', target: 0    },  // ramp down
            ],
        },
    },
    thresholds: {
        'http_req_duration{name:login}':     ['p(95)<800'],
        'http_req_duration{name:dashboard}': ['p(95)<800'],
        'errors':                            ['rate<0.005'],
        'http_req_failed':                   ['rate<0.01'],
    },
};

export default function () {
    // 1. GET /login to grab a CSRF token
    const loginPage = http.get(`${BASE_URL}/login`, { tags: { name: 'login_page' } });
    check(loginPage, { 'login page 200': (r) => r.status === 200 }) || errorRate.add(1);

    const csrfMatch = loginPage.body.match(/name="_csrf"\s+value="([^"]+)"/);
    if (!csrfMatch) {
        errorRate.add(1);
        return;
    }
    const csrf = csrfMatch[1];

    // 2. POST /login with credentials + CSRF
    const loginStart = Date.now();
    const loginRes = http.post(
        `${BASE_URL}/login`,
        { username: TEST_EMAIL, password: TEST_PASSWORD, _csrf: csrf },
        { tags: { name: 'login' }, redirects: 0 }
    );
    loginTime.add(Date.now() - loginStart);
    const loggedIn = check(loginRes, {
        'login 302 to /dashboard': (r) => r.status === 302 && r.headers['Location']?.includes('/dashboard'),
    });
    if (!loggedIn) {
        errorRate.add(1);
        return;
    }

    const cookie = loginRes.headers['Set-Cookie'];

    // 3. GET /dashboard
    const dashStart = Date.now();
    const dashRes = http.get(`${BASE_URL}/dashboard`, {
        headers: { Cookie: cookie },
        tags: { name: 'dashboard' },
    });
    dashboardTime.add(Date.now() - dashStart);
    check(dashRes, { 'dashboard 200': (r) => r.status === 200 }) || errorRate.add(1);

    sleep(Math.random() * 2 + 1); // 1-3s think time
}
