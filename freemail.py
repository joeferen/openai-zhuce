"""
Freemail 临时邮箱服务模块
基于 https://github.com/smanx/freemail 项目
"""

import json
import re
import time
import secrets
from typing import Any, Dict, Optional, List
from datetime import datetime

from curl_cffi import requests


# ==========================================
# 配置
# ==========================================

MAIL_BASE = "https://mailfree.smanx.xx.kg"
JWT_TOKEN = "auto"  # 管理员令牌


def _headers() -> Dict[str, str]:
    """构建请求头，使用管理员令牌认证"""
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Admin-Token": JWT_TOKEN,
    }


# ==========================================
# 邮箱管理
# ==========================================

def get_domains(proxies: Any = None) -> List[str]:
    """获取可用域名列表"""
    try:
        resp = requests.get(
            f"{MAIL_BASE}/api/domains",
            headers=_headers(),
            proxies=proxies,
            impersonate="chrome",
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception as e:
        print(f"[Error] 获取域名列表失败: {e}")
        return []


def create_email(
    local: Optional[str] = None,
    domain_index: int = 0,
    proxies: Any = None
) -> Dict[str, Any]:
    """
    创建临时邮箱
    
    Args:
        local: 邮箱前缀，不指定则随机生成
        domain_index: 域名索引
    
    Returns:
        {"email": "xxx@domain.com", "password": "生成的密码", "success": True}
    """
    try:
        if local:
            # 自定义创建
            resp = requests.post(
                f"{MAIL_BASE}/api/create",
                headers=_headers(),
                json={"local": local, "domainIndex": domain_index},
                proxies=proxies,
                impersonate="chrome",
                timeout=15,
            )
        else:
            # 随机生成
            local = f"oc{secrets.token_hex(5)}"
            resp = requests.get(
                f"{MAIL_BASE}/api/generate",
                headers=_headers(),
                params={"length": 12, "domainIndex": domain_index},
                proxies=proxies,
                impersonate="chrome",
                timeout=15,
            )

        if resp.status_code != 200:
            print(f"[Error] 创建邮箱失败，状态码: {resp.status_code}")
            return {"success": False, "error": resp.text}

        data = resp.json()
        email = data.get("email", "")
        
        if not email:
            return {"success": False, "error": "未返回邮箱地址"}

        # 生成随机密码
        password = secrets.token_urlsafe(12)
        
        # 设置邮箱密码
        pwd_resp = requests.post(
            f"{MAIL_BASE}/api/mailboxes/change-password",
            headers=_headers(),
            json={"address": email, "new_password": password},
            proxies=proxies,
            impersonate="chrome",
            timeout=15,
        )

        if pwd_resp.status_code == 200:
            print(f"[*] 成功创建邮箱: {email}")
            return {"email": email, "password": password, "success": True}
        else:
            # 如果设置密码失败，尝试重置密码
            reset_resp = requests.post(
                f"{MAIL_BASE}/api/mailboxes/reset-password",
                headers=_headers(),
                json={"address": email},
                proxies=proxies,
                impersonate="chrome",
                timeout=15,
            )
            if reset_resp.status_code == 200:
                print(f"[*] 成功创建邮箱（使用重置密码）: {email}")
                return {"email": email, "password": "请查看管理后台", "success": True}
            
            print(f"[Warn] 设置密码失败，邮箱已创建: {email}")
            return {"email": email, "password": "", "success": True}

    except Exception as e:
        print(f"[Error] 创建邮箱出错: {e}")
        return {"success": False, "error": str(e)}


def delete_email(email: str, proxies: Any = None) -> bool:
    """删除指定邮箱"""
    try:
        resp = requests.delete(
            f"{MAIL_BASE}/api/mailboxes",
            headers=_headers(),
            params={"address": email},
            proxies=proxies,
            impersonate="chrome",
            timeout=15,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[Error] 删除邮箱失败: {e}")
        return False


def list_mailboxes(proxies: Any = None, limit: int = 100) -> List[Dict]:
    """获取邮箱列表"""
    try:
        resp = requests.get(
            f"{MAIL_BASE}/api/mailboxes",
            headers=_headers(),
            params={"limit": limit},
            proxies=proxies,
            impersonate="chrome",
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception as e:
        print(f"[Error] 获取邮箱列表失败: {e}")
        return []


# ==========================================
# 邮件操作
# ==========================================

def get_emails(
    email: str,
    limit: int = 20,
    proxies: Any = None
) -> List[Dict]:
    """获取邮件列表"""
    try:
        resp = requests.get(
            f"{MAIL_BASE}/api/emails",
            headers=_headers(),
            params={"mailbox": email, "limit": limit},
            proxies=proxies,
            impersonate="chrome",
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception as e:
        print(f"[Error] 获取邮件列表失败: {e}")
        return []


def get_email_detail(email_id: int, proxies: Any = None) -> Optional[Dict]:
    """获取邮件详情"""
    try:
        resp = requests.get(
            f"{MAIL_BASE}/api/email/{email_id}",
            headers=_headers(),
            proxies=proxies,
            impersonate="chrome",
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        print(f"[Error] 获取邮件详情失败: {e}")
        return None


def get_verification_code(
    email: str,
    proxies: Any = None,
    max_attempts: int = 40,
    interval: int = 3
) -> str:
    """
    轮询获取验证码
    
    Args:
        email: 邮箱地址
        max_attempts: 最大尝试次数
        interval: 轮询间隔（秒）
    
    Returns:
        6位验证码，未获取到返回空字符串
    """
    regex = r"(?<!\d)(\d{6})(?!\d)"
    seen_ids: set = set()

    print(f"[*] 正在等待邮箱 {email} 的验证码...", end="", flush=True)

    for attempt in range(max_attempts):
        print(".", end="", flush=True)
        try:
            emails = get_emails(email, limit=10, proxies=proxies)
            
            for msg in emails:
                msg_id = msg.get("id")
                if not msg_id or msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                sender = str(msg.get("sender", "")).lower()
                subject = str(msg.get("subject", ""))
                preview = str(msg.get("preview", ""))
                vcode = str(msg.get("verification_code", ""))

                # 检查是否来自 OpenAI
                if "openai" not in sender and "openai" not in subject.lower():
                    continue

                # 优先使用系统提取的验证码
                if vcode and re.match(regex, vcode):
                    print(f" 抓到啦! 验证码: {vcode}")
                    return vcode

                # 从内容中提取验证码
                content = "\n".join([subject, preview])
                
                # 获取完整邮件内容
                detail = get_email_detail(msg_id, proxies=proxies)
                if detail:
                    content = "\n".join([
                        subject,
                        preview,
                        str(detail.get("content", "")),
                        str(detail.get("html_content", ""))
                    ])

                m = re.search(regex, content)
                if m:
                    print(f" 抓到啦! 验证码: {m.group(1)}")
                    return m.group(1)

        except Exception:
            pass

        time.sleep(interval)

    print(" 超时，未收到验证码")
    return ""


def clear_emails(email: str, proxies: Any = None) -> bool:
    """清空邮箱所有邮件"""
    try:
        resp = requests.delete(
            f"{MAIL_BASE}/api/emails",
            headers=_headers(),
            params={"mailbox": email},
            proxies=proxies,
            impersonate="chrome",
            timeout=15,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[Error] 清空邮件失败: {e}")
        return False


# ==========================================
# 账号保存
# ==========================================

def save_account(email: str, password: str, file_path: str = "accounts.txt") -> bool:
    """
    保存账号信息到文件
    
    Args:
        email: 邮箱地址
        password: 密码
        file_path: 保存文件路径
    
    Returns:
        是否保存成功
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} | {email} | {password}\n")
        return True
    except Exception as e:
        print(f"[Error] 保存账号失败: {e}")
        return False


# ==========================================
# 测试
# ==========================================

if __name__ == "__main__":
    print("[*] Freemail 临时邮箱服务测试")
    print(f"[*] 服务地址: {MAIL_BASE}")
    
    # 获取域名列表
    domains = get_domains()
    print(f"[*] 可用域名: {domains}")
    
    if domains:
        # 创建邮箱
        result = create_email()
        if result.get("success"):
            email = result["email"]
            password = result["password"]
            print(f"[*] 邮箱: {email}")
            print(f"[*] 密码: {password}")
            
            # 保存账号
            save_account(email, password)
            print("[*] 账号已保存到 accounts.txt")
        else:
            print(f"[Error] {result.get('error')}")
