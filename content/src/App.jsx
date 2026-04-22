import { useEffect, useMemo, useState } from 'react';
import {
  clearInviteToken,
  fetchInviteStatus,
  fetchSchedule,
  getInviteToken,
  login,
  setInviteToken,
  signContinuous,
  signRange,
  signSingleDay,
  verifyInviteCode,
} from './api';
import './App.css';

function fmtTimeRange(begin, end) {
  const safeBegin = typeof begin === 'string' ? begin : '';
  const safeEnd = typeof end === 'string' ? end : '';
  return `${safeBegin.slice(0, 10)} ${safeBegin.slice(11, 16)}-${safeEnd.slice(11, 16)}`;
}

function normalizeDateInput(raw) {
  return raw.replaceAll('-', '').trim();
}

function formatCurrentDateTime(date) {
  return date.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function formatCooldownText(totalSeconds) {
  const safeSeconds = Math.max(0, Number(totalSeconds) || 0);
  const minute = String(Math.floor(safeSeconds / 60)).padStart(2, '0');
  const second = String(safeSeconds % 60).padStart(2, '0');
  return `${minute}:${second}`;
}

function formatSignFailureReason(item) {
  const reason = String(item?.errMsg || item?.message || '').trim();
  const errCode = String(item?.errCode || '').trim();
  if (!reason && !errCode) {
    return '';
  }
  if (reason && errCode) {
    return `${reason} (ERRCODE=${errCode})`;
  }
  return reason || `ERRCODE=${errCode}`;
}

function getSummaryFeedback(successCount, totalCount, title) {
  const total = Math.max(0, Number(totalCount) || 0);
  const success = Math.max(0, Number(successCount) || 0);
  const failed = Math.max(0, total - success);

  if (total === 0) {
    return {
      level: 'info',
      text: `${title}: 没有可打卡课程`,
    };
  }

  if (failed === 0) {
    return {
      level: 'success',
      text: `${title}: 全部成功 ${success}/${total}`,
    };
  }

  if (success === 0) {
    return {
      level: 'error',
      text: `${title}: 全部失败 0/${total}`,
    };
  }

  return {
    level: 'error',
    text: `${title}: 部分成功 ${success}/${total}，失败 ${failed}`,
  };
}

function App() {
  const [studentId, setStudentId] = useState('');
  const [auth, setAuth] = useState(null);
  const [mode, setMode] = useState('single');
  const [dateStr, setDateStr] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [continuousStartDate, setContinuousStartDate] = useState('');
  const [maxDays, setMaxDays] = useState('');
  const [emptyStopDays, setEmptyStopDays] = useState('');
  const [courses, setCourses] = useState([]);
  const [selectedCourseIds, setSelectedCourseIds] = useState([]);
  const [selectAll, setSelectAll] = useState(true);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('请先登录');
  const [logs, setLogs] = useState([]);
  const [currentTime, setCurrentTime] = useState(() => formatCurrentDateTime(new Date()));
  const [inviteCode, setInviteCode] = useState('');
  const [inviteVerified, setInviteVerified] = useState(() => Boolean(getInviteToken()));
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteMessage, setInviteMessage] = useState('请输入邀请码后进入平台');
  const [attemptsLeft, setAttemptsLeft] = useState(3);
  const [cooldownRemainingSec, setCooldownRemainingSec] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(formatCurrentDateTime(new Date()));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (cooldownRemainingSec <= 0) {
      return () => { };
    }
    const timer = setInterval(() => {
      setCooldownRemainingSec((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [cooldownRemainingSec]);

  useEffect(() => {
    if (inviteVerified) {
      return () => { };
    }

    let cancelled = false;
    (async () => {
      try {
        const status = await fetchInviteStatus();
        if (cancelled) {
          return;
        }
        setAttemptsLeft(Number(status.attemptsLeft ?? 3));
        setCooldownRemainingSec(Number(status.cooldownRemainingSec ?? 0));
        if (Number(status.cooldownRemainingSec ?? 0) > 0) {
          setInviteMessage('当前设备处于冷却中，请稍后重试');
        }
      } catch {
        if (!cancelled) {
          setInviteMessage('无法同步邀请码状态，请稍后重试');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [inviteVerified]);

  const canUseSystem = useMemo(() => Boolean(auth?.userId && auth?.sessionId), [auth]);

  function pushLog(text, level = 'info') {
    const stamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    setLogs((prev) => [{ id: `${Date.now()}-${Math.random()}`, text, level, stamp }, ...prev]);
  }

  function handleInviteInvalid(error) {
    if (error?.payload?.code !== 'INVITE_TOKEN_INVALID') {
      return false;
    }
    clearInviteToken();
    setInviteVerified(false);
    setAttemptsLeft(3);
    setCooldownRemainingSec(0);
    setInviteMessage('邀请码已失效，请重新输入邀请码');
    setAuth(null);
    setMessage('邀请码已失效，请重新验证');
    return true;
  }

  async function handleInviteSubmit(event) {
    event.preventDefault();
    if (cooldownRemainingSec > 0) {
      return;
    }
    const code = inviteCode.trim();
    if (!code) {
      setInviteMessage('请输入邀请码');
      return;
    }

    setInviteLoading(true);
    try {
      const res = await verifyInviteCode(code);
      setInviteToken(res.inviteToken);
      setInviteVerified(true);
      setInviteMessage('邀请码验证通过');
      setAttemptsLeft(3);
      setCooldownRemainingSec(0);
      setInviteCode('');
    } catch (error) {
      const payload = error?.payload || {};
      setAttemptsLeft(Number(payload.attemptsLeft ?? attemptsLeft));
      setCooldownRemainingSec(Number(payload.cooldownRemainingSec ?? 0));
      setInviteMessage(error.message || '邀请码验证失败');
    } finally {
      setInviteLoading(false);
    }
  }

  async function handleLogin(event) {
    event.preventDefault();
    const trimmed = studentId.trim();
    if (!trimmed) {
      setMessage('请输入学号');
      return;
    }

    setLoading(true);
    setMessage('登录中...');
    try {
      const res = await login(trimmed);
      setAuth({ userId: res.userId, sessionId: res.sessionId, studentId: trimmed });
      const displayName = String(res.studentName || trimmed).trim() || trimmed;
      setMessage('登录成功');
      pushLog(`登录成功，userId=${res.userId}`, 'success');
      window.alert(`（${displayName}）你不乘哦`);
    } catch (error) {
      if (handleInviteInvalid(error)) {
        return;
      }
      setAuth(null);
      setMessage(error.message);
      pushLog(`登录失败: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  }

  async function handleQuerySingleDay() {
    if (!canUseSystem) {
      setMessage('请先登录');
      return;
    }

    const normalized = normalizeDateInput(dateStr);
    if (!/^\d{8}$/.test(normalized)) {
      setMessage('单日日期格式应为 YYYYMMDD 或 YYYY-MM-DD');
      return;
    }

    setLoading(true);
    setMessage('查询课程中...');
    try {
      const res = await fetchSchedule({
        userId: auth.userId,
        sessionId: auth.sessionId,
        dateStr: normalized,
      });
      setCourses(res.courses || []);
      setSelectAll(true);
      setSelectedCourseIds((res.courses || []).map((course) => course.id));
      setMessage(`查询完成，共 ${res.courses?.length || 0} 门课程`);
      pushLog(`${normalized} 查询成功，课程数: ${res.courses?.length || 0}`, 'success');
    } catch (error) {
      if (handleInviteInvalid(error)) {
        return;
      }
      setCourses([]);
      setSelectedCourseIds([]);
      setMessage(error.message);
      pushLog(`单日查询失败: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  }

  function toggleCourse(courseId) {
    setSelectedCourseIds((prev) => {
      if (prev.includes(courseId)) {
        const next = prev.filter((item) => item !== courseId);
        setSelectAll(false);
        return next;
      }
      const next = [...prev, courseId];
      setSelectAll(next.length === courses.length && courses.length > 0);
      return next;
    });
  }

  function toggleSelectAll(value) {
    setSelectAll(value);
    setSelectedCourseIds(value ? courses.map((course) => course.id) : []);
  }

  async function handleSignSingleDay() {
    if (!canUseSystem) {
      setMessage('请先登录');
      return;
    }

    const normalized = normalizeDateInput(dateStr);
    if (!/^\d{8}$/.test(normalized)) {
      setMessage('单日日期格式应为 YYYYMMDD 或 YYYY-MM-DD');
      return;
    }

    if (!selectAll && selectedCourseIds.length === 0) {
      setMessage('请至少选择一门课程');
      return;
    }

    setLoading(true);
    setMessage('单日打卡执行中...');

    try {
      const res = await signSingleDay({
        userId: auth.userId,
        sessionId: auth.sessionId,
        dateStr: normalized,
        mode: selectAll ? 'all' : 'selected',
        selectedCourseIds,
      });

      const summary = getSummaryFeedback(res.successCount, res.total, `单日 ${res.dateStr}`);
      setMessage(summary.text);
      pushLog(summary.text, summary.level);
      for (const item of res.results || []) {
        const prefix = item.success ? '成功' : '失败';
        const level = item.success ? 'success' : 'error';
        const failureReason = formatSignFailureReason(item);
        const suffix = !item.success && failureReason ? `，原因: ${failureReason}` : '';
        pushLog(`${prefix}: ${item.courseName} (${fmtTimeRange(item.classBeginTime, item.classEndTime)})${suffix}`, level);
      }
    } catch (error) {
      if (handleInviteInvalid(error)) {
        return;
      }
      setMessage(error.message);
      pushLog(`单日打卡失败: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  }

  async function handleSignRange() {
    if (!canUseSystem) {
      setMessage('请先登录');
      return;
    }

    const start = normalizeDateInput(startDate);
    const end = normalizeDateInput(endDate);
    if (!/^\d{8}$/.test(start) || !/^\d{8}$/.test(end)) {
      setMessage('日期范围格式应为 YYYYMMDD 或 YYYY-MM-DD');
      return;
    }

    setLoading(true);
    setMessage('区间打卡执行中...');
    try {
      const res = await signRange({ userId: auth.userId, sessionId: auth.sessionId, startDate: start, endDate: end });
      const summary = getSummaryFeedback(res.successCount, res.totalCourses, `区间 ${res.startDate}-${res.endDate}`);
      setMessage(summary.text);
      pushLog(summary.text, summary.level);

      for (const day of res.days || []) {
        if (!day.ok) {
          pushLog(`${day.dateStr} 查询失败: ${day.message}`, 'error');
          continue;
        }
        if ((day.courses || []).length === 0) {
          pushLog(`${day.dateStr} 无课程`, 'info');
          continue;
        }
        for (const course of day.courses) {
          const prefix = course.success ? '成功' : '失败';
          const level = course.success ? 'success' : 'error';
          const failureReason = formatSignFailureReason(course);
          const suffix = !course.success && failureReason ? `，原因: ${failureReason}` : '';
          pushLog(`${day.dateStr} ${prefix}: ${course.courseName}${suffix}`, level);
        }
      }
    } catch (error) {
      if (handleInviteInvalid(error)) {
        return;
      }
      setMessage(error.message);
      pushLog(`区间打卡失败: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  }

  async function handleSignContinuous() {
    if (!canUseSystem) {
      setMessage('请先登录');
      return;
    }

    const start = normalizeDateInput(continuousStartDate);
    if (!/^\d{8}$/.test(start)) {
      setMessage('连续打卡起始日期格式应为 YYYYMMDD 或 YYYY-MM-DD');
      return;
    }

    setLoading(true);
    setMessage('连续打卡执行中...');
    try {
      const parsedMaxDays = Number(maxDays);
      const parsedEmptyStopDays = Number(emptyStopDays);
      const res = await signContinuous({
        userId: auth.userId,
        sessionId: auth.sessionId,
        startDate: start,
        maxDays: parsedMaxDays > 0 ? parsedMaxDays : 120,
        emptyStopDays: parsedEmptyStopDays > 0 ? parsedEmptyStopDays : 7,
      });

      const summary = getSummaryFeedback(res.successCount, res.totalCourses, `连续打卡(起始 ${res.startDate})`);
      setMessage(summary.text);
      pushLog(summary.text, summary.level);

      for (const day of res.days || []) {
        if (!day.ok) {
          pushLog(`${day.dateStr} 查询失败: ${day.message}`, 'error');
          continue;
        }
        if ((day.courses || []).length === 0) {
          pushLog(`${day.dateStr} ${day.message || '无课程'}`, 'info');
          continue;
        }
        for (const course of day.courses) {
          const prefix = course.success ? '成功' : '失败';
          const level = course.success ? 'success' : 'error';
          const failureReason = formatSignFailureReason(course);
          const suffix = !course.success && failureReason ? `，原因: ${failureReason}` : '';
          pushLog(`${day.dateStr} ${prefix}: ${course.courseName}${suffix}`, level);
        }
      }
    } catch (error) {
      if (handleInviteInvalid(error)) {
        return;
      }
      setMessage(error.message);
      pushLog(`连续打卡失败: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  }

  if (!inviteVerified) {
    return (
      <div className="page-shell gate-shell">
        <main className="gate-card">
          <p className="badge">Access Gate</p>
          <h1>请输入邀请码</h1>
          <p className="hint">邀请码错误达到 3 次会进入 30 分钟冷却。</p>
          <form className="row" onSubmit={handleInviteSubmit}>
            <input
              type="password"
              value={inviteCode}
              onChange={(event) => setInviteCode(event.target.value)}
              placeholder="请输入邀请码"
              disabled={inviteLoading || cooldownRemainingSec > 0}
            />
            <button type="submit" disabled={inviteLoading || cooldownRemainingSec > 0}>
              {inviteLoading ? '验证中...' : '进入平台'}
            </button>
          </form>
          <p className="hint">剩余尝试次数：{attemptsLeft}</p>
          {cooldownRemainingSec > 0 && (
            <p className="cooldown-text">冷却中，请在 {formatCooldownText(cooldownRemainingSec)} 后重试。</p>
          )}
          <p className="hint">{inviteMessage}</p>
        </main>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <header className="hero">
        <div>
          <p className="badge">BUAA iClass</p>
          <h1>课程打卡平台</h1>
        </div>
        <div className="status-box">
          <p>状态</p>
          <strong>{loading ? '处理中' : canUseSystem ? '已登录' : '未登录'}</strong>
          <span>{message}</span>
          <p className="clock-label">当前时间</p>
          <strong className="clock-value">{currentTime}</strong>
        </div>
      </header>

      <main className="layout">
        <section className="panel">
          <h2>1. 登录</h2>
          <form className="row" onSubmit={handleLogin}>
            <input
              value={studentId}
              onChange={(event) => setStudentId(event.target.value)}
              placeholder="请输入学号"
              disabled={loading}
            />
            <button type="submit" disabled={loading}>登录</button>
          </form>
          {auth && (
            <p className="hint">
              当前账号: {auth.studentId} | userId: {auth.userId}
            </p>
          )}
        </section>

        <section className="panel">
          <h2>2. 模式选择</h2>
          <div className="mode-tabs">
            <button className={mode === 'single' ? 'active' : ''} onClick={() => setMode('single')} disabled={loading}>
              单日
            </button>
            <button className={mode === 'range' ? 'active' : ''} onClick={() => setMode('range')} disabled={loading}>
              日期范围
            </button>
            <button className={mode === 'continuous' ? 'active' : ''} onClick={() => setMode('continuous')} disabled={loading}>
              连续打卡
            </button>
          </div>

          {mode === 'single' && (
            <div className="mode-body">
              <div className="row">
                <input
                  type="date"
                  value={dateStr}
                  onChange={(event) => setDateStr(event.target.value)}
                  disabled={loading}
                />
                <button onClick={handleQuerySingleDay} disabled={loading || !canUseSystem}>查询课程</button>
                <button onClick={handleSignSingleDay} disabled={loading || !canUseSystem}>执行打卡</button>
              </div>

              <div className="row check-row">
                <label>
                  <input
                    type="checkbox"
                    checked={selectAll}
                    onChange={(event) => toggleSelectAll(event.target.checked)}
                    disabled={loading || courses.length === 0}
                  />
                  打卡全部课程
                </label>
              </div>

              <div className="course-list">
                {courses.length === 0 ? (
                  <p className="hint">暂无课程数据，请先查询。</p>
                ) : (
                  courses.map((course) => (
                    <label key={course.id} className="course-item">
                      <input
                        type="checkbox"
                        checked={selectAll || selectedCourseIds.includes(course.id)}
                        onChange={() => toggleCourse(course.id)}
                        disabled={loading || selectAll}
                      />
                      <span className="course-title">{course.courseName}</span>
                      <span className="course-time">{fmtTimeRange(course.classBeginTime, course.classEndTime)}</span>
                    </label>
                  ))
                )}
              </div>
            </div>
          )}

          {mode === 'range' && (
            <div className="mode-body">
              <div className="row">
                <input
                  type="date"
                  value={startDate}
                  onChange={(event) => setStartDate(event.target.value)}
                  disabled={loading}
                />
                <input
                  type="date"
                  value={endDate}
                  onChange={(event) => setEndDate(event.target.value)}
                  disabled={loading}
                />
                <button onClick={handleSignRange} disabled={loading || !canUseSystem}>执行区间打卡</button>
              </div>
            </div>
          )}

          {mode === 'continuous' && (
            <div className="mode-body">
              <div className="continuous-grid">
                <label className="field-group">
                  <span className="field-label">起始日期</span>
                  <input
                    type="date"
                    value={continuousStartDate}
                    onChange={(event) => setContinuousStartDate(event.target.value)}
                    disabled={loading}
                  />
                  <small className="field-help">从这一天开始向后自动查课并打卡。</small>
                </label>
                <label className="field-group">
                  <span className="field-label">最大尝试天数</span>
                  <input
                    type="number"
                    value={maxDays}
                    onChange={(event) => setMaxDays(event.target.value)}
                    placeholder="示例：120"
                    min="1"
                    disabled={loading}
                  />
                  <small className="field-help">最多向后处理多少天，防止无限执行。</small>
                </label>
                <label className="field-group">
                  <span className="field-label">连续无课停止天数</span>
                  <input
                    type="number"
                    value={emptyStopDays}
                    onChange={(event) => setEmptyStopDays(event.target.value)}
                    placeholder="示例：7"
                    min="1"
                    disabled={loading}
                  />
                  <small className="field-help">连续这么多天无课程时自动停止任务。</small>
                </label>
              </div>
              <p className="mode-note">示例：起始日期填今天，最大尝试天数 120，连续无课停止天数 7。</p>
              <div className="row">
                <button onClick={handleSignContinuous} disabled={loading || !canUseSystem}>执行连续打卡</button>
              </div>
            </div>
          )}
        </section>

        <section className="panel logs-panel">
          <h2>执行日志</h2>
          <div className="logs">
            {logs.length === 0 ? (
              <p className="hint">暂无日志。</p>
            ) : (
              logs.map((log) => (
                <div key={log.id} className={`log-item ${log.level}`}>
                  <span>{log.stamp}</span>
                  <p>{log.text}</p>
                </div>
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
