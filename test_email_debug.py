import requests, re

BASE = "https://solarpro.aiappinvent.com"
s = requests.Session()

def get_csrf(url):
    r = s.get(url, timeout=20)
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', r.text)
    return m.group(1) if m else ""

def post(url, data):
    token = get_csrf(url)
    if token: data = dict(data); data["_csrf"] = token
    return s.post(url, data=data, allow_redirects=True, timeout=40)

s.get(BASE + "/", timeout=60)
post(BASE + "/login", {"username": "admin", "password": "SolarAdmin2026!"})

# Use project 1 (should have results)
r = s.get(BASE + "/project/1/email", timeout=30)
print("Status:", r.status_code)
with open("email_debug.txt", "w", encoding="utf-8", errors="replace") as f:
    f.write(r.text)
# Print first 2000 chars ASCII-safe
print(r.text.encode('ascii','replace').decode('ascii')[:2000])
