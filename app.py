from __future__ import annotations

import datetime
import json
import logging
import os
import secrets
import threading
import time
from typing import Any, Dict, List, Tuple
from logging.handlers import RotatingFileHandler

import requests
from flask import Flask, g, jsonify, request
from flask_cors import CORS

LOGIN_URL = "https://iclass.buaa.edu.cn:8347/app/user/login.action"
SCHEDULE_URL = "https://iclass.buaa.edu.cn:8347/app/course/get_stu_course_sched.action"
SIGN_URL = "http://iclass.buaa.edu.cn:8081/app/course/stu_scan_sign.action"

CHECKIN_OFFSET_MIN = -15_000
CHECKIN_OFFSET_MAX = -1_000
GLOBAL_CHECKIN_OFFSET_CACHE_KEY = "global"
SCHEDULE_CACHE_TTL_SECONDS = 24 * 60 * 60

FALLBACK_MOBILE_UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7 Build/TQ3A.230901.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36"
CHECKIN_PY_LIKE_UA = "Mozilla/5.0 (Linux; Android 13; M2012K11AC Build/TKQ1.220829.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 wxwork/4.1.22 MicroMessenger/7.0.1 NetType/WIFI Language/zh"

MOBILE_WECHAT_USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 9; COL-AL10 Build/HUAWEICOL-AL10; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/85.0.3527.52 MQQBrowser/6.2 TBS/044607 Mobile Safari/537.36 MMWEBID/7140 MicroMessenger/7.0.4.1420(0x27000437) Process/tools NetType/4G Language/zh_CN",
    "Mozilla/5.0 (Linux; Android 13; V2148A Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 XWEB/1160117 MMWEBSDK/20240404 MMWEBID/8833 MicroMessenger/8.0.49.2600(0x28003137) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 12; NOH-AL00 Build/HUAWEINOH-AL00; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 XWEB/1160117 MMWEBSDK/20240404 MMWEBID/6916 MicroMessenger/8.0.49.2600(0x28003136) WeChat/arm64 Weixin NetType/4G Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 14; V2307A Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 XWEB/1160117 MMWEBSDK/20240301 MMWEBID/4922 MicroMessenger/8.0.48.2580(0x28003052) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 13; 23049RAD8C Build/TKQ1.221114.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 XWEB/1160083 MMWEBSDK/20230303 MMWEBID/4466 MicroMessenger/8.0.34.2340(0x2800225F) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 10; PBEM00 Build/QKQ1.190918.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 XWEB/1160083 MMWEBSDK/20240301 MMWEBID/3124 MicroMessenger/8.0.48.2580(0x2800303F) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 13; V2024A Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 XWEB/1160117 MMWEBSDK/20240301 MMWEBID/2429 MicroMessenger/8.0.48.2580(0x28003050) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 13; V2304A Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 XWEB/1160083 MMWEBSDK/20240301 MMWEBID/195 MicroMessenger/8.0.48.2580(0x2800303F) WeChat/arm64 Weixin NetType/5G Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 9; COL-AL10 Build/HUAWEICOL-AL10; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/58.0.4467.59 MQQBrowser/6.2 TBS/044607 Mobile Safari/537.36 MMWEBID/7140 MicroMessenger/7.0.4.1420(0x27000437) Process/tools NetType/4G Language/zh_CN",
    "Mozilla/5.0 (Linux; Android 9; COL-AL10 Build/HUAWEICOL-AL10; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/56.0.3545.100 MQQBrowser/6.2 TBS/044607 Mobile Safari/537.36 MMWEBID/7140 MicroMessenger/7.0.4.1420(0x27000437) Process/tools NetType/4G Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.49(0x18003127) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.49(0x18003127) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.48(0x18003030) NetType/4G Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.42(0x18002a32) NetType/4G Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.48(0x1800302c) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.49(0x18003129) NetType/4G Language/zh_HK",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.48(0x18003030) NetType/4G Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_8_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.48(0x18003030) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.48(0x18003030) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.49(0x1800312a) NetType/WIFI Language/zh_CN",
]

app = Flask(__name__)
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGIN", "https://hjhjh144.github.io").split(",")
    if origin.strip()
]
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": FRONTEND_ORIGINS,
            "allow_headers": ["Content-Type", "X-Invite-Token"],
            "methods": ["GET", "POST", "OPTIONS"],
        }
    },
)

STUDENT_NAME_CACHE: Dict[str, str] = {}
USER_NAME_CACHE: Dict[str, str] = {}
USER_STUDENT_ID_CACHE: Dict[str, str] = {}
IP_LOCATION_CACHE: Dict[str, Dict[str, str]] = {}
SCHEDULE_CACHE: Dict[Tuple[str, str], Tuple[float, List[Dict[str, str]]]] = {}
CHECKIN_OFFSET_CACHE: Dict[str, Tuple[int, float]] = {}
REQUEST_LOG_LOCK = threading.Lock()
SCHEDULE_CACHE_LOCK = threading.Lock()
CHECKIN_OFFSET_CACHE_LOCK = threading.Lock()

INVITE_CODE = "zhll334"
INVITE_MAX_ATTEMPTS = 3
INVITE_COOLDOWN_SECONDS = 30 * 60
INVITE_TOKEN_TTL_SECONDS = 12 * 60 * 60
INVITE_VERIFY_PATH = "/api/invite/verify"
INVITE_STATUS_PATH = "/api/invite/status"
INVITE_PUBLIC_PATHS = {"/api/health", INVITE_VERIFY_PATH, INVITE_STATUS_PATH}
INVITE_FAIL_TRACK: Dict[str, Dict[str, float]] = {}
INVITE_TOKENS: Dict[str, float] = {}
INVITE_LOCK = threading.Lock()


def _select_mobile_ua_from_pool(pool: List[str]) -> str:
    """从User Agent池中随机选择一个，如果池为空返回备用UA."""
    if not pool:
        return FALLBACK_MOBILE_UA
    import random
    return random.choice(pool)


def _mobile_user_agent() -> str:
    """获取随机移动WeChat User Agent."""
    return _select_mobile_ua_from_pool(MOBILE_WECHAT_USER_AGENTS)


def _is_offset_error(err_msg: str) -> bool:
    """检查是否是偏移量相关的错误."""
    return "参数错误" in err_msg or "二维码已失效" in err_msg or "已失效" in err_msg


def _binary_search_checkin_offset(
    user_id: str, session_id: str, schedule_id: str, base_ts: int
) -> Tuple[bool, Dict[str, Any]]:
    """
    通过二分搜索找到有效的打卡时间戳偏移量。
    返回 (success, data) 其中 data 包含 found_offset 和 result.
    """
    lo = CHECKIN_OFFSET_MIN
    hi = CHECKIN_OFFSET_MAX

    while lo < hi - 1:
        mid = (lo + hi) // 2
        ok, data = _do_single_checkin(user_id, session_id, schedule_id, base_ts + mid)
        
        if ok:
            return True, {"found_offset": mid, "result": data}
        
        err_msg = data.get("errMsg", "")
        if "参数错误" in err_msg:
            # 偏移量偏小，需要更负的值
            hi = mid
        elif "二维码已失效" in err_msg or "已失效" in err_msg:
            # 偏移量偏大，需要更接近零的值
            lo = mid
        else:
            # 其他错误，不继续搜索
            return False, data
    
    # 尝试剩余的候选值
    for offset in [lo, lo + 1, hi - 1, hi]:
        if CHECKIN_OFFSET_MIN <= offset <= CHECKIN_OFFSET_MAX:
            ok, data = _do_single_checkin(user_id, session_id, schedule_id, base_ts + offset)
            if ok:
                return True, {"found_offset": offset, "result": data}
    
    return False, {
        "message": f"二分搜索失败，无有效偏移量(范围:{CHECKIN_OFFSET_MIN}~{CHECKIN_OFFSET_MAX})",
        "errCode": "BINARY_SEARCH_FAILED",
        "errMsg": "无有效打卡偏移量",
    }


def _do_single_checkin(
    user_id: str, session_id: str, schedule_id: str, timestamp: int
) -> Tuple[bool, Dict[str, Any]]:
    """
    执行单次打卡请求。
    返回 (success, data)
    """
    params = {"id": user_id, "courseSchedId": schedule_id, "timestamp": str(timestamp)}
    headers = {"Sessionid": session_id}
    
    try:
        resp = requests.post(url=SIGN_URL, params=params, headers=headers, timeout=10)
    except requests.RequestException as exc:
        return False, {"message": f"打卡请求失败: {exc}", "errCode": "REQUEST_ERROR", "errMsg": str(exc)}
    
    if not resp.ok:
        return False, {
            "message": f"打卡失败，状态码: {resp.status_code}",
            "errCode": "HTTP_ERROR",
            "errMsg": "HTTP请求失败",
        }
    
    data = _safe_json_loads(resp.text)
    status_text = str(data.get("STATUS", "")).strip()
    err_code = str(data.get("ERRCODE", "")).strip()
    err_msg = str(data.get("ERRMSG", "")).strip() or str(data.get("ERRORMSG", "")).strip()
    result = data.get("result")
    
    if status_text == "0" and result:
        return True, {
            "status": status_text,
            "errCode": err_code,
            "errMsg": err_msg,
            "result": result,
        }
    
    return False, {
        "message": err_msg or f"打卡失败(STATUS={status_text})",
        "status": status_text or "-1",
        "errCode": err_code,
        "errMsg": err_msg,
    }


def _setup_audit_logger() -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger("audit")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = RotatingFileHandler(
        "logs/audit.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    # 默认不在终端打印审计日志；设置 AUDIT_CONSOLE_LOG=true 可临时开启。
    if os.getenv("AUDIT_CONSOLE_LOG", "false").lower() == "true":
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


audit_logger = _setup_audit_logger()


def _get_client_ip() -> str:
    cf_ip = request.headers.get("CF-Connecting-IP", "").strip()
    if cf_ip:
        return cf_ip

    xff = request.headers.get("X-Forwarded-For", "").strip()
    if xff:
        return xff.split(",")[0].strip()

    return (request.remote_addr or "").strip()


def _cleanup_invite_tokens(now_ts: float) -> None:
    expired = [token for token, expire_ts in INVITE_TOKENS.items() if expire_ts <= now_ts]
    for token in expired:
        INVITE_TOKENS.pop(token, None)


def _get_invite_status(ip: str) -> Dict[str, Any]:
    now_ts = time.time()
    with INVITE_LOCK:
        state = INVITE_FAIL_TRACK.get(ip, {})
        attempts = int(state.get("attempts", 0))
        cooldown_until = float(state.get("cooldownUntil", 0.0))
        cooldown_remaining = max(0, int(cooldown_until - now_ts))
        if cooldown_remaining <= 0 and cooldown_until > 0:
            INVITE_FAIL_TRACK[ip] = {"attempts": attempts, "cooldownUntil": 0.0}

    attempts_left = max(0, INVITE_MAX_ATTEMPTS - attempts)
    return {
        "attemptsLeft": attempts_left,
        "maxAttempts": INVITE_MAX_ATTEMPTS,
        "cooldownRemainingSec": cooldown_remaining,
        "isCoolingDown": cooldown_remaining > 0,
    }


def _issue_invite_token() -> Dict[str, Any]:
    now_ts = time.time()
    expire_ts = now_ts + INVITE_TOKEN_TTL_SECONDS
    token = secrets.token_urlsafe(24)
    with INVITE_LOCK:
        _cleanup_invite_tokens(now_ts)
        INVITE_TOKENS[token] = expire_ts
    return {"inviteToken": token, "tokenExpiresInSec": INVITE_TOKEN_TTL_SECONDS}


def _is_invite_token_valid(token: str) -> bool:
    if not token:
        return False
    now_ts = time.time()
    with INVITE_LOCK:
        _cleanup_invite_tokens(now_ts)
        expire_ts = INVITE_TOKENS.get(token)
        if not isinstance(expire_ts, (int, float)):
            return False
        return expire_ts > now_ts


def _extract_identity_fields() -> Tuple[str, str]:
    student_id = ""
    user_id = ""

    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        student_id = str(payload.get("studentId", "")).strip()
        user_id = str(payload.get("userId", "")).strip()

    if not user_id:
        user_id = str(request.args.get("userId", "")).strip()

    if not student_id:
        student_id = str(request.args.get("studentId", "")).strip()

    return student_id, user_id


def _extract_student_name_from_result(result: Dict[str, Any]) -> str:
    # 优先取真实姓名，最后才回退到学号型字段。
    name_keys = ["realName", "nickName", "studentName", "name", "truename", "userName"]
    for key in name_keys:
        value = str(result.get(key, "")).strip()
        if value:
            return value
    return ""


def _mask_token(token: str) -> str:
    token = str(token or "").strip()
    if len(token) <= 10:
        return token
    return f"{token[:6]}...{token[-4:]}"


def _extract_login_profile(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    result = raw_data.get("result") if isinstance(raw_data.get("result"), dict) else {}

    account_info = {
        "用户ID": str(result.get("id", "")).strip(),
        "会话ID": _mask_token(str(result.get("sessionId", "")).strip()),
        "学号": str(result.get("studentNo", "")).strip() or str(result.get("userUUID", "")).strip(),
        "账号": str(result.get("userName", "")).strip(),
        "姓名": _extract_student_name_from_result(result),
        "昵称": str(result.get("nickName", "")).strip(),
        "性别": str(result.get("gender", "")).strip(),
        "用户级别": str(result.get("userLevel", "")).strip(),
    }

    org_info = {
        "角色": str(raw_data.get("roleNames", "")).strip(),
        "角色编码": str(raw_data.get("roleCodes", "")).strip(),
        "学院": str(result.get("academyName", "")).strip(),
        "学院ID": str(result.get("academyId", "")).strip(),
        "班级": str(result.get("classInfoName", "")).strip(),
        "班级ID": str(result.get("classId", "")).strip(),
        "学校编码": str(raw_data.get("schoolCode", "")).strip(),
    }

    capability_info = {
        "下载类型": str(raw_data.get("downloadType", "")).strip(),
        "播放器类型": str(raw_data.get("playerType", "")).strip(),
        "日历类型": str(raw_data.get("calendarType", "")).strip(),
        "视频下载类型": str(raw_data.get("videoDownType", "")).strip(),
        "智能运维地址": str(raw_data.get("smartOperationIp", "")).strip(),
        "大数据地址": str(raw_data.get("bigDataIp", "")).strip(),
    }

    return {
        "登录状态": str(raw_data.get("STATUS", "")).strip(),
        "账户信息": account_info,
        "组织信息": org_info,
        "能力信息": capability_info,
    }


def _format_login_profile_text(profile: Dict[str, Any]) -> str:
    if not profile:
        return "无"

    sections = []
    for section in ["账户信息", "组织信息", "能力信息"]:
        data = profile.get(section)
        if not isinstance(data, dict):
            continue
        pairs = []
        for key, value in data.items():
            text = str(value).strip()
            if text:
                pairs.append(f"{key}:{text}")
        if pairs:
            sections.append(f"{section}[{'，'.join(pairs)}]")

    status_text = str(profile.get("登录状态", "")).strip()
    if status_text:
        sections.insert(0, f"登录状态:{status_text}")

    return " | ".join(sections) if sections else "无"


def _format_signed_courses_text(response_data: Dict[str, Any]) -> str:
    signed_courses = response_data.get("signedCourses") if isinstance(response_data, dict) else None
    if not isinstance(signed_courses, list) or not signed_courses:
        return "无"

    parts: List[str] = []
    for item in signed_courses:
        if not isinstance(item, dict):
            continue
        date_str = str(item.get("dateStr", "")).strip()
        course_name = str(item.get("courseName", "")).strip() or "未知课程"
        course_sched_id = str(item.get("courseSchedId", "")).strip()
        label = f"{course_name}(ID:{course_sched_id or '未知'})"
        if date_str:
            label = f"{date_str} {label}"
        parts.append(label)

    if not parts:
        return "无"
    return f"共{len(parts)}门: " + "；".join(parts)


def _resolve_student_name(student_id: str, user_id: str = "") -> str:
    if student_id:
        cached = STUDENT_NAME_CACHE.get(student_id, "")
        if cached:
            return cached
    if user_id:
        cached = USER_NAME_CACHE.get(user_id, "")
        if cached:
            return cached
    return ""


def _resolve_student_id(user_id: str, student_id: str = "") -> str:
    if student_id:
        return student_id
    if user_id:
        return USER_STUDENT_ID_CACHE.get(user_id, "")
    return ""


def _get_ip_location(ip: str) -> Dict[str, str]:
    if not ip:
        return {
            "country": "",
            "region": "",
            "city": "",
            "isp": "",
            "queryStatus": "failed",
            "error": "IP为空",
        }

    if ip in IP_LOCATION_CACHE:
        return IP_LOCATION_CACHE[ip]

    # 本地回环地址没有公网归属地信息。
    if ip in {"127.0.0.1", "::1"}:
        location = {
            "country": "本机",
            "region": "本机",
            "city": "本机",
            "isp": "本机",
            "queryStatus": "local",
            "error": "",
        }
        IP_LOCATION_CACHE[ip] = location
        return location

    location = {
        "country": "",
        "region": "",
        "city": "",
        "isp": "",
        "queryStatus": "failed",
        "error": "未知错误",
    }
    try:
        resp = requests.get(f"https://ipwho.is/{ip}", timeout=3)
        data = resp.json() if resp.ok else {}
        if isinstance(data, dict) and data.get("success") is True:
            location = {
                "country": str(data.get("country", "")).strip(),
                "region": str(data.get("region", "")).strip(),
                "city": str(data.get("city", "")).strip(),
                "isp": str(data.get("connection", {}).get("isp", "")).strip()
                if isinstance(data.get("connection"), dict)
                else "",
                "queryStatus": "success",
                "error": "",
            }
        elif isinstance(data, dict):
            location = {
                "country": "",
                "region": "",
                "city": "",
                "isp": "",
                "queryStatus": "failed",
                "error": str(data.get("message", "归属地服务返回失败")).strip() or "归属地服务返回失败",
            }
        else:
            location = {
                "country": "",
                "region": "",
                "city": "",
                "isp": "",
                "queryStatus": "failed",
                "error": "归属地服务响应格式异常",
            }
    except (requests.RequestException, ValueError, TypeError):
        location = {
            "country": "",
            "region": "",
            "city": "",
            "isp": "",
            "queryStatus": "failed",
            "error": "归属地查询请求异常",
        }

    IP_LOCATION_CACHE[ip] = location
    return location


def _format_ip_location(location: Dict[str, str]) -> str:
    country = location.get("country", "")
    region = location.get("region", "")
    city = location.get("city", "")
    isp = location.get("isp", "")

    area = " ".join([item for item in [country, region, city] if item]).strip()
    if not area and not isp:
        return "未知"
    if area and isp:
        return f"{area} | {isp}"
    return area or isp


def _build_request_summary() -> str:
    payload = request.get_json(silent=True)
    query_data = request.args.to_dict(flat=True)
    lines = []
    if isinstance(payload, dict) and payload:
        payload_copy = dict(payload)
        # 仅在邀请码验证接口记录明文邀请码，其他接口继续脱敏。
        if "inviteCode" in payload_copy and request.path != INVITE_VERIFY_PATH:
            payload_copy["inviteCode"] = "***"
        lines.append(f"JSON参数: {json.dumps(payload_copy, ensure_ascii=False, separators=(',', ':'))}")
    if query_data:
        lines.append(f"Query参数: {json.dumps(query_data, ensure_ascii=False, separators=(',', ':'))}")
    if not lines:
        return "无"
    return " | ".join(lines)


def _write_daily_request_txt(
    *,
    req_time: datetime.datetime,
    ip: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    student_id: str,
    student_name: str,
    user_id: str,
    ip_location_text: str,
    ip_location_status: str,
    ip_location_error: str,
    user_agent: str,
    request_summary: str,
    login_profile_text: str = "",
    signed_courses_text: str = "",
) -> None:
    os.makedirs("request_logs", exist_ok=True)
    day_file = os.path.join("request_logs", f"{req_time.strftime('%Y-%m-%d')}.txt")

    block = (
        f"时间: {req_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"客户端IP: {ip}\n"
        f"请求方法: {method}\n"
        f"请求路径: {path}\n"
        f"响应状态码: {status_code}\n"
        f"处理耗时: {duration_ms:.2f} ms\n"
        f"学生学号: {student_id or '未知'}\n"
        f"学生姓名: {student_name or '未知'}\n"
        f"平台用户ID: {user_id or '未知'}\n"
        f"IP归属地: {ip_location_text}\n"
        f"IP归属查询状态: {ip_location_status or '未知'}\n"
        f"IP归属查询失败原因: {ip_location_error or '无'}\n"
        f"设备信息: {user_agent or '未知'}\n"
        f"请求参数摘要: {request_summary}\n"
        f"登录返回摘要: {login_profile_text or '无'}\n"
        f"打卡课程摘要: {signed_courses_text or '无'}\n"
        f"{'-' * 72}\n"
    )

    with REQUEST_LOG_LOCK:
        with open(day_file, "a", encoding="utf-8") as file:
            file.write(block)


def _safe_json_loads(text: str) -> Dict[str, Any]:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
        return {"STATUS": "-1", "ERRORMSG": "响应格式异常"}
    except json.JSONDecodeError:
        return {"STATUS": "-1", "ERRORMSG": "响应不是有效的JSON"}


def _parse_sign_status_flag(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "ok", "success"}:
        return True
    if text in {"0", "false", "no", "fail", "failed"}:
        return False
    return None


def _extract_sign_success_flag(data: Dict[str, Any]) -> Any:
    result = data.get("result")
    if isinstance(result, dict):
        for key in ["stuSignStatus", "signStatus", "status"]:
            if key in result:
                parsed = _parse_sign_status_flag(result.get(key))
                if isinstance(parsed, bool):
                    return parsed
    return None


def _validate_date_str(date_str: str) -> bool:
    try:
        datetime.datetime.strptime(date_str, "%Y%m%d")
        return True
    except ValueError:
        return False


def login_student(student_id: str) -> Tuple[bool, Dict[str, Any]]:
    params = {
        "phone": student_id,
        "userLevel": "1",
        "verificationType": "2",
        "verificationUrl": "",
    }
    ua = _mobile_user_agent()
    headers = {"User-Agent": ua}

    try:
        resp = requests.get(url=LOGIN_URL, params=params, headers=headers, timeout=10)
    except requests.RequestException as exc:
        return False, {"message": f"网络请求失败: {exc}"}

    data = _safe_json_loads(resp.text)
    if data.get("STATUS") != "0":
        return False, {"message": data.get("ERRORMSG", "登录失败"), "loginProfile": _extract_login_profile(data)}

    result = data.get("result") or {}
    user_id = result.get("id")
    session_id = result.get("sessionId")
    student_name = _extract_student_name_from_result(result)
    if not user_id or not session_id:
        return False, {"message": "登录响应缺少 userId 或 sessionId"}

    response_data: Dict[str, Any] = {
        "userId": str(user_id),
        "sessionId": str(session_id),
        "loginProfile": _extract_login_profile(data),
    }
    if student_name:
        response_data["studentName"] = student_name
    return True, response_data


def get_course_schedule(user_id: str, session_id: str, date_str: str) -> Tuple[bool, Dict[str, Any]]:
    # 尝试从缓存获取
    cache_key = (user_id, date_str)
    now = time.time()
    
    with SCHEDULE_CACHE_LOCK:
        if cache_key in SCHEDULE_CACHE:
            cached_at, courses = SCHEDULE_CACHE[cache_key]
            if now - cached_at < SCHEDULE_CACHE_TTL_SECONDS:
                return True, {"courses": courses}
    
    params = {
        "dateStr": date_str,
        "id": user_id,
    }
    headers = {"Sessionid": session_id}
    ua = _mobile_user_agent()
    headers["User-Agent"] = ua

    try:
        resp = requests.get(url=SCHEDULE_URL, params=params, headers=headers, timeout=10)
    except requests.RequestException as exc:
        return False, {"message": f"获取课程表失败: {exc}"}

    data = _safe_json_loads(resp.text)
    if data.get("STATUS") != "0":
        return False, {"message": data.get("ERRORMSG", "查询课程失败")}

    courses = data.get("result")
    if not isinstance(courses, list):
        return False, {"message": "课程数据格式异常"}

    normalized = []
    for item in courses:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "id": str(item.get("id", "")),
                "courseName": str(item.get("courseName", "")),
                "classBeginTime": str(item.get("classBeginTime", "")),
                "classEndTime": str(item.get("classEndTime", "")),
            }
        )

    # 存入缓存
    with SCHEDULE_CACHE_LOCK:
        SCHEDULE_CACHE[cache_key] = (now, normalized)

    return True, {"courses": normalized}


def sign_course(user_id: str, session_id: str, course_sched_id: str) -> Tuple[bool, Dict[str, Any]]:
    """
    打卡函数，集成二分搜索和全局偏移量缓存。
    """
    # 获取基础时间戳
    base_ts = int(time.time() * 1000)
    now = time.time()
    
    # 尝试使用全局缓存的偏移量
    with CHECKIN_OFFSET_CACHE_LOCK:
        cache_entry = CHECKIN_OFFSET_CACHE.get(GLOBAL_CHECKIN_OFFSET_CACHE_KEY)
    
    if cache_entry:
        cached_offset, cached_at = cache_entry
        if now - cached_at < SCHEDULE_CACHE_TTL_SECONDS:  # 使用相同的TTL
            # 尝试缓存的偏移量
            ok, data = _do_single_checkin(user_id, session_id, course_sched_id, base_ts + cached_offset)
            if ok:
                return True, {
                    "message": "打卡成功",
                    "httpStatus": 200,
                    "status": data.get("status", "0"),
                    "errCode": "",
                    "errMsg": "",
                }
            
            # 检查是否是偏移量错误
            err_msg = data.get("errMsg", "")
            if not _is_offset_error(err_msg):
                # 不是偏移量错误，直接返回
                return False, {
                    "message": data.get("message", "打卡失败"),
                    "httpStatus": 200,
                    "status": data.get("status", "-1"),
                    "errCode": data.get("errCode", ""),
                    "errMsg": err_msg,
                }
    
    # 缓存偏移量失效或不存在，执行二分搜索
    ok, search_result = _binary_search_checkin_offset(user_id, session_id, course_sched_id, base_ts)
    
    if ok:
        found_offset = search_result.get("found_offset", 0)
        # 缓存找到的偏移量
        with CHECKIN_OFFSET_CACHE_LOCK:
            CHECKIN_OFFSET_CACHE[GLOBAL_CHECKIN_OFFSET_CACHE_KEY] = (found_offset, now)
        
        return True, {
            "message": "打卡成功",
            "httpStatus": 200,
            "status": "0",
            "errCode": "",
            "errMsg": "",
        }
    
    return False, {
        "message": search_result.get("message", "打卡失败"),
        "httpStatus": 200,
        "status": search_result.get("status", "-1"),
        "errCode": search_result.get("errCode", ""),
        "errMsg": search_result.get("errMsg", ""),
    }


def _date_range(start_date: str, end_date: str) -> List[str]:
    start = datetime.datetime.strptime(start_date, "%Y%m%d")
    end = datetime.datetime.strptime(end_date, "%Y%m%d")
    days: List[str] = []
    current = start
    while current <= end:
        days.append(current.strftime("%Y%m%d"))
        current += datetime.timedelta(days=1)
    return days


def _course_result(
    course: Dict[str, str],
    success: bool,
    message: str,
    status: str = "",
    err_code: str = "",
    err_msg: str = "",
) -> Dict[str, Any]:
    return {
        "courseSchedId": course.get("id", ""),
        "courseName": course.get("courseName", ""),
        "classBeginTime": course.get("classBeginTime", ""),
        "classEndTime": course.get("classEndTime", ""),
        "success": success,
        "message": message,
        "status": status,
        "errCode": err_code,
        "errMsg": err_msg,
    }


@app.before_request
def before_request_log_start() -> None:
    g.request_start_time = time.perf_counter()

    if not request.path.startswith("/api/"):
        return
    if request.method == "OPTIONS":
        return
    if request.path in INVITE_PUBLIC_PATHS:
        return

    invite_token = str(request.headers.get("X-Invite-Token", "")).strip()
    if _is_invite_token_valid(invite_token):
        return

    response = jsonify(
        {
            "ok": False,
            "code": "INVITE_TOKEN_INVALID",
            "message": "邀请码验证已失效，请重新输入邀请码",
        }
    )
    response.status_code = 401
    return response


@app.after_request
def after_request_audit(response: Any) -> Any:
    if request.path.startswith("/api/") and request.method in {"GET", "POST"}:
        start = getattr(g, "request_start_time", None)
        now = datetime.datetime.now()
        duration_ms = 0.0
        if isinstance(start, float):
            duration_ms = (time.perf_counter() - start) * 1000

        student_id, user_id = _extract_identity_fields()
        student_id = _resolve_student_id(user_id=user_id, student_id=student_id)
        student_name = str(getattr(g, "student_name", "")).strip() or _resolve_student_name(student_id, user_id)
        request_summary = _build_request_summary()
        ip = _get_client_ip()
        ip_location = _get_ip_location(ip)
        ip_location_text = _format_ip_location(ip_location)
        ip_location_status = str(ip_location.get("queryStatus", "")).strip()
        ip_location_error = str(ip_location.get("error", "")).strip()
        login_profile_text = ""
        signed_courses_text = ""
        response_data: Dict[str, Any] = {}
        if request.path.startswith("/api/sign"):
            parsed = response.get_json(silent=True)
            if isinstance(parsed, dict):
                response_data = parsed
            signed_courses_text = _format_signed_courses_text(response_data)
        if request.path == "/api/login":
            login_profile = getattr(g, "login_profile", {})
            if isinstance(login_profile, dict):
                login_profile_text = _format_login_profile_text(login_profile)

        audit_logger.info(
            "请求日志 time=%s ip=%s ipLocation=%s method=%s path=%s status=%s duration_ms=%.2f studentId=%s studentName=%s userId=%s",
            now.isoformat(timespec="seconds"),
            ip,
            ip_location_text,
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            student_id,
            student_name,
            user_id,
        )

        _write_daily_request_txt(
            req_time=now,
            ip=ip,
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            student_id=student_id,
            student_name=student_name,
            user_id=user_id,
            ip_location_text=ip_location_text,
            ip_location_status=ip_location_status,
            ip_location_error=ip_location_error,
            user_agent=request.user_agent.string,
            request_summary=request_summary,
            login_profile_text=login_profile_text,
            signed_courses_text=signed_courses_text,
        )
    return response


@app.get("/api/health")
def health() -> Any:
    return jsonify({"ok": True})


@app.post(INVITE_VERIFY_PATH)
def api_invite_verify() -> Any:
    ip = _get_client_ip() or "unknown"
    payload = request.get_json(silent=True) or {}
    input_code = str(payload.get("inviteCode", "")).strip()
    status = _get_invite_status(ip)

    if status["isCoolingDown"]:
        return (
            jsonify(
                {
                    "ok": False,
                    "code": "INVITE_COOLDOWN",
                    "message": "输入错误次数过多，请稍后再试",
                    **status,
                }
            ),
            429,
        )

    if input_code != INVITE_CODE:
        now_ts = time.time()
        with INVITE_LOCK:
            state = INVITE_FAIL_TRACK.get(ip, {"attempts": 0, "cooldownUntil": 0.0})
            attempts = int(state.get("attempts", 0)) + 1
            cooldown_until = float(state.get("cooldownUntil", 0.0))
            if attempts >= INVITE_MAX_ATTEMPTS:
                cooldown_until = now_ts + INVITE_COOLDOWN_SECONDS
                attempts = INVITE_MAX_ATTEMPTS
            INVITE_FAIL_TRACK[ip] = {"attempts": attempts, "cooldownUntil": cooldown_until}

        status = _get_invite_status(ip)
        message = "邀请码错误"
        code = "INVITE_INVALID"
        http_status = 403
        if status["isCoolingDown"]:
            message = "输入错误次数过多，请30分钟后重试"
            code = "INVITE_COOLDOWN"
            http_status = 429
        return jsonify({"ok": False, "code": code, "message": message, **status}), http_status

    with INVITE_LOCK:
        INVITE_FAIL_TRACK[ip] = {"attempts": 0, "cooldownUntil": 0.0}
    token_data = _issue_invite_token()
    status = _get_invite_status(ip)

    return jsonify(
        {
            "ok": True,
            "message": "邀请码验证通过",
            **token_data,
            **status,
            "attemptsLeft": INVITE_MAX_ATTEMPTS,
            "cooldownRemainingSec": 0,
            "isCoolingDown": False,
        }
    )


@app.get(INVITE_STATUS_PATH)
def api_invite_status() -> Any:
    ip = _get_client_ip() or "unknown"
    status = _get_invite_status(ip)
    return jsonify({"ok": True, **status})


@app.post("/api/login")
def api_login() -> Any:
    payload = request.get_json(silent=True) or {}
    student_id = str(payload.get("studentId", "")).strip()

    if not student_id:
        audit_logger.info(
            "登录日志 time=%s ip=%s action=login status=failed studentId=%s reason=%s",
            datetime.datetime.now().isoformat(timespec="seconds"),
            _get_client_ip(),
            student_id,
            "studentId 不能为空",
        )
        return jsonify({"ok": False, "message": "studentId 不能为空"}), 400

    ok, data = login_student(student_id)
    ip = _get_client_ip()
    ip_location = _get_ip_location(ip)
    login_profile = data.get("loginProfile", {}) if isinstance(data.get("loginProfile"), dict) else {}
    student_name = str(data.get("studentName", "")).strip()
    user_id_text = str(data.get("userId", "")).strip()
    if ok and student_name:
        STUDENT_NAME_CACHE[student_id] = student_name
        if user_id_text:
            USER_NAME_CACHE[user_id_text] = student_name
    if ok and user_id_text and student_id:
        USER_STUDENT_ID_CACHE[user_id_text] = student_id
    g.student_name = student_name
    g.login_profile = login_profile
    data["ipLocation"] = {
        "country": ip_location.get("country", ""),
        "region": ip_location.get("region", ""),
        "city": ip_location.get("city", ""),
        "isp": ip_location.get("isp", ""),
        "text": _format_ip_location(ip_location),
        "queryStatus": ip_location.get("queryStatus", ""),
        "error": ip_location.get("error", ""),
        "国家": ip_location.get("country", ""),
        "省州": ip_location.get("region", ""),
        "城市": ip_location.get("city", ""),
        "运营商": ip_location.get("isp", ""),
        "归属地": _format_ip_location(ip_location),
        "查询状态": ip_location.get("queryStatus", ""),
        "失败原因": ip_location.get("error", ""),
    }

    audit_logger.info(
        "登录日志 time=%s ip=%s ipLocation=%s action=login status=%s studentId=%s studentName=%s userId=%s message=%s profile=%s",
        datetime.datetime.now().isoformat(timespec="seconds"),
        ip,
        _format_ip_location(ip_location),
        "success" if ok else "failed",
        student_id,
        student_name,
        str(data.get("userId", "")),
        str(data.get("message", "")),
        _format_login_profile_text(login_profile),
    )
    status = 200 if ok else 400
    return jsonify({"ok": ok, **data}), status


@app.get("/api/schedule")
def api_schedule() -> Any:
    user_id = str(request.args.get("userId", "")).strip()
    session_id = str(request.args.get("sessionId", "")).strip()
    date_str = str(request.args.get("dateStr", "")).strip()

    if not user_id or not session_id or not date_str:
        return jsonify({"ok": False, "message": "缺少 userId/sessionId/dateStr"}), 400
    if not _validate_date_str(date_str):
        return jsonify({"ok": False, "message": "dateStr 格式必须为 YYYYMMDD"}), 400

    ok, data = get_course_schedule(user_id, session_id, date_str)
    status = 200 if ok else 400
    student_id = _resolve_student_id(user_id=user_id)
    student_name = _resolve_student_name(student_id, user_id)
    return jsonify({"ok": ok, "dateStr": date_str, "studentName": student_name, **data}), status


@app.post("/api/sign")
def api_sign() -> Any:
    payload = request.get_json(silent=True) or {}
    user_id = str(payload.get("userId", "")).strip()
    session_id = str(payload.get("sessionId", "")).strip()
    course_sched_id = str(payload.get("courseSchedId", "")).strip()

    if not user_id or not session_id or not course_sched_id:
        return jsonify({"ok": False, "message": "缺少 userId/sessionId/courseSchedId"}), 400

    ok, data = sign_course(user_id, session_id, course_sched_id)
    status = 200 if ok else 400
    student_id = _resolve_student_id(user_id=user_id)
    student_name = _resolve_student_name(student_id, user_id)
    return jsonify(
        {
            "ok": ok,
            **data,
            "studentName": student_name,
            "status": str(data.get("status", "")).strip(),
            "errCode": str(data.get("errCode", "")).strip(),
            "errMsg": str(data.get("errMsg", "")).strip(),
            "signedCourses": [
                {
                    "courseSchedId": course_sched_id,
                    "courseName": "",
                    "dateStr": "",
                    "success": ok,
                }
            ]
            if ok
            else [],
        }
    ), status


@app.post("/api/sign/single-day")
def api_sign_single_day() -> Any:
    payload = request.get_json(silent=True) or {}
    user_id = str(payload.get("userId", "")).strip()
    session_id = str(payload.get("sessionId", "")).strip()
    date_str = str(payload.get("dateStr", "")).strip()
    mode = str(payload.get("mode", "all")).strip().lower()
    selected_ids = payload.get("selectedCourseIds") or []

    if not user_id or not session_id or not date_str:
        return jsonify({"ok": False, "message": "缺少 userId/sessionId/dateStr"}), 400
    if not _validate_date_str(date_str):
        return jsonify({"ok": False, "message": "dateStr 格式必须为 YYYYMMDD"}), 400
    if mode not in {"all", "selected"}:
        return jsonify({"ok": False, "message": "mode 仅支持 all 或 selected"}), 400

    ok, schedule_data = get_course_schedule(user_id, session_id, date_str)
    if not ok:
        return jsonify({"ok": False, "message": schedule_data.get("message", "查询课程失败")}), 400

    courses: List[Dict[str, str]] = schedule_data.get("courses", [])
    if mode == "selected":
        selected_set = {str(item) for item in selected_ids}
        courses = [course for course in courses if course.get("id") in selected_set]

    results = []
    success_count = 0
    for course in courses:
        sign_ok, sign_data = sign_course(user_id, session_id, course.get("id", ""))
        if sign_ok:
            success_count += 1
        results.append(
            _course_result(
                course,
                sign_ok,
                sign_data.get("message", ""),
                str(sign_data.get("status", "")).strip(),
                str(sign_data.get("errCode", "")).strip(),
                str(sign_data.get("errMsg", "")).strip(),
            )
        )
        time.sleep(0.3)

    return jsonify(
        {
            "ok": True,
            "dateStr": date_str,
            "studentName": _resolve_student_name(_resolve_student_id(user_id=user_id), user_id),
            "total": len(courses),
            "successCount": success_count,
            "failedCount": max(0, len(courses) - success_count),
            "allSuccess": success_count == len(courses),
            "results": results,
            "signedCourses": [
                {
                    "dateStr": date_str,
                    "courseSchedId": item.get("courseSchedId", ""),
                    "courseName": item.get("courseName", ""),
                    "success": item.get("success", False),
                }
                for item in results
                if bool(item.get("success"))
            ],
        }
    )


@app.post("/api/sign/range")
def api_sign_range() -> Any:
    payload = request.get_json(silent=True) or {}
    user_id = str(payload.get("userId", "")).strip()
    session_id = str(payload.get("sessionId", "")).strip()
    start_date = str(payload.get("startDate", "")).strip()
    end_date = str(payload.get("endDate", "")).strip()

    if not user_id or not session_id or not start_date or not end_date:
        return jsonify({"ok": False, "message": "缺少 userId/sessionId/startDate/endDate"}), 400
    if not _validate_date_str(start_date) or not _validate_date_str(end_date):
        return jsonify({"ok": False, "message": "日期格式必须为 YYYYMMDD"}), 400
    if start_date > end_date:
        return jsonify({"ok": False, "message": "startDate 不能大于 endDate"}), 400

    day_results: List[Dict[str, Any]] = []
    signed_courses: List[Dict[str, Any]] = []
    total_courses = 0
    total_success = 0

    for day in _date_range(start_date, end_date):
        ok, schedule_data = get_course_schedule(user_id, session_id, day)
        if not ok:
            day_results.append(
                {
                    "dateStr": day,
                    "ok": False,
                    "message": schedule_data.get("message", "查询课程失败"),
                    "courses": [],
                }
            )
            continue

        courses: List[Dict[str, str]] = schedule_data.get("courses", [])
        course_results: List[Dict[str, Any]] = []
        for course in courses:
            sign_ok, sign_data = sign_course(user_id, session_id, course.get("id", ""))
            if sign_ok:
                total_success += 1
                signed_courses.append(
                    {
                        "dateStr": day,
                        "courseSchedId": course.get("id", ""),
                        "courseName": course.get("courseName", ""),
                        "success": True,
                    }
                )
            total_courses += 1
            course_results.append(
                _course_result(
                    course,
                    sign_ok,
                    sign_data.get("message", ""),
                    str(sign_data.get("status", "")).strip(),
                    str(sign_data.get("errCode", "")).strip(),
                    str(sign_data.get("errMsg", "")).strip(),
                )
            )
            time.sleep(0.3)

        day_results.append({"dateStr": day, "ok": True, "message": "", "courses": course_results})

    return jsonify(
        {
            "ok": True,
            "startDate": start_date,
            "endDate": end_date,
            "studentName": _resolve_student_name(_resolve_student_id(user_id=user_id), user_id),
            "totalCourses": total_courses,
            "successCount": total_success,
            "failedCount": max(0, total_courses - total_success),
            "allSuccess": total_success == total_courses,
            "days": day_results,
            "signedCourses": signed_courses,
        }
    )


@app.post("/api/sign/continuous")
def api_sign_continuous() -> Any:
    payload = request.get_json(silent=True) or {}
    user_id = str(payload.get("userId", "")).strip()
    session_id = str(payload.get("sessionId", "")).strip()
    start_date = str(payload.get("startDate", "")).strip()
    max_days = int(payload.get("maxDays", 120))
    empty_stop_days = int(payload.get("emptyStopDays", 7))

    if not user_id or not session_id or not start_date:
        return jsonify({"ok": False, "message": "缺少 userId/sessionId/startDate"}), 400
    if not _validate_date_str(start_date):
        return jsonify({"ok": False, "message": "startDate 格式必须为 YYYYMMDD"}), 400
    if max_days <= 0 or empty_stop_days <= 0:
        return jsonify({"ok": False, "message": "maxDays 和 emptyStopDays 必须大于 0"}), 400

    current = datetime.datetime.strptime(start_date, "%Y%m%d")
    empty_count = 0
    day_results: List[Dict[str, Any]] = []
    signed_courses: List[Dict[str, Any]] = []
    total_courses = 0
    total_success = 0

    for _ in range(max_days):
        day = current.strftime("%Y%m%d")
        ok, schedule_data = get_course_schedule(user_id, session_id, day)

        if not ok:
            day_results.append(
                {
                    "dateStr": day,
                    "ok": False,
                    "message": schedule_data.get("message", "查询课程失败"),
                    "courses": [],
                }
            )
            empty_count += 1
            if empty_count >= empty_stop_days:
                break
            current += datetime.timedelta(days=1)
            continue

        courses: List[Dict[str, str]] = schedule_data.get("courses", [])
        if not courses:
            day_results.append({"dateStr": day, "ok": True, "message": "无课程", "courses": []})
            empty_count += 1
            if empty_count >= empty_stop_days:
                break
            current += datetime.timedelta(days=1)
            continue

        empty_count = 0
        course_results: List[Dict[str, Any]] = []
        for course in courses:
            sign_ok, sign_data = sign_course(user_id, session_id, course.get("id", ""))
            if sign_ok:
                total_success += 1
                signed_courses.append(
                    {
                        "dateStr": day,
                        "courseSchedId": course.get("id", ""),
                        "courseName": course.get("courseName", ""),
                        "success": True,
                    }
                )
            total_courses += 1
            course_results.append(
                _course_result(
                    course,
                    sign_ok,
                    sign_data.get("message", ""),
                    str(sign_data.get("status", "")).strip(),
                    str(sign_data.get("errCode", "")).strip(),
                    str(sign_data.get("errMsg", "")).strip(),
                )
            )
            time.sleep(0.3)

        day_results.append({"dateStr": day, "ok": True, "message": "", "courses": course_results})
        current += datetime.timedelta(days=1)

    return jsonify(
        {
            "ok": True,
            "startDate": start_date,
            "maxDays": max_days,
            "emptyStopDays": empty_stop_days,
            "studentName": _resolve_student_name(_resolve_student_id(user_id=user_id), user_id),
            "totalCourses": total_courses,
            "successCount": total_success,
            "failedCount": max(0, total_courses - total_success),
            "allSuccess": total_success == total_courses,
            "days": day_results,
            "signedCourses": signed_courses,
        }
    )


if __name__ == "__main__":
    # 降低 Flask 默认访问日志噪音，重点查看业务审计日志。
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("PORT") or os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)
