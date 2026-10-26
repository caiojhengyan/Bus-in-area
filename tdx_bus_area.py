#!/usr/bin/env python3
"""
TDX 範圍公車紀錄 - 本機代理 (只用標準函式庫)
用法:  python tdx_bus_area.py        然後開啟 http://localhost:8765

省額度設計:
1. 全台只打「一支」API: /v2/Bus/RealTimeByFrequency/NearBy (A1, 空間篩選)，
   不必逐縣市、逐路線呼叫。
2. Token 快取到過期前 60 秒才換新 (token 不算資料 API 用量，但避免多餘請求)。
3. 伺服器端快取: 同一查詢在 MIN_INTERVAL 秒內重複請求，直接回傳快取，不再打 TDX。
4. 向 TDX 要求 gzip 壓縮。
"""
import gzip, json, os, sys, time, threading, urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", 8765))
MIN_INTERVAL = 10          # 秒；A1 資料本身約 10~30 秒才更新一次
TOKEN_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
API_URL = "https://tdx.transportdata.tw/api/basic/v2/Bus/RealTimeByFrequency/NearBy"
HERE = os.path.dirname(os.path.abspath(__file__))

state = {"id": os.environ.get("TDX_ID", ""), "secret": os.environ.get("TDX_SECRET", ""),
         "token": None, "exp": 0, "calls": 0}
cache = {}                 # key -> (timestamp, bytes)
lock = threading.Lock()


def get_token():
    if state["token"] and time.time() < state["exp"] - 60:
        return state["token"]
    if not state["id"] or not state["secret"]:
        raise RuntimeError("尚未設定 Client ID / Secret")
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": state["id"], "client_secret": state["secret"]}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read())
    state["token"] = j["access_token"]
    state["exp"] = time.time() + int(j.get("expires_in", 86400))
    return state["token"]


def fetch_nearby(lat, lon, r):
    key = (round(lat, 4), round(lon, 4), int(r))
    with lock:
        hit = cache.get(key)
        if hit and time.time() - hit[0] < MIN_INTERVAL:
            return hit[1], True
        q = urllib.parse.urlencode({
            "$spatialFilter": f"nearby({lat:.6f},{lon:.6f},{int(r)})",
            "$format": "JSON"}, quote_via=urllib.parse.quote)
        req = urllib.request.Request(f"{API_URL}?{q}", headers={
            "Authorization": "Bearer " + get_token(),
            "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
        state["calls"] += 1
        cache[key] = (time.time(), raw)
        return raw, False


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/api/status":
            return self._send(200, json.dumps({
                "configured": bool(state["id"] and state["secret"]),
                "calls": state["calls"]}).encode())
        if u.path == "/api/nearby":
            q = urllib.parse.parse_qs(u.query)
            try:
                raw, cached = fetch_nearby(float(q["lat"][0]), float(q["lon"][0]), float(q["r"][0]))
                return self._send(200, raw, extra={
                    "X-Cached": "1" if cached else "0", "X-Calls": str(state["calls"])})
            except urllib.error.HTTPError as e:
                return self._send(e.code, json.dumps({"error": f"TDX HTTP {e.code}", "detail": e.read().decode("utf-8", "ignore")[:300]}).encode())
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}).encode())
        self._send(404, b"{}")

    def do_POST(self):
        if self.path == "/api/config":
            n = int(self.headers.get("Content-Length", 0))
            j = json.loads(self.rfile.read(n) or b"{}")
            state.update(id=j.get("id", "").strip(), secret=j.get("secret", "").strip(), token=None, exp=0)
            try:
                get_token()
                return self._send(200, b'{"ok":true}')
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}).encode())
        self._send(404, b"{}")


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)   # 只綁本機，金鑰不外流
    print(f"開啟 http://localhost:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
