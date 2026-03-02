"""
OpenAI 自动注册脚本 V2 - 使用 mailfree.smanx.xx.kg 邮箱服务
"""
import json
import os
import re
import sys
import time
import random
import secrets
import hashlib
import base64
import argparse
from datetime import datetime
from urllib.parse import urlencode
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

from curl_cffi import requests

# ==========================================
# 配置
# ==========================================

MAILFREE_BASE = "https://mailfree.smanx.xx.kg"
JWT_TOKEN = "auto"  # 管理员令牌

AUTH_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

DEFAULT_REDIRECT_URI = "http://localhost:1455/auth/callback"
DEFAULT_SCOPE = "openid email profile offline_access"

# 账号密码保存文件
ACCOUNTS_FILE = "email_accounts.txt"


# ==========================================
# MailFree 邮箱 API
# ==========================================


def _mailfree_headers() -> Dict[str, Any]:
    """构建请求头，使用管理员令牌认证"""
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Admin-Token": JWT_TOKEN,
    }


def get_domains(proxies: Any = None) -> List[str]:
    """获取可用域名列表"""
    resp = requests.get(
        f"{MAILFREE_BASE}/api/domains",
        headers=_mailfree_headers(),
        proxies=proxies,
        impersonate="chrome",
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"获取域名失败，状态码: {resp.status_code}")
    return resp.json()


def create_email(local: str, domain_index: int = 0, proxies: Any = None) -> Dict[str, Any]:
    """创建自定义邮箱"""
    resp = requests.post(
        f"{MAILFREE_BASE}/api/create",
        headers=_mailfree_headers(),
        json={"local": local, "domainIndex": domain_index},
        proxies=proxies,
        impersonate="chrome",
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"创建邮箱失败，状态码: {resp.status_code}: {resp.text}")
    return resp.json()


def generate_random_email(length: int = 10, domain_index: int = 0, proxies: Any = None) -> Dict[str, Any]:
    """随机生成邮箱"""
    resp = requests.get(
        f"{MAILFREE_BASE}/api/generate",
        headers=_mailfree_headers(),
        params={"length": length, "domainIndex": domain_index},
        proxies=proxies,
        impersonate="chrome",
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"生成邮箱失败，状态码: {resp.status_code}")
    return resp.json()


def get_emails(mailbox: str, limit: int = 20, proxies: Any = None) -> List[Dict[str, Any]]:
    """获取邮件列表"""
    resp = requests.get(
        f"{MAILFREE_BASE}/api/emails",
        headers=_mailfree_headers(),
        params={"mailbox": mailbox, "limit": limit},
        proxies=proxies,
        impersonate="chrome",
        timeout=15,
    )
    if resp.status_code != 200:
        return []
    return resp.json()


def get_email_detail(email_id: int, proxies: Any = None) -> Dict[str, Any]:
    """获取邮件详情"""
    resp = requests.get(
        f"{MAILFREE_BASE}/api/email/{email_id}",
        headers=_mailfree_headers(),
        proxies=proxies,
        impersonate="chrome",
        timeout=15,
    )
    if resp.status_code != 200:
        return {}
    return resp.json()


def delete_mailbox(address: str, proxies: Any = None) -> bool:
    """删除邮箱及其所有邮件"""
    resp = requests.delete(
        f"{MAILFREE_BASE}/api/mailboxes",
        headers=_mailfree_headers(),
        json={"address": address},
        proxies=proxies,
        impersonate="chrome",
        timeout=15,
    )
    return resp.status_code == 200


def reset_mailbox_password(address: str, new_password: str, proxies: Any = None) -> bool:
    """设置邮箱密码"""
    resp = requests.post(
        f"{MAILFREE_BASE}/api/mailboxes/change-password",
        headers=_mailfree_headers(),
        json={"address": address, "new_password": new_password},
        proxies=proxies,
        impersonate="chrome",
        timeout=15,
    )
    return resp.status_code == 200


def save_account_info(email: str, password: str):
    """保存账号信息到文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {email} | {password}\n")
    print(f"[*] 账号信息已保存到: {ACCOUNTS_FILE}")


def get_openai_code(email: str, proxies: Any = None) -> str:
    """轮询获取 OpenAI 验证码"""
    regex = r"(?<!\d)(\d{6})(?!\d)"
    seen_ids: set = set()

    print(f"[*] 正在等待邮箱 {email} 的验证码...", end="", flush=True)

    for attempt in range(3):
        print(".", end="", flush=True)
        try:
            resp = requests.get(
                f"{MAILFREE_BASE}/api/emails",
                headers=_mailfree_headers(),
                params={"mailbox": email, "limit": 10},
                proxies=proxies,
                impersonate="chrome",
                timeout=15,
            )

            if resp.status_code != 200:
                time.sleep(3)
                continue

            emails = resp.json()
            if not isinstance(emails, list):
                emails = []

            for mail in emails:
                msg_id = mail.get("id")
                if not msg_id or msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                sender = str(mail.get("sender") or "").lower()
                subject = str(mail.get("subject") or "")
                preview = str(mail.get("preview") or "")
                verification_code = mail.get("verification_code")

                # 如果已有提取的验证码
                if verification_code:
                    if "openai" in sender or "openai" in subject.lower():
                        print(f"\n 抓到啦! 验证码: {verification_code}")
                        return str(verification_code)

                # 获取邮件详情
                detail_resp = requests.get(
                    f"{MAILFREE_BASE}/api/email/{msg_id}",
                    headers=_mailfree_headers(),
                    proxies=proxies,
                    impersonate="chrome",
                    timeout=15,
                )

                if detail_resp.status_code == 200:
                    detail = detail_resp.json()
                    content = "\n".join([
                        subject,
                        preview,
                        str(detail.get("content") or ""),
                        str(detail.get("html_content") or ""),
                    ])
                else:
                    content = "\n".join([subject, preview])

                if "openai" not in sender and "openai" not in content.lower():
                    continue

                m = re.search(regex, content)
                if m:
                    print(f"\n 抓到啦! 验证码: {m.group(1)}")
                    return m.group(1)

        except Exception as e:
            pass

        time.sleep(10)

    print("\n 超时，未收到验证码")
    return ""


# ==========================================
# OAuth 授权与辅助函数
# ==========================================


def _b64url_no_pad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _sha256_b64url_no_pad(s: str) -> str:
    return _b64url_no_pad(hashlib.sha256(s.encode("ascii")).digest())


def _random_state(nbytes: int = 16) -> str:
    return secrets.token_urlsafe(nbytes)


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _decode_jwt_segment(seg: str) -> Dict[str, Any]:
    raw = (seg or "").strip()
    if not raw:
        return {}
    pad = "=" * ((4 - (len(raw) % 4)) % 4)
    try:
        decoded = base64.urlsafe_b64decode((raw + pad).encode("ascii"))
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}


def _jwt_claims_no_verify(id_token: str) -> Dict[str, Any]:
    if not id_token or id_token.count(".") < 2:
        return {}
    payload_b64 = id_token.split(".")[1]
    pad = "=" * ((4 - (len(payload_b64) % 4)) % 4)
    try:
        payload = base64.urlsafe_b64decode((payload_b64 + pad).encode("ascii"))
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return {}


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


import urllib.parse
import urllib.request
import urllib.error


def _post_form(url: str, data: Dict[str, str], timeout: int = 30) -> Dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.status != 200:
                raise RuntimeError(
                    f"token exchange failed: {resp.status}: {raw.decode('utf-8', 'replace')}"
                )
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        raise RuntimeError(
            f"token exchange failed: {exc.code}: {raw.decode('utf-8', 'replace')}"
        ) from exc


def _parse_callback_url(callback_url: str) -> Dict[str, Any]:
    candidate = callback_url.strip()
    if not candidate:
        return {"code": "", "state": "", "error": "", "error_description": ""}

    if "://" not in candidate:
        if candidate.startswith("?"):
            candidate = f"http://localhost{candidate}"
        elif any(ch in candidate for ch in "/?#") or ":" in candidate:
            candidate = f"http://{candidate}"
        elif "=" in candidate:
            candidate = f"http://localhost/?{candidate}"

    parsed = urllib.parse.urlparse(candidate)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    fragment = urllib.parse.parse_qs(parsed.fragment, keep_blank_values=True)

    for key, values in fragment.items():
        if key not in query or not query[key] or not (query[key][0] or "").strip():
            query[key] = values

    def get1(k: str) -> str:
        v = query.get(k, [""])
        return (v[0] or "").strip()

    code = get1("code")
    state = get1("state")
    error = get1("error")
    error_description = get1("error_description")

    if code and not state and "#" in code:
        code, state = code.split("#", 1)

    if not error and error_description:
        error, error_description = error_description, ""

    return {
        "code": code,
        "state": state,
        "error": error,
        "error_description": error_description,
    }


@dataclass(frozen=True)
class OAuthStart:
    auth_url: str
    state: str
    code_verifier: str
    redirect_uri: str


def generate_oauth_url(
    *, redirect_uri: str = DEFAULT_REDIRECT_URI, scope: str = DEFAULT_SCOPE
) -> OAuthStart:
    state = _random_state()
    code_verifier = _pkce_verifier()
    code_challenge = _sha256_b64url_no_pad(code_verifier)

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    return OAuthStart(
        auth_url=auth_url,
        state=state,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
    )


def submit_callback_url(
    *,
    callback_url: str,
    expected_state: str,
    code_verifier: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
) -> str:
    cb = _parse_callback_url(callback_url)
    if cb["error"]:
        desc = cb["error_description"]
        raise RuntimeError(f"oauth error: {cb['error']}: {desc}".strip())

    if not cb["code"]:
        raise ValueError("callback url missing ?code=")
    if not cb["state"]:
        raise ValueError("callback url missing ?state=")
    if cb["state"] != expected_state:
        raise ValueError("state mismatch")

    token_resp = _post_form(
        TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": cb["code"],
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
    )

    access_token = (token_resp.get("access_token") or "").strip()
    refresh_token = (token_resp.get("refresh_token") or "").strip()
    id_token = (token_resp.get("id_token") or "").strip()
    expires_in = _to_int(token_resp.get("expires_in"))

    claims = _jwt_claims_no_verify(id_token)
    email = str(claims.get("email") or "").strip()
    auth_claims = claims.get("https://api.openai.com/auth") or {}
    account_id = str(auth_claims.get("chatgpt_account_id") or "").strip()

    now = int(time.time())
    expired_rfc3339 = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + max(expires_in, 0))
    )
    now_rfc3339 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

    config = {
        "id_token": id_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_id": account_id,
        "last_refresh": now_rfc3339,
        "email": email,
        "type": "codex",
        "expired": expired_rfc3339,
    }

    return json.dumps(config, ensure_ascii=False, separators=(",", ":"))


# ==========================================
# 核心注册逻辑
# ==========================================


def run(proxy: Optional[str]) -> Optional[str]:
    proxies: Any = None
    if proxy:
        proxies = {"http": proxy, "https": proxy}

    s = requests.Session(proxies=proxies, impersonate="chrome")

    # IP 检查
    try:
        trace = s.get("https://cloudflare.com/cdn-cgi/trace", timeout=10)
        trace = trace.text
        loc_re = re.search(r"^loc=(.+)$", trace, re.MULTILINE)
        loc = loc_re.group(1) if loc_re else None
        print(f"[*] 当前 IP 所在地: {loc}")
        if loc == "CN" or loc == "HK":
            raise RuntimeError("检查代理哦w - 所在地不支持")
    except Exception as e:
        print(f"[Error] 网络连接检查失败: {e}")
        return None

    # 获取域名并创建邮箱
    try:
        domains = get_domains(proxies)
        if not domains:
            print("[Error] 没有可用域名")
            return None
        print(f"[*] 可用域名: {domains}")

        # 随机生成邮箱
        local = f"oc{secrets.token_hex(5)}"
        email_info = create_email(local, domain_index=0, proxies=proxies)
        email = email_info.get("address") or email_info.get("email")
        
        if not email:
            print("[Error] 创建邮箱失败")
            return None

        # 生成密码并设置
        email_password = secrets.token_urlsafe(12)
        if reset_mailbox_password(email, email_password, proxies=proxies):
            print(f"[*] 成功创建邮箱: {email}")
            print(f"[*] 邮箱密码: {email_password}")
        else:
            email_password = "默认密码(查看后台)"
            print(f"[Warn] 设置密码失败，邮箱: {email}")

    except Exception as e:
        print(f"[Error] 邮箱创建失败: {e}")
        return None

    oauth = generate_oauth_url()
    url = oauth.auth_url

    try:
        resp = s.get(url, timeout=15)
        did = s.cookies.get("oai-did")
        print(f"[*] Device ID: {did}")

        signup_body = f'{{"username":{{"value":"{email}","kind":"email"}},"screen_hint":"signup"}}'
        sen_req_body = f'{{"p":"","id":"{did}","flow":"authorize_continue"}}'

        sen_resp = requests.post(
            "https://sentinel.openai.com/backend-api/sentinel/req",
            headers={
                "origin": "https://sentinel.openai.com",
                "referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html?sv=20260219f9f6",
                "content-type": "text/plain;charset=UTF-8",
            },
            data=sen_req_body,
            proxies=proxies,
            impersonate="chrome",
            timeout=15,
        )

        if sen_resp.status_code != 200:
            print(f"[Error] Sentinel 异常拦截，状态码: {sen_resp.status_code}")
            return None

        sen_token = sen_resp.json()["token"]
        sentinel = f'{{"p": "", "t": "", "c": "{sen_token}", "id": "{did}", "flow": "authorize_continue"}}'

        signup_resp = s.post(
            "https://auth.openai.com/api/accounts/authorize/continue",
            headers={
                "referer": "https://auth.openai.com/create-account",
                "accept": "application/json",
                "content-type": "application/json",
                "openai-sentinel-token": sentinel,
            },
            data=signup_body,
        )
        print(f"[*] 提交注册表单状态: {signup_resp.status_code}")

        otp_resp = s.post(
            "https://auth.openai.com/api/accounts/passwordless/send-otp",
            headers={
                "referer": "https://auth.openai.com/create-account/password",
                "accept": "application/json",
                "content-type": "application/json",
            },
        )
        print(f"[*] 验证码发送状态: {otp_resp.status_code}")

        code = get_openai_code(email, proxies)
        if not code:
            return {"email": email, "password": email_password}

        code_body = f'{{"code":"{code}"}}'
        code_resp = s.post(
            "https://auth.openai.com/api/accounts/email-otp/validate",
            headers={
                "referer": "https://auth.openai.com/email-verification",
                "accept": "application/json",
                "content-type": "application/json",
            },
            data=code_body,
        )
        print(f"[*] 验证码校验状态: {code_resp.status_code}")

        create_account_body = '{"name":"Neo","birthdate":"2000-02-20"}'
        create_account_resp = s.post(
            "https://auth.openai.com/api/accounts/create_account",
            headers={
                "referer": "https://auth.openai.com/about-you",
                "accept": "application/json",
                "content-type": "application/json",
            },
            data=create_account_body,
        )
        create_account_status = create_account_resp.status_code
        print(f"[*] 账户创建状态: {create_account_status}")

        if create_account_status != 200:
            print(create_account_resp.text)
            return {"email": email, "password": email_password}

        auth_cookie = s.cookies.get("oai-client-auth-session")
        if not auth_cookie:
            print("[Error] 未能获取到授权 Cookie")
            return {"email": email, "password": email_password}

        auth_json = _decode_jwt_segment(auth_cookie.split(".")[0])
        workspaces = auth_json.get("workspaces") or []
        if not workspaces:
            print("[Error] 授权 Cookie 里没有 workspace 信息")
            return {"email": email, "password": email_password}
        workspace_id = str((workspaces[0] or {}).get("id") or "").strip()
        if not workspace_id:
            print("[Error] 无法解析 workspace_id")
            return {"email": email, "password": email_password}

        select_body = f'{{"workspace_id":"{workspace_id}"}}'
        select_resp = s.post(
            "https://auth.openai.com/api/accounts/workspace/select",
            headers={
                "referer": "https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
                "content-type": "application/json",
            },
            data=select_body,
        )

        if select_resp.status_code != 200:
            print(f"[Error] 选择 workspace 失败，状态码: {select_resp.status_code}")
            print(select_resp.text)
            return {"email": email, "password": email_password}

        continue_url = str((select_resp.json() or {}).get("continue_url") or "").strip()
        if not continue_url:
            print("[Error] workspace/select 响应里缺少 continue_url")
            return {"email": email, "password": email_password}

        current_url = continue_url
        for i in range(6):
            final_resp = s.get(current_url, allow_redirects=False, timeout=15)
            location = final_resp.headers.get("Location") or ""

            if final_resp.status_code not in [301, 302, 303, 307, 308]:
                break
            if not location:
                break

            next_url = urllib.parse.urljoin(current_url, location)
            if "code=" in next_url and "state=" in next_url:
                token_json = submit_callback_url(
                    callback_url=next_url,
                    code_verifier=oauth.code_verifier,
                    redirect_uri=oauth.redirect_uri,
                    expected_state=oauth.state,
                )
                return {"token": token_json, "email": email, "password": email_password}
            current_url = next_url

        print("[Error] 未能在重定向链中捕获到最终 Callback URL")
        return {"email": email, "password": email_password}

    except Exception as e:
        print(f"[Error] 运行时发生错误: {e}")
        return {"email": email, "password": email_password}


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI 自动注册脚本 V2 - MailFree")
    parser.add_argument(
        "--proxy", default=None, help="代理地址，如 http://127.0.0.1:7890"
    )
    parser.add_argument("--once", action="store_true", help="只运行一次")
    parser.add_argument("--sleep-min", type=int, default=5, help="循环模式最短等待秒数")
    parser.add_argument(
        "--sleep-max", type=int, default=30, help="循环模式最长等待秒数"
    )
    args = parser.parse_args()

    sleep_min = max(1, args.sleep_min)
    sleep_max = max(sleep_min, args.sleep_max)

    count = 0
    print("[Info] OpenAI Auto-Registrar V2 Started (MailFree)")

    while True:
        count += 1
        print(
            f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> 开始第 {count} 次注册流程 <<<"
        )

        try:
            result = run(args.proxy)

            if result and result.get("token"):
                token_json = result["token"]
                email = result.get("email", "unknown")
                password = result.get("password", "")

                try:
                    t_data = json.loads(token_json)
                    fname_email = t_data.get("email", email).replace("@", "_")
                except Exception:
                    fname_email = email.replace("@", "_")

                file_name = f"token_{fname_email}_{int(time.time())}.json"

                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(token_json)

                print(f"[*] 成功! Token 已保存至: {file_name}")

                # 保存账号信息
                save_account_info(email, password)
            else:
                print("[-] 本次注册失败。")

            # 无论成功失败都删除邮箱
            if result and result.get("email"):
                email = result.get("email")
                if delete_mailbox(email, proxies={"http": args.proxy, "https": args.proxy} if args.proxy else None):
                    print(f"[*] 已删除邮箱: {email}")
                else:
                    print(f"[Warn] 删除邮箱失败: {email}")

        except Exception as e:
            print(f"[Error] 发生未捕获异常: {e}")

        if args.once:
            break

        wait_time = random.randint(sleep_min, sleep_max)
        print(f"[*] 休息 {wait_time} 秒...")
        time.sleep(wait_time)


if __name__ == "__main__":
    main()