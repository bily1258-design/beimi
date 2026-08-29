#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多源节点订阅合并器: 拉取多个免费节点源 -> 解析 -> 去重
-> 输出 output/clash.yaml (Clash/Mihomo 订阅) + output/subscribe.txt (通用 Base64 订阅)
"""
import base64
import json
import os
import re
import sys
import urllib.request
from collections import OrderedDict

try:
    import yaml
except ImportError:
    yaml = None

# 源列表: 优先喂 raw 文件(纯URI文本 / clash yaml), 比爬 HTML 稳
SOURCES = [
    # 大源: 纯 vless/trojan URI 文本 (每日更新, ~700KB)
    "https://raw.githubusercontent.com/yafeisun/v2raynode/main/result/nodetotal.txt",
    # FreeNodes 聚合: ss/vmess 文本
    "https://raw.githubusercontent.com/Barabama/FreeNodes/main/nodes/simple.txt",
    "https://raw.githubusercontent.com/Barabama/FreeNodes/main/nodes/yudou66.txt",
    # V2RayAggregator: 多协议聚合, 每日更新 (ss/vmess/vless 文本 + yaml)
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/Eternity.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/Eternity.yml",
    # ripaojiedian/freenode: 大而全的 clash yaml 聚合
    "https://raw.githubusercontent.com/ripaojiedian/freenode/main/clash",
    # ermaozi/get_subscribe: 老牌聚合, 长期维护 (clash yaml)
    "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/clash.yml",
    # xiaoji235/airport-free: 超大节点池 (12MB+, 每3小时更新)
    "https://raw.githubusercontent.com/xiaoji235/airport-free/main/v2ray.txt",
    # clash yaml 源 (hysteria2/vless)
    "https://raw.githubusercontent.com/tonygyf/free/main/all.yaml",
    # 备用: 测速过筛版
    "https://raw.githubusercontent.com/yafeisun/v2raynode/main/result/karing.txt",
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIMEOUT = 40


def fetch(url):
    """下载源内容, 失败返回 None"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠️ 拉取失败 {url}: {e}")
        return None


def looks_like_b64(text):
    """整体 base64 编码的订阅检测"""
    s = text.strip()
    if not s or len(s) < 50:
        return False
    # 去掉换行后仍是 base64 字符集, 且没有 URI 特征
    flat = re.sub(r"\s+", "", s)
    if "://" in flat:
        return False
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", flat):
        return False
    return len(flat) % 4 == 0


def try_b64_decode(text):
    """尝试 base64 解码订阅内容"""
    try:
        flat = re.sub(r"\s+", "", text.strip())
        flat += "=" * (-len(flat) % 4)
        raw = base64.b64decode(flat)
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def split_uris(text):
    """把文本拆成 URI 行, 自动处理整体 base64 订阅"""
    t = text.strip()
    if not t:
        return []
    if looks_like_b64(t):
        dec = try_b64_decode(t)
        if dec:
            t = dec
    uris = []
    for line in t.splitlines():
        line = line.strip()
        if line.startswith(("ss://", "vmess://", "trojan://", "vless://", "hysteria2://", "hy2://")):
            uris.append(line)
    return uris


# ---------- URI -> clash proxy ----------

def b64d(s):
    try:
        s = s.strip() + "=" * (-len(s.strip()) % 4)
        return base64.b64decode(s).decode("utf-8", errors="replace")
    except Exception:
        return None


def _valid_short_id(sid):
    """REALITY short-id 合法格式: 偶数长度 hex (2~16 位 = 1~8 字节, mihomo 限制
    RealityMaxShortIDLen=8 字节)。空串/奇数长度/非 hex/超长都非法, 返回 None。
    mihomo 对空 short-id 报 "invalid REALITY short ID" (短 ID 解析为 0 字节仍会报)。
    注意: 短 ID 不能是纯数字样式的 YAML 标量(如 08), go-yaml 会解析成 int 再转字符串
    丢前导零 ("08"->"8" 奇数位) 导致 mihomo 报错, 因此 dump 时必须给 short-id 强制加引号。"""
    if not sid:
        return None
    sid = str(sid).strip()
    if len(sid) < 2 or len(sid) > 16 or len(sid) % 2 != 0:
        return None
    if not re.fullmatch(r"[0-9a-fA-F]+", sid):
        return None
    return sid


def dump_clash_yaml(clash, f):
    """safe_dump 后给 short-id 强制加单引号, 防止 PyYAML 把 "08" 这类纯数字样式
    字符串写成裸标量 08, 被 mihomo(go-yaml) 解析成 int 丢前导零导致
    "invalid REALITY short ID"。"""
    text = yaml.safe_dump(clash, allow_unicode=True,
                          sort_keys=False, default_flow_style=False)
    text = re.sub(
        r'(^|\n)(\s*short-id:\s*)([^\n]+)',
        lambda m: m.group(1) + m.group(2) + (
            m.group(3) if m.group(3).lstrip().startswith(("'", '"'))
            else "'" + m.group(3).strip() + "'"),
        text)
    f.write(text)


def sanitize_proxy(p):
    """清洗单个 clash proxy, 规避 mihomo 严格校验导致的加载失败:
    - reality-opts.short-id 非法(空/奇数/非hex) -> 删除该字段(short-id 可选)
    - short-id 被 YAML 解析成数字 -> 转字符串再校验
    - ss cipher 为 'none' -> 剔除该节点 (mihomo 不支持)
    - port 强制 int
    返回清洗后的 dict, 若节点不可用返回 None。"""
    if not isinstance(p, dict):
        return None
    # reality-opts
    ro = p.get("reality-opts")
    if isinstance(ro, dict):
        if "short-id" in ro:
            sid = _valid_short_id(ro.get("short-id"))
            if sid:
                ro["short-id"] = sid
            else:
                del ro["short-id"]
        if not ro:
            p.pop("reality-opts", None)
    # ss cipher: mihomo 白名单校验, 乱码/未知方法直接剔除节点
    if p.get("type") == "ss":
        cipher = str(p.get("cipher", "")).strip().lower()
        if cipher in ("", "none"):
            return None
        if cipher not in ("aes-128-gcm", "aes-192-gcm", "aes-256-gcm",
                          "chacha20-ietf-poly1305", "xchacha20-ietf-poly1305",
                          "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm",
                          "2022-blake3-chacha20-poly1305"):
            return None
    # port
    try:
        p["port"] = int(p.get("port", 0))
    except (ValueError, TypeError):
        p["port"] = 0
    return p


def parse_vmess(uri, idx):
    try:
        j = json.loads(b64d(uri[len("vmess://"):]) or "{}")
        name = j.get("ps") or f"vmess-{idx}"
        try:
            aid = int(j.get("aid", 0) or 0)
        except (ValueError, TypeError):
            aid = 0
        p = {
            "name": name, "type": "vmess",
            "server": j.get("add", ""), "port": int(j.get("port", 0) or 0),
            "uuid": j.get("id", ""), "alterId": aid,
            "cipher": "auto", "udp": True,
        }
        net = j.get("net", "tcp")
        if net in ("ws", "websocket"):
            p["network"] = "ws"
            p["ws-opts"] = {"path": j.get("path", "/"), "headers": {"Host": j.get("host", "")}}
        elif net == "grpc":
            p["network"] = "grpc"
            p["grpc-opts"] = {"grpc-service-name": j.get("path", "")}
        else:
            p["network"] = "tcp"
        if j.get("tls") in ("tls", "1", True):
            p["tls"] = True
            p["servername"] = j.get("sni") or j.get("host") or ""
        if j.get("sni"):
            p["servername"] = j["sni"]
        return p
    except Exception:
        return None


def parse_vless(uri, idx):
    try:
        body, _, frag = uri.partition("#")
        head, _, query = body[len("vless://"):].partition("?")
        uuid, _, addr = head.rpartition("@")
        # 支持 IPv6 地址 (如 [2401:db8::1]:443)
        if addr.startswith("["):
            host, _, port = addr[1:].partition("]:")
        else:
            host, _, port = addr.rpartition(":")
        params = dict(re.findall(r"([^&=]+)=([^&]*)", query))
        name = urllib.parse.unquote(frag) if frag else f"vless-{idx}"
        p = {"name": name, "type": "vless", "server": host, "port": int(port), "uuid": uuid, "udp": True}
        net = params.get("type", "tcp")
        p["network"] = net
        if net == "ws":
            p["ws-opts"] = {"path": params.get("path", "/"), "headers": {"Host": params.get("host", "")}}
        elif net == "grpc":
            p["grpc-opts"] = {"grpc-service-name": params.get("serviceName", "")}
        if params.get("security") in ("tls", "reality"):
            p["tls"] = True
            p["servername"] = params.get("sni") or params.get("host") or ""
            if params.get("flow"):
                p["flow"] = params["flow"]
            if params.get("fp"):
                p["client-fingerprint"] = params["fp"]
            if params.get("pbk"):
                _sid = _valid_short_id(params.get("sid", ""))
                p["reality-opts"] = {"public-key": params["pbk"]}
                if _sid:
                    p["reality-opts"]["short-id"] = _sid
        return p
    except Exception:
        return None


def parse_trojan(uri, idx):
    try:
        body, _, frag = uri.partition("#")
        head, _, query = body[len("trojan://"):].partition("?")
        pw, _, addr = head.rpartition("@")
        host, _, port = addr.rpartition(":")
        params = dict(re.findall(r"([^&=]+)=([^&]*)", query))
        name = urllib.parse.unquote(frag) if frag else f"trojan-{idx}"
        p = {"name": name, "type": "trojan", "server": host, "port": int(port), "password": pw, "udp": True}
        if params.get("sni"):
            p["sni"] = params["sni"]
            p["servername"] = params["sni"]
        if params.get("type") == "ws":
            p["network"] = "ws"
            p["ws-opts"] = {"path": params.get("path", "/"), "headers": {"Host": params.get("host", "")}}
        if params.get("security") == "reality" and params.get("pbk"):
            _sid = _valid_short_id(params.get("sid", ""))
            p["reality-opts"] = {"public-key": params["pbk"]}
            if _sid:
                p["reality-opts"]["short-id"] = _sid
        if params.get("allowInsecure", "") == "1":
            p["skip-cert-verify"] = True
        return p
    except Exception as e:
        print(f"  ⚠️ trojan 解析失败: {e}")
        return None


def parse_ss(uri, idx):
    try:
        body, _, frag = uri.partition("#")
        name = urllib.parse.unquote(frag) if frag else f"ss-{idx}"
        # SIP002: ss://base64(method:password)@host:port/?plugin=...
        m = re.match(r"ss://([^@]+)@([^:]+):(\d+)(/?\?.*)?$", body)
        if m:
            secret, host, port, q = m.group(1), m.group(2), m.group(3), m.group(4) or ""
            dec = b64d(secret) or secret
            if ":" in dec:
                method, password = dec.split(":", 1)
            else:
                # 老格式整串 base64
                whole = b64d(body[len("ss://"):]) or ""
                method, _, rest = whole.partition(":")
                password, _, h2 = rest.rpartition("@")
                host, _, port = h2.rpartition(":")
            p = {"name": name, "type": "ss", "server": host, "port": int(port), "cipher": method, "password": password, "udp": True}
            if "plugin=" in q:
                pl = re.search(r"plugin=([^&]+)", q)
                if pl:
                    p["plugin"] = "v2ray-plugin"
                    p["plugin-opts"] = {"mode": "websocket", "tls": True, "host": host}
            return p
        # 整串 base64: ss://base64(method:password@host:port)
        whole = b64d(body[len("ss://"):])
        if whole:
            method, _, rest = whole.partition(":")
            password, _, addr = rest.rpartition("@")
            host, _, port = addr.rpartition(":")
            return {"name": name, "type": "ss", "server": host, "port": int(port),
                    "cipher": method, "password": password, "udp": True}
        return None
    except Exception:
        return None


def parse_hysteria2(uri, idx):
    try:
        body, _, frag = uri.partition("#")
        head, _, query = body.split("://", 1)[1].partition("?")
        pw, _, addr = head.rpartition("@")
        host, _, port = addr.rpartition(":")
        params = dict(re.findall(r"([^&=]+)=([^&]*)", query))
        name = urllib.parse.unquote(frag) if frag else f"hy2-{idx}"
        p = {"name": name, "type": "hysteria2", "server": host, "port": int(port), "password": pw, "udp": True}
        if params.get("sni"):
            p["sni"] = params["sni"]
            p["servername"] = params["sni"]
        if params.get("insecure") == "1":
            p["skip-cert-verify"] = True
        return p
    except Exception as e:
        print(f"  ⚠️ hysteria2 解析失败: {e}")
        return None


def uri_to_proxy(uri, idx):
    if uri.startswith("vmess://"):
        return parse_vmess(uri, idx)
    if uri.startswith("vless://"):
        return parse_vless(uri, idx)
    if uri.startswith("trojan://"):
        return parse_trojan(uri, idx)
    if uri.startswith("ss://"):
        return parse_ss(uri, idx)
    if uri.startswith(("hysteria2://", "hy2://")):
        return parse_hysteria2(uri.replace("hy2://", "hysteria2://"), idx)
    return None


def proxy_to_uri(p):
    """把 clash proxy dict 反序列化回 URI (与 uri_to_proxy 互逆)。

    供 subscribe_b64/plain 使用: 从地区过滤+去重后的 all_proxies 生成,
    保证 b64 订阅与 clash.yaml 节点集合完全一致。反序列化失败返回 None
    (该节点只进 clash.yaml, 不进 b64)。
    """
    from urllib.parse import quote
    try:
        name = str(p.get("name", ""))
        frag = quote(name, safe="") if name else ""
        server = p.get("server", "")
        port = p.get("port", 0)
        t = p.get("type", "")
        if not server or not port:
            return None

        if t == "ss":
            # SIP002: ss://base64(method:password)@host:port#name
            secret = base64.b64encode(
                f"{p.get('cipher','')}:{p.get('password','')}".encode()).decode("ascii")
            u = f"ss://{secret}@{server}:{port}"
            # 尽力还原 v2ray-plugin (v2rayNG 支持 SIP002 plugin 参数)
            if p.get("plugin") == "v2ray-plugin":
                opts = p.get("plugin-opts", {})
                host = opts.get("host", server)
                mode = opts.get("mode", "websocket")
                tls = "true" if opts.get("tls") else "false"
                u += f"/?plugin=v2ray-plugin%3Bmode%3D{mode}%3Btls%3D{tls}%3Bhost%3D{quote(host, safe='')}"
            return u + (f"#{frag}" if frag else "")

        if t == "vmess":
            j = {
                "v": "2", "ps": name, "add": server, "port": str(port),
                "id": p.get("uuid", ""), "aid": str(p.get("alterId", 0)),
                "scy": "auto", "net": p.get("network", "tcp"),
                "type": "none", "host": "", "path": "",
                "tls": "tls" if p.get("tls") else "",
            }
            net = p.get("network", "tcp")
            if net == "ws":
                ws = p.get("ws-opts", {})
                j["host"] = ws.get("headers", {}).get("Host", "")
                j["path"] = ws.get("path", "")
            elif net == "h2":
                h2 = p.get("h2-opts", {})
                j["host"] = h2.get("host", "")
                j["path"] = h2.get("path", "")
            elif net == "grpc":
                j["host"] = p.get("grpc-opts", {}).get("grpc-service-name", "")
                j["path"] = "grpc"
            if p.get("servername"):
                j["sni"] = p["servername"]
            if p.get("client-fingerprint"):
                j["fp"] = p["client-fingerprint"]
            raw = base64.b64encode(json.dumps(j, ensure_ascii=False).encode()).decode("ascii")
            return f"vmess://{raw}"

        if t == "vless":
            q = []
            net = p.get("network", "tcp")
            if net == "ws":
                ws = p.get("ws-opts", {})
                q.append(f"type=ws&path={quote(ws.get('path','/'), safe='')}"
                         f"&host={quote(ws.get('headers',{}).get('Host',''), safe='')}")
            elif net == "grpc":
                q.append(f"type=grpc&serviceName={quote(p.get('grpc-opts',{}).get('grpc-service-name',''), safe='')}")
            if p.get("tls"):
                sec = "reality" if p.get("reality-opts") else "tls"
                q.append(f"security={sec}")
                if p.get("servername"):
                    q.append(f"sni={quote(p['servername'], safe='')}")
                if p.get("client-fingerprint"):
                    q.append(f"fp={quote(p['client-fingerprint'], safe='')}")
                if p.get("flow"):
                    q.append(f"flow={quote(p['flow'], safe='')}")
                ro = p.get("reality-opts")
                if ro:
                    if ro.get("public-key"):
                        q.append(f"pbk={quote(ro['public-key'], safe='')}")
                    if ro.get("short-id"):
                        q.append(f"sid={quote(ro['short-id'], safe='')}")
            u = f"vless://{p.get('uuid','')}@{server}:{port}"
            if q:
                u += "?" + "&".join(q)
            return u + (f"#{frag}" if frag else "")

        if t == "trojan":
            q = []
            net = p.get("network", "tcp")
            if net == "ws":
                ws = p.get("ws-opts", {})
                q.append(f"type=ws&path={quote(ws.get('path','/'), safe='')}"
                         f"&host={quote(ws.get('headers',{}).get('Host',''), safe='')}")
            if p.get("servername"):
                q.append(f"sni={quote(p['servername'], safe='')}")
            if p.get("skip-cert-verify"):
                q.append("allowInsecure=1")
            ro = p.get("reality-opts")
            if ro and ro.get("public-key"):
                q.append(f"security=reality&pbk={quote(ro['public-key'], safe='')}")
                if ro.get("short-id"):
                    q.append(f"sid={quote(ro['short-id'], safe='')}")
            u = f"trojan://{quote(p.get('password',''), safe='')}@{server}:{port}"
            if q:
                u += "?" + "&".join(q)
            return u + (f"#{frag}" if frag else "")

        if t == "hysteria2":
            q = []
            if p.get("servername"):
                q.append(f"sni={quote(p['servername'], safe='')}")
            if p.get("skip-cert-verify"):
                q.append("insecure=1")
            u = f"hysteria2://{quote(p.get('password',''), safe='')}@{server}:{port}"
            if q:
                u += "?" + "&".join(q)
            return u + (f"#{frag}" if frag else "")

        return None
    except Exception:
        return None


# ---------- clash yaml 源 ----------

def parse_yaml_proxies(text):
    """从 clash yaml 提取 proxies 列表"""
    if yaml is None:
        print("  ⚠️ 无 pyyaml, 跳过 yaml 源")
        return []
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict) and isinstance(data.get("proxies"), list):
            out = []
            for p in data["proxies"]:
                if isinstance(p, dict) and p.get("server") and p.get("port"):
                    p = dict(p)
                    p.setdefault("udp", True)
                    p = sanitize_proxy(p)   # yaml 源直接带空 short-id, 必须清洗
                    if p:
                        out.append(p)
            return out
    except Exception as e:
        print(f"  ⚠️ yaml 解析失败: {e}")
    return []


# ---------- 地区过滤: 只保留 美国/日本/香港/台湾/新加坡 ----------

REGION_PATTERNS = {
    # 美国
    "US": {
        "name": re.compile(
            r"美国|美利坚|🇺🇸|\bus\b|\busa\b|united\s*states|\bamerica\b|"
            r"硅谷|洛杉矶|纽约|西雅图|芝加哥|达拉斯|圣何塞|凤凰城|亚特兰大|"
            r"休斯顿|迈阿密|旧金山|波士顿|费城|丹佛|拉斯维加斯|"
            r"silicon\s*valley|los\s*angeles|new\s*york|seattle|chicago|dallas|"
            r"san\s*jose|phoenix|atlanta|houston|miami|san\s*francisco|"
            r"boston|philadelphia|denver|las\s*vegas", re.I),
        "server": re.compile(
            r"(^|[^a-z])(us|usa)([\d\-]|\.|$)|unitedstates|\.us($|[^a-z])|us\d+", re.I),
    },
    # 日本
    "JP": {
        "name": re.compile(
            r"日本|🇯🇵|\bjp\b|japan|东京|大阪|名古屋|福冈|札幌|冲绳|"
            r"tokyo|osaka|nagoya|fukuoka|sapporo|okinawa", re.I),
        "server": re.compile(
            r"(^|[^a-z])(jp|japan)([\d\-]|\.|$)|jp\d+", re.I),
    },
    # 香港
    "HK": {
        "name": re.compile(
            r"香港|🇭🇰|\bhk\b|hksar|hong\s*kong|hongkong|港服|港区|\b港\b", re.I),
        "server": re.compile(
            r"(^|[^a-z])hk([\d\-]|\.|$)|hongkong", re.I),
    },
    # 台湾
    "TW": {
        "name": re.compile(
            r"台湾|臺灣|🇹🇼|\btw\b|taiwan|台北|台中|台南|高雄|新竹|桃园|"
            r"taipei|taichung|tainan|kaohsiung|hsinchu|taoyuan", re.I),
        "server": re.compile(
            r"(^|[^a-z])(tw|taiwan)([\d\-]|\.|$)|taiwan|tw\d+", re.I),
    },
    # 新加坡
    "SG": {
        "name": re.compile(
            r"新加坡|狮城|🇸🇬|\bsg\b|singapore", re.I),
        "server": re.compile(
            r"(^|[^a-z])(sg|singapore)([\d\-]|\.|$)|singapore|\.sg($|[^a-z])|sg\d+", re.I),
    },
}


def match_region(proxy):
    """按节点名 + 服务器域名判断地区, 命中保留区(美/日/港/台/新)返回地区码, 否则 None"""
    name = str(proxy.get("name", ""))
    server = str(proxy.get("server", ""))
    for region, pats in REGION_PATTERNS.items():
        if pats["name"].search(name) or pats["server"].search(server):
            return region
    return None


# ---------- 主流程 ----------

def main():
    print("=== 多源订阅合并器 ===")
    out_dir = "output"
    os.makedirs(out_dir, exist_ok=True)

    all_proxies = []      # clash proxy dict 列表
    uri_order = []        # 原始 URI 顺序(用于 subscribe.txt 去重)
    uri_proxies = {}      # URI -> 解析出的 proxy (供 b64/plain 订阅同步地区过滤)
    seen_uri = set()
    seen_key = set()

    # 1) 本地米贝源: enhanced_crawler.py 生成的 subscription.txt
    local_srcs = ["subscription.txt"]
    for f in local_srcs:
        if os.path.exists(f):
            with open(f, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            uris = split_uris(text)
            if uris:
                print(f"✔ 本地源 {f}: {len(uris)} 行")
                for u in uris:
                    if u not in seen_uri:
                        seen_uri.add(u)
                        uri_order.append(u)
                        p = uri_to_proxy(u, len(uri_order))
                        if p:
                            uri_proxies[u] = p
                            all_proxies.append(p)
            else:
                print(f"  ⚠️ 本地源 {f} 无可用节点(米贝爬取可能失败, 不影响其他源)")

    # 2) 远程源
    for url in SOURCES:
        print(f"→ {url}")
        text = fetch(url)
        if not text:
            continue
        t = text.strip()
        ps = parse_yaml_proxies(t) if ("proxies:" in t and yaml is not None) else []
        if ps:
            print(f"  ✔ yaml 源: {len(ps)} 个节点")
            for p in ps:
                key = (p.get("type"), p.get("server"), p.get("port"))
                if key in seen_key:
                    continue
                seen_key.add(key)
                # 重名加序号, 保证 clash 配置合法
                name = p.get("name", f"node-{len(all_proxies)+1}")
                if any(x["name"] == name for x in all_proxies):
                    name = f"{name}-{len(all_proxies)+1}"
                p["name"] = name
                all_proxies.append(p)
        else:
            uris = split_uris(t)
            print(f"  ✔ 文本源: {len(uris)} 行 URI")
            for u in uris:
                if u in seen_uri:
                    continue
                seen_uri.add(u)
                uri_order.append(u)
                p = uri_to_proxy(u, len(uri_order))
                if p:
                    uri_proxies[u] = p
                    all_proxies.append(p)

    # 3) 按 (type, server, port) 去重
    dedup = []
    for p in all_proxies:
        key = (p.get("type"), p.get("server"), p.get("port"))
        if key in seen_key:
            continue
        seen_key.add(key)
        name = p.get("name", f"node-{len(dedup)+1}")
        if any(x["name"] == name for x in dedup):
            name = f"{name}-{len(dedup)+1}"
        p["name"] = name
        p = sanitize_proxy(p)   # 最终兜底清洗: 空 short-id / 非法 cipher 等
        if p:
            dedup.append(p)
    all_proxies = dedup

    # 3b) 地区过滤: 只保留 美国/日本/香港/台湾/新加坡 (按节点名 + 服务器域名判定)
    before_region = len(all_proxies)
    region_stats = {}
    filtered = []
    for p in all_proxies:
        r = match_region(p)
        if r:
            region_stats[r] = region_stats.get(r, 0) + 1
            filtered.append(p)
    all_proxies = filtered
    # 同步过滤 URI 列表: subscribe_b64.txt / subscribe_plain.txt 只输出保留地区节点。
    # 按 URI 自身解析结果判定地区 (名称含地区标识), 不能用 (server,port) 匹配——
    # 反代服务器被多地区共用 (如 oplosgru-c.catcat321.com 挂 US/BR 多节点) 会混入非保留区。
    uri_order = [u for u, pp in uri_proxies.items() if match_region(pp)]

    print(f"\n=== 汇总: {before_region} 个唯一节点 → 地区过滤后 {len(all_proxies)} 个 "
          f"(🇺🇸美国{region_stats.get('US', 0)} / 🇯🇵日本{region_stats.get('JP', 0)} "
          f"/ 🇭🇰香港{region_stats.get('HK', 0)} / 🇹🇼台湾{region_stats.get('TW', 0)} "
          f"/ 🇸🇬新加坡{region_stats.get('SG', 0)}) ===")

    if not all_proxies:
        print("!! 没有拿到任何节点, 不覆盖 output/")
        sys.exit(1)

    # 4) 生成 clash.yaml
    group_names = [p["name"] for p in all_proxies]
    clash = {
        "mixed-port": 7890,
        "allow-lan": True,
        "mode": "rule",
        "log-level": "info",
        "proxies": all_proxies,
        "proxy-groups": [
            {"name": "🚀 节点选择", "type": "select", "proxies": ["♻️ 自动选择"] + group_names},
            {"name": "♻️ 自动选择", "type": "url-test", "proxies": group_names,
             "url": "http://www.gstatic.com/generate_204", "interval": 300},
        ],
        "rules": [
            "GEOIP,CN,DIRECT",
            "MATCH,🚀 节点选择",
        ],
    }
    with open(os.path.join(out_dir, "clash.yaml"), "w", encoding="utf-8") as f:
        dump_clash_yaml(clash, f)
    print(f"✔ {out_dir}/clash.yaml 已生成 ({len(all_proxies)} 节点)")

    # 5) 生成 subscribe.txt (Clash/mihomo 兼容 YAML 配置)
    #    注意: mihomo 内核只按 YAML 加载订阅内容, 无 base64 fallback;
    #    旧版输出整体 base64(URI行) 会导致 "cannot unmarshal !!str into config.RawConfig",
    #    所以主订阅改为 YAML, base64 版单列为 subscribe_b64.txt 供 v2rayNG 等使用
    with open(os.path.join(out_dir, "subscribe.txt"), "w", encoding="utf-8") as f:
        dump_clash_yaml(clash, f)
    print(f"✔ {out_dir}/subscribe.txt 已生成 (Clash/Mihomo YAML, {len(all_proxies)} 节点)")

    # 5b) subscribe_b64.txt: 整体 base64 URI 订阅 (v2rayNG 等通用客户端)
    #    从地区过滤+去重后的 all_proxies 反序列化回 URI —— 与 clash.yaml 节点
    #    集合完全一致 (旧逻辑只收 URI 文本源节点, 丢 yaml 大源且未按 key 去重)。
    b64_uris = []
    for _p in all_proxies:
        _u = proxy_to_uri(_p)
        if _u and _u not in b64_uris:
            b64_uris.append(_u)
    if not b64_uris:
        # 兜底: 全部反序列化失败时退回旧逻辑, 至少不输出空文件
        b64_uris = uri_order
    b64_all = base64.b64encode("\n".join(b64_uris).encode("utf-8")).decode("ascii")
    # 分块每 76 字符换行 (标准 MIME base64, 客户端兼容性最好)
    b64_lines = "\n".join(b64_all[i:i+76] for i in range(0, len(b64_all), 76))
    with open(os.path.join(out_dir, "subscribe_b64.txt"), "w", encoding="utf-8") as f:
        f.write(b64_lines + "\n")
    # 同时保留明文 URI 版, 方便调试/直接导入 v2rayNG
    with open(os.path.join(out_dir, "subscribe_plain.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(b64_uris) + "\n")
    print(f"✔ {out_dir}/subscribe_b64.txt 已生成 ({len(b64_uris)} 行 URI, Base64, 与 clash.yaml 节点一致)")
    print(f"✔ {out_dir}/subscribe_plain.txt 已生成")

    # 6) 统计
    types = {}
    for p in all_proxies:
        types[p.get("type", "?")] = types.get(p.get("type", "?"), 0) + 1
    print("协议分布: " + ", ".join(f"{k}={v}" for k, v in sorted(types.items())))


if __name__ == "__main__":
    import urllib.parse  # noqa
    main()
