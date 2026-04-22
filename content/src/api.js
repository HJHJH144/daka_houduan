const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000';
const INVITE_TOKEN_KEY = 'inviteToken';

export function getInviteToken() {
    return window.sessionStorage.getItem(INVITE_TOKEN_KEY) || '';
}

export function setInviteToken(token) {
    if (!token) {
        return;
    }
    window.sessionStorage.setItem(INVITE_TOKEN_KEY, token);
}

export function clearInviteToken() {
    window.sessionStorage.removeItem(INVITE_TOKEN_KEY);
}

async function request(path, options = {}) {
    const inviteToken = getInviteToken();
    const response = await fetch(`${API_BASE_URL}${path}`, {
        headers: {
            'Content-Type': 'application/json',
            ...(inviteToken ? { 'X-Invite-Token': inviteToken } : {}),
            ...(options.headers || {}),
        },
        ...options,
    });

    let payload = {};
    try {
        payload = await response.json();
    } catch {
        payload = { ok: false, message: '服务返回了不可解析的数据' };
    }

    if (!response.ok || payload.ok === false) {
        if (payload.code === 'INVITE_TOKEN_INVALID') {
            clearInviteToken();
        }
        const error = new Error(payload.message || `请求失败: ${response.status}`);
        error.status = response.status;
        error.payload = payload;
        throw error;
    }

    return payload;
}

export function verifyInviteCode(inviteCode) {
    return request('/api/invite/verify', {
        method: 'POST',
        body: JSON.stringify({ inviteCode }),
    });
}

export function fetchInviteStatus() {
    return request('/api/invite/status');
}

export function login(studentId) {
    return request('/api/login', {
        method: 'POST',
        body: JSON.stringify({ studentId }),
    });
}

export function fetchSchedule({ userId, sessionId, dateStr }) {
    const query = new URLSearchParams({ userId, sessionId, dateStr });
    return request(`/api/schedule?${query.toString()}`);
}

export function signSingleDay({ userId, sessionId, dateStr, mode, selectedCourseIds }) {
    return request('/api/sign/single-day', {
        method: 'POST',
        body: JSON.stringify({ userId, sessionId, dateStr, mode, selectedCourseIds }),
    });
}

export function signRange({ userId, sessionId, startDate, endDate }) {
    return request('/api/sign/range', {
        method: 'POST',
        body: JSON.stringify({ userId, sessionId, startDate, endDate }),
    });
}

export function signContinuous({ userId, sessionId, startDate, maxDays = 120, emptyStopDays = 7 }) {
    return request('/api/sign/continuous', {
        method: 'POST',
        body: JSON.stringify({ userId, sessionId, startDate, maxDays, emptyStopDays }),
    });
}
