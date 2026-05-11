"""
AgentShield Landing Page
Serves the marketing site + demo proxy + self-serve signup + customer dashboard + status monitor.
"""
import os
import time
import json
import sqlite3
import threading
import smtplib
import ssl
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse

STATIC_DIR = Path(__file__).parent
DATA_DIR = Path.home() / ".agentshield-landing"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATUS_DB = DATA_DIR / "status.db"

# Configuration (env-driven)
GATEWAY_URL = os.getenv("AGENTSHIELD_GATEWAY_URL", "http://localhost:8820")
DEMO_API_KEY = os.getenv("AGENTSHIELD_DEMO_API_KEY", "")
ADMIN_KEY_FILE = os.path.expanduser("~/.agentshield/admin_key.txt")
_ADMIN_KEY_FALLBACK = os.getenv("AGENTSHIELD_ADMIN_KEY", "")

def get_admin_key():
    """Read admin key fresh from file (auto-syncs after gateway restart)."""
    try:
        with open(ADMIN_KEY_FILE, "r") as f:
            key = f.read().strip()
            if key:
                return key
    except FileNotFoundError:
        pass
    return _ADMIN_KEY_FALLBACK
SITE_URL = os.getenv("AGENTSHIELD_SITE_URL", "https://agentshield.pro")

# SMTP (reads SMTP_* from env — share billing.env on agents-pc via EnvironmentFile)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "hello@agentshield.pro")

app = FastAPI(title="AgentShield Landing Page", docs_url=None, redoc_url=None)
http_client = httpx.AsyncClient(timeout=20.0)

# ── Analytics middleware ──────────────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

# Analytics IP rate limit: max 10 pageviews per IP per minute (blocks scrapers)
_analytics_hits: dict[str, deque] = defaultdict(deque)
_analytics_lock = threading.Lock()
_ANALYTICS_RATE_WINDOW = 60  # seconds
_ANALYTICS_RATE_MAX = 10     # max pageviews per IP per window

def _analytics_rate_ok(ip: str) -> bool:
    now = time.time()
    with _analytics_lock:
        q = _analytics_hits[ip]
        while q and q[0] < now - _ANALYTICS_RATE_WINDOW:
            q.popleft()
        if len(q) >= _ANALYTICS_RATE_MAX:
            return False
        q.append(now)
        return True

class AnalyticsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        try:
            path = request.url.path
            if path in _TRACK_PATHS and response.status_code == 200:
                ua = request.headers.get("user-agent", "")
                if not _is_bot(ua):
                    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
                    if _analytics_rate_ok(ip):
                        referrer = request.headers.get("referer", "")
                        conn = sqlite3.connect(str(ANALYTICS_DB))
                        conn.execute(
                            "INSERT INTO pageviews (ts, path, referrer, ip, user_agent, country) VALUES (?,?,?,?,?,?)",
                            (int(time.time()), path, referrer or None, ip or None, ua[:500] or None, None)
                        )
                        # Cleanup: keep 90 days
                        conn.execute("DELETE FROM pageviews WHERE ts < ?", (int(time.time()) - 90 * 86400,))
                        conn.commit()
                        conn.close()
        except Exception as e:
            print(f"[analytics] error: {e}")
        return response

app.add_middleware(AnalyticsMiddleware)


# ── In-memory IP rate limit for demo proxy (60 req/IP/hour) ─────────────────
_demo_hits: dict[str, deque] = defaultdict(deque)
_demo_lock = threading.Lock()
DEMO_RATE_WINDOW_SECONDS = 3600
DEMO_RATE_MAX = 60

# ── Analytics ─────────────────────────────────────────────────────────────────
ANALYTICS_DB = DATA_DIR / "analytics.db"
ANALYTICS_PASSWORD = os.getenv("AGENTSHIELD_ANALYTICS_PW", "")
GATEWAY_DB = Path.home() / ".agentshield" / "gateway.db"

def init_analytics_db():
    conn = sqlite3.connect(str(ANALYTICS_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pageviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            path TEXT NOT NULL,
            referrer TEXT,
            ip TEXT,
            user_agent TEXT,
            country TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pv_ts ON pageviews(ts);
        CREATE INDEX IF NOT EXISTS idx_pv_path ON pageviews(path);
    """)
    conn.close()

# Bot / crawler filter
_BOT_KEYWORDS = {"bot", "crawler", "spider", "curl", "wget", "python-requests",
                 "httpx", "go-http", "java/", "headlesschrome", "lighthouse",
                 "pingdom", "uptimerobot", "semrush", "ahref", "bytespider",
                 "gptbot", "claudebot", "bingbot", "googlebot", "yandex",
                 "baiduspider", "facebookexternalhit", "twitterbot",
                 "cms-checker", "dataprovider", "palo alto", "cortex",
                 "censys", "shodan", "nmap", "masscan", "zgrab",
                 "netcraft", "expanse", "nuclei", "httpie", "postman",
                 "scrapy", "phantomjs", "selenium", "puppeteer", "playwright"}

def _is_bot(ua: str) -> bool:
    ua_lower = (ua or "").lower()
    return any(kw in ua_lower for kw in _BOT_KEYWORDS)

# Pages we want to track (not static assets, not API calls)
_TRACK_PATHS = {"/", "/blog", "/benchmark", "/compare", "/self-hosted",
                "/security", "/signup", "/account", "/status", "/dashboard",
                "/pricing", "/terms", "/privacy", "/refund",
                "/blog/benchmark", "/blog/mythos", "/blog/hijacked",
                "/blog/multi-agent-frontier", "/blog/ncsc-perfect-storm", "/blog/tutorial-5min"}


def demo_rate_ok(ip: str) -> bool:
    now = time.time()
    with _demo_lock:
        q = _demo_hits[ip]
        while q and q[0] < now - DEMO_RATE_WINDOW_SECONDS:
            q.popleft()
        if len(q) >= DEMO_RATE_MAX:
            return False
        q.append(now)
        return True


# ── Status monitor ────────────────────────────────────────────────────────────
def init_status_db():
    conn = sqlite3.connect(str(STATUS_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            status TEXT NOT NULL,
            latency_ms REAL,
            detail TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ts ON checks(ts);
    """)
    conn.close()


def status_worker():
    import time as _t
    import urllib.request
    import urllib.error

    while True:
        try:
            t0 = _t.time()
            try:
                req = urllib.request.Request(f"{GATEWAY_URL}/health")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read().decode()
                    latency = (_t.time() - t0) * 1000
                    body = json.loads(data)
                    cls_ok = body.get("classifier") == "ok"
                    status = "operational" if cls_ok else "degraded"
                    detail = data
            except urllib.error.URLError as e:
                latency = (_t.time() - t0) * 1000
                status = "down"
                detail = str(e)
            except Exception as e:
                latency = None
                status = "down"
                detail = str(e)

            conn = sqlite3.connect(str(STATUS_DB))
            conn.execute(
                "INSERT INTO checks (ts, status, latency_ms, detail) VALUES (?,?,?,?)",
                (int(_t.time()), status, latency, detail),
            )
            conn.execute("DELETE FROM checks WHERE ts < ?", (int(_t.time()) - 40 * 86400,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[status] worker error: {e}")
        _t.sleep(60)


@app.on_event("startup")
async def _startup():
    init_analytics_db()
    init_status_db()
    t = threading.Thread(target=status_worker, daemon=True, name="status-worker")
    t.start()
    print(f"[landing] started | gateway={GATEWAY_URL} | demo_key={'yes' if DEMO_API_KEY else 'MISSING'}")


# ── Page routes ──────────────────────────────────────────────────────────────
def page(name: str):
    return FileResponse(STATIC_DIR / name, media_type="text/html")


@app.get("/")
async def index():
    return page("index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "landing-page"}


@app.get("/dashboard")
async def dashboard():
    return page("dashboard.html")


@app.get("/blog")
async def blog():
    return page("blog.html")


@app.get("/benchmark")
async def benchmark():
    return page("benchmark.html")


@app.get("/blog/benchmark")
async def blog_benchmark():
    return page("blog-benchmark.html")


@app.get("/blog/mythos")
async def blog_mythos():
    return page("blog-mythos.html")


@app.get("/blog/hijacked")
async def blog_hijacked():
    return page("blog-hijacked.html")


@app.get('/blog/multi-agent-frontier')
async def blog_multi_agent():
    return page('blog-multi-agent-frontier.html')




@app.get('/security')
async def security_page():
    return FileResponse('/opt/agentshield-landing/security-compliance.html')

@app.get('/self-hosted')
async def self_hosted_page():
    return FileResponse('/opt/agentshield-landing/self-hosted.html')

@app.get('/blog/ncsc-perfect-storm')
async def blog_ncsc_perfect_storm():
    return page("blog-ncsc-perfect-storm.html")


@app.get('/blog/tutorial-5min')
async def blog_tutorial_5min():
    return page("blog-tutorial-5min.html")


@app.get("/compare")
async def compare():
    return page("compare.html")


@app.get("/status")
async def status_page():
    return page("status.html")


@app.get("/signup")
async def signup_page():
    return page("signup.html")


@app.get("/account")
async def account_page():
    return page("account.html")


@app.get("/billing/success")
async def billing_success():
    return page("billing-success.html")


@app.get("/billing/cancel")
async def billing_cancel():
    return RedirectResponse(url="/#pricing")


@app.get("/terms")
async def terms():
    return page("terms.html")


@app.get("/privacy")
async def privacy():
    return page("privacy.html")


@app.get("/refund")
async def refund():
    return page("refund.html")


@app.get("/googlef11c3da79495d3fa.html")
async def google_verify():
    return page("googlef11c3da79495d3fa.html")


@app.get("/pricing")
async def pricing_redirect():
    return RedirectResponse(url="/#pricing")


# ── SEO ──────────────────────────────────────────────────────────────────────
@app.get("/robots.txt")
async def robots():
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /account\n"
        "Disallow: /billing/\n"
        "Disallow: /api/\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )
    return PlainTextResponse(body, media_type="text/plain")


@app.api_route("/llms.txt", methods=["GET", "HEAD"])
async def llms_txt():
    """LLM-facing discovery document. See https://llmstxt.org for the emerging spec.
    Served as text/plain so crawlers (and agents doing web_fetch) get a clean read.
    HEAD is supported so crawlers can probe Content-Type before a full GET."""
    return FileResponse(STATIC_DIR / "llms.txt", media_type="text/plain; charset=utf-8")


@app.get("/sitemap.xml")
async def sitemap():
    urls = [
        ("/", "1.0", "weekly"),
        ("/blog", "0.9", "weekly"),
        ("/blog/benchmark", "0.9", "monthly"),
        ("/blog/mythos", "0.9", "weekly"),
        ("/blog/hijacked", "0.8", "monthly"),
        ("/security", "0.7", "monthly"),
        ("/self-hosted", "0.8", "weekly"),
        ("/blog/multi-agent-frontier", "0.9", "weekly"),
        ("/blog/ncsc-perfect-storm", "0.9", "weekly"),
        ("/blog/tutorial-5min", "0.9", "weekly"),
        ("/benchmark", "0.9", "weekly"),
        ("/compare", "0.8", "monthly"),
        ("/status", "0.5", "hourly"),
        ("/signup", "0.7", "monthly"),
        ("/terms", "0.3", "yearly"),
        ("/privacy", "0.3", "yearly"),
        ("/refund", "0.3", "yearly"),
    ]
    from datetime import date
    today = date.today().isoformat()
    items = "\n".join(
        f"  <url><loc>{SITE_URL}{p}</loc><changefreq>{c}</changefreq><priority>{pr}</priority><lastmod>{today}</lastmod></url>"
        for p, pr, c in urls
    )
    body = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
{items}
</urlset>
"""
    return PlainTextResponse(body, media_type="application/xml")


# ── Demo proxy ───────────────────────────────────────────────────────────────
@app.post("/api/demo")
async def demo_classify(request: Request):
    ip = request.client.host if request.client else "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()

    if not demo_rate_ok(ip):
        raise HTTPException(
            status_code=429,
            detail={"error": "demo_rate_limit", "message": f"Demo limit of {DEMO_RATE_MAX}/hour reached. Sign up for a free API key to keep going."},
        )

    if not DEMO_API_KEY:
        raise HTTPException(status_code=503, detail={"error": "demo_unavailable", "message": "Demo temporarily unavailable. Sign up for a free API key to try it yourself."})

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail={"error": "missing_text", "message": "'text' field required"})
    if len(text) > 2000:
        raise HTTPException(status_code=413, detail={"error": "too_long", "message": "Demo limited to 2000 chars. Sign up to classify up to 10,000."})

    t0 = time.monotonic()
    try:
        resp = await http_client.post(
            f"{GATEWAY_URL}/v1/classify",
            headers={"x-api-key": DEMO_API_KEY, "Content-Type": "application/json"},
            json={"text": text},
            timeout=15.0,
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Classifier timeout")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")
    latency = (time.monotonic() - t0) * 1000

    if resp.status_code != 200:
        return JSONResponse(
            status_code=resp.status_code,
            content={"error": "upstream", "upstream_status": resp.status_code, "detail": resp.text[:500]},
        )

    data = resp.json()
    result = data.get("result", data)
    return {"result": result, "meta": {"latency_ms": round(latency, 2), "source": "demo_proxy"}}


@app.get("/api/status-data")
async def status_data():
    conn = sqlite3.connect(str(STATUS_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT ts, status, latency_ms FROM checks WHERE ts > ? ORDER BY ts DESC",
            (int(time.time()) - 30 * 86400,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"uptime_30d": None, "daily": [], "latest": None, "recent_latency": []}

    from collections import defaultdict as _dd
    from datetime import datetime, timezone
    daily = _dd(lambda: {"total": 0, "down": 0})
    for r in rows:
        day = datetime.fromtimestamp(r["ts"], tz=timezone.utc).strftime("%Y-%m-%d")
        daily[day]["total"] += 1
        if r["status"] == "down":
            daily[day]["down"] += 1

    daily_list = []
    for day in sorted(daily.keys()):
        d = daily[day]
        uptime_pct = 100.0 * (d["total"] - d["down"]) / d["total"] if d["total"] else None
        daily_list.append({"day": day, "uptime_pct": round(uptime_pct, 2) if uptime_pct is not None else None, "checks": d["total"], "down": d["down"]})

    total_checks = sum(d["total"] for d in daily.values())
    total_down = sum(d["down"] for d in daily.values())
    uptime_30d = 100.0 * (total_checks - total_down) / total_checks if total_checks else None

    latest = rows[0]
    recent_latency = [
        {"ts": r["ts"], "latency_ms": r["latency_ms"]}
        for r in rows[:120]
        if r["latency_ms"] is not None
    ]
    recent_latency.reverse()

    return {
        "uptime_30d": round(uptime_30d, 3) if uptime_30d is not None else None,
        "daily": daily_list,
        "latest": {"ts": latest["ts"], "status": latest["status"], "latency_ms": latest["latency_ms"]},
        "recent_latency": recent_latency,
    }


# ── Signup (free tier + email delivery) ──────────────────────────────────────
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _send_email(to_email: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        print(f"[email] SMTP not configured, would send to {to_email}: {subject}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"AgentShield <{NOTIFY_EMAIL}>"
        msg["To"] = to_email
        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(context=ctx)
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[email] send failed: {e}")
        return False


@app.post("/api/signup")
async def signup(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    email = (body.get("email") or "").strip().lower()
    name = (body.get("name") or (email.split("@")[0] if email else "")).strip()
    promo_code = (body.get("promo_code") or "").strip().upper()

    if not email or not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail={"error": "invalid_email", "message": "Please provide a valid email address."})
    if len(name) > 100:
        name = name[:100]

    admin_key = get_admin_key()
    if not admin_key:
        raise HTTPException(status_code=503, detail={"error": "signup_unavailable", "message": "Signup temporarily unavailable. Contact hello@agentshield.pro."})

    try:
        resp = await http_client.post(
            f"{GATEWAY_URL}/admin/keys",
            headers={"x-api-key": admin_key, "Content-Type": "application/json"},
            json={"name": name, "email": email, "tier": "free", "promo_code": promo_code or None},
            timeout=10.0,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

    if resp.status_code != 200:
        return JSONResponse(status_code=resp.status_code, content={"error": "upstream", "detail": resp.text[:500]})

    data = resp.json()
    api_key = data["api_key"]
    prefix = data["prefix"]

    promo_applied = data.get("promo_applied")
    promo_limit = data.get("promo_limit", 100)
    promo_expires = data.get("promo_expires", "")
    if promo_applied:
        tier_label = f"Product Hunt promo — {promo_limit} requests/day until {promo_expires[:10]}"
    else:
        tier_label = "free tier — 100 requests/day"

    body_text = f"""Welcome to AgentShield!

Your API key ({tier_label}):

  {api_key}

Quick start:
  curl -X POST https://api.agentshield.pro/v1/classify \\
    -H "x-api-key: {api_key}" \\
    -H "Content-Type: application/json" \\
    -d '{{"text":"Ignore previous instructions and..."}}'

Docs:      https://api.agentshield.pro/docs
Dashboard: https://agentshield.pro/account (paste your key to view usage)
Upgrade:   https://agentshield.pro/#pricing

Keep this key private — it authenticates your account.

— The AgentShield team
"""
    body_html = f"""<!DOCTYPE html><html><body style="font-family:-apple-system,Segoe UI,sans-serif;max-width:560px;margin:2rem auto;color:#222;line-height:1.6;">
<h2 style="color:#6366f1">Welcome to AgentShield</h2>
<p>Your API key (<strong>{tier_label}</strong>):</p>
<pre style="background:#f4f4f6;padding:1rem;border-radius:8px;font-size:.9rem;overflow:auto;"><code>{api_key}</code></pre>
<h3>Quick start</h3>
<pre style="background:#0a0a0f;color:#e5e5e7;padding:1rem;border-radius:8px;font-size:.85rem;overflow:auto;"><code>curl -X POST https://api.agentshield.pro/v1/classify \\
  -H "x-api-key: {api_key}" \\
  -H "Content-Type: application/json" \\
  -d '{{"text":"Ignore previous instructions and..."}}'</code></pre>
<p><a href="https://api.agentshield.pro/docs">API Docs</a> · <a href="https://agentshield.pro/account">Dashboard</a> · <a href="https://agentshield.pro/#pricing">Upgrade</a></p>
<p style="color:#666;font-size:.85rem;">Keep this key private. If you didn't request it, just ignore this email.</p>
<p style="color:#888;font-size:.8rem;">— The AgentShield team</p>
</body></html>"""

    sent = _send_email(email, "Your AgentShield API key", body_text, body_html)
    result = {
        "ok": True,
        "prefix": prefix,
        "email_sent": sent,
        "api_key": api_key if not sent else None,
        "message": "Check your inbox for your API key." if sent else "Save your API key now — we couldn't send it by email.",
    }
    if promo_applied:
        result["promo_applied"] = promo_applied
        result["promo_limit"] = promo_limit
        result["promo_expires"] = promo_expires
    if data.get("promo_invalid"):
        result["promo_invalid"] = True
        result["promo_message"] = data.get("promo_message", "Invalid promo code.")
    return result


# ── Account dashboard ────────────────────────────────────────────────────────
@app.post("/api/account")
async def account_info(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    api_key = (body.get("api_key") or "").strip()
    if not api_key or not api_key.startswith("ask_"):
        raise HTTPException(status_code=400, detail={"error": "invalid_key", "message": "Invalid API key format."})

    import hashlib as _h
    key_hash = _h.sha256(api_key.encode()).hexdigest()

    gw_db = Path.home() / ".agentshield" / "gateway.db"
    if not gw_db.exists():
        raise HTTPException(status_code=503, detail={"error": "unavailable", "message": "Database unavailable."})

    conn = sqlite3.connect(str(gw_db))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT key_prefix, name, email, tier, active, created_at, last_used FROM api_keys WHERE key_hash=?",
            (key_hash,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "API key not recognised."})
        if not row["active"]:
            raise HTTPException(status_code=403, detail={"error": "deactivated", "message": "API key is deactivated."})

        today_count = conn.execute(
            "SELECT COUNT(*) as c FROM usage_log WHERE key_hash=? AND date(timestamp)=date('now')",
            (key_hash,),
        ).fetchone()["c"]
        total_count = conn.execute(
            "SELECT COUNT(*) as c FROM usage_log WHERE key_hash=?",
            (key_hash,),
        ).fetchone()["c"]
        threats = conn.execute(
            "SELECT COUNT(*) as c FROM usage_log WHERE key_hash=? AND is_threat=1",
            (key_hash,),
        ).fetchone()["c"]
        daily_rows = conn.execute(
            """SELECT date(timestamp) as day, COUNT(*) as calls,
                      SUM(CASE WHEN is_threat=1 THEN 1 ELSE 0 END) as threats,
                      AVG(latency_ms) as avg_latency
               FROM usage_log
               WHERE key_hash=? AND timestamp > datetime('now','-14 days')
               GROUP BY date(timestamp) ORDER BY day ASC""",
            (key_hash,),
        ).fetchall()
    finally:
        conn.close()

    tier_limits = {"free": 100, "dev": 5000, "pro": 50000, "enterprise": -1}
    limit = tier_limits.get(row["tier"], 100)

    return {
        "prefix": row["key_prefix"],
        "name": row["name"],
        "email": row["email"],
        "tier": row["tier"],
        "created_at": row["created_at"],
        "last_used": row["last_used"],
        "daily_limit": limit,
        "today_used": today_count,
        "today_remaining": (limit - today_count) if limit > 0 else -1,
        "total_calls": total_count,
        "total_threats": threats,
        "daily_history": [dict(r) for r in daily_rows],
    }


# ── Checkout passthrough ─────────────────────────────────────────────────────
@app.post("/api/checkout")
async def create_checkout(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    plan = body.get("plan", "")
    email = (body.get("email") or "").strip().lower()
    if plan not in ("dev", "pro"):
        raise HTTPException(status_code=400, detail="plan must be 'dev' or 'pro'")
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="invalid email")

    try:
        resp = await http_client.post(
            f"{GATEWAY_URL}/billing/checkout",
            json={"plan": plan, "email": email, "success_url": f"{SITE_URL}/billing/success", "cancel_url": f"{SITE_URL}/billing/cancel"},
            timeout=15.0,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")
    try:
        payload = resp.json()
    except Exception:
        payload = {"error": "non_json_response", "text": resp.text[:500]}
    return JSONResponse(status_code=resp.status_code, content=payload)




# ── Admin analytics ──────────────────────────────────────────────────────────
@app.get("/admin/analytics")
async def analytics_dashboard(request: Request):
    return FileResponse(STATIC_DIR / "analytics.html", media_type="text/html")


@app.get("/api/analytics-data")
async def analytics_data(request: Request, pw: str = "", hours: int = 24):
    if pw != ANALYTICS_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    since = int(time.time()) - hours * 3600
    conn = sqlite3.connect(str(ANALYTICS_DB))
    conn.row_factory = sqlite3.Row
    try:
        # Total pageviews
        total = conn.execute("SELECT COUNT(*) as c FROM pageviews WHERE ts > ?", (since,)).fetchone()["c"]

        # Unique IPs
        unique_ips = conn.execute("SELECT COUNT(DISTINCT ip) as c FROM pageviews WHERE ts > ?", (since,)).fetchone()["c"]

        # Top pages
        top_pages = [dict(r) for r in conn.execute(
            "SELECT path, COUNT(*) as views FROM pageviews WHERE ts > ? GROUP BY path ORDER BY views DESC LIMIT 20", (since,)
        ).fetchall()]

        # Top referrers
        top_referrers = [dict(r) for r in conn.execute(
            "SELECT referrer, COUNT(*) as views FROM pageviews WHERE ts > ? AND referrer IS NOT NULL AND referrer != '' GROUP BY referrer ORDER BY views DESC LIMIT 20", (since,)
        ).fetchall()]

        # Hourly breakdown (last 48h max)
        hourly = [dict(r) for r in conn.execute(
            """SELECT (ts / 3600) * 3600 as hour_ts, COUNT(*) as views, COUNT(DISTINCT ip) as visitors
               FROM pageviews WHERE ts > ? GROUP BY hour_ts ORDER BY hour_ts ASC""", (since,)
        ).fetchall()]

        # Recent pageviews (live feed)
        recent = [dict(r) for r in conn.execute(
            "SELECT ts, path, referrer, ip, user_agent FROM pageviews WHERE ts > ? ORDER BY ts DESC LIMIT 50", (since,)
        ).fetchall()]

        # Daily breakdown
        daily = [dict(r) for r in conn.execute(
            """SELECT date(ts, 'unixepoch') as day, COUNT(*) as views, COUNT(DISTINCT ip) as visitors
               FROM pageviews WHERE ts > ? GROUP BY day ORDER BY day ASC""",
            (int(time.time()) - 30 * 86400,)
        ).fetchall()]

    finally:
        conn.close()


    # ── Signup stats from gateway DB ─────────────────────────────────────────
    signups = {"total": 0, "active": 0, "new_7d": 0, "new_24h": 0, "keys": []}
    try:
        if GATEWAY_DB.exists():
            gw = sqlite3.connect(str(GATEWAY_DB))
            gw.row_factory = sqlite3.Row
            signups["total"] = gw.execute("SELECT COUNT(*) as c FROM api_keys").fetchone()["c"]
            signups["active"] = gw.execute("SELECT COUNT(*) as c FROM api_keys WHERE active=1").fetchone()["c"]
            signups["new_7d"] = gw.execute("SELECT COUNT(*) as c FROM api_keys WHERE created_at > datetime('now', '-7 days')").fetchone()["c"]
            signups["new_24h"] = gw.execute("SELECT COUNT(*) as c FROM api_keys WHERE created_at > datetime('now', '-1 day')").fetchone()["c"]
            signups["keys"] = [dict(r) for r in gw.execute(
                "SELECT key_prefix, name, email, tier, active, created_at, last_used FROM api_keys ORDER BY created_at DESC LIMIT 20"
            ).fetchall()]
            gw.close()
    except Exception as e:
        print(f"[analytics] gateway DB error: {e}")

    return {
        "period_hours": hours,
        "total_pageviews": total,
        "unique_visitors": unique_ips,
        "top_pages": top_pages,
        "top_referrers": top_referrers,
        "hourly": hourly,
        "daily": daily,
        "recent": recent,
        "signups": signups,
    }

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8830)
