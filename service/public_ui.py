"""Same-origin customer-facing experiment workspace.

This deliberately stays dependency-free so the API container can serve the
first web experience without a second build system. A future PWA or native
client should call the same ``/customer/tickets`` channel contract.
"""

PUBLIC_LANDING_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#173b68">
  <title>Support Copilot · 客服助手</title>
  <link rel="icon" href="data:,">
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --ink: #17253b;
      --muted: #718097;
      --line: #e4eaf2;
      --panel: #ffffff;
      --canvas: #f4f7fb;
      --navy: #173b68;
      --blue: #2b6de8;
      --blue-soft: #eaf2ff;
      --green: #188458;
      --amber: #a36a16;
      --shadow: 0 18px 50px rgba(24, 48, 82, .10);
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-width: 320px; background: var(--canvas); color: var(--ink); }
    button, textarea { font: inherit; }
    button { cursor: pointer; }
    .app-shell { min-height: 100vh; display: flex; flex-direction: column; }
    .topbar { height: 72px; display: flex; align-items: center; justify-content: space-between; padding: 0 32px; background: var(--panel); border-bottom: 1px solid var(--line); }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-mark { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 11px; background: var(--navy); color: #fff; font-weight: 800; letter-spacing: -.05em; }
    .brand-name { font-size: 16px; font-weight: 760; letter-spacing: -.02em; }
    .brand-subtitle { margin-top: 2px; color: var(--muted); font-size: 12px; }
    .topbar-meta { display: flex; align-items: center; gap: 14px; color: var(--muted); font-size: 12px; }
    .status-pill { display: inline-flex; align-items: center; gap: 7px; padding: 7px 10px; border: 1px solid #ccebdd; border-radius: 999px; background: #f2fcf7; color: var(--green); font-weight: 700; }
    .status-dot { width: 7px; height: 7px; border-radius: 50%; background: #25aa70; box-shadow: 0 0 0 3px #d7f4e5; }
    .workspace { width: min(1380px, calc(100% - 48px)); flex: 1; display: grid; grid-template-columns: 250px minmax(0, 1fr) 280px; gap: 18px; margin: 24px auto; }
    .panel { min-width: 0; border: 1px solid var(--line); border-radius: 18px; background: var(--panel); box-shadow: var(--shadow); }
    .sidebar { padding: 22px 18px; }
    .eyebrow { margin: 0 0 8px; color: var(--blue); font-size: 11px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
    h1, h2, h3, p { margin-top: 0; }
    h1 { margin-bottom: 10px; font-size: 25px; line-height: 1.2; letter-spacing: -.04em; }
    h2 { margin-bottom: 5px; font-size: 15px; }
    h3 { margin-bottom: 8px; font-size: 12px; }
    .muted { color: var(--muted); }
    .sidebar-intro { margin-bottom: 24px; color: var(--muted); font-size: 13px; line-height: 1.65; }
    .side-section { padding-top: 18px; border-top: 1px solid var(--line); }
    .side-section + .side-section { margin-top: 18px; }
    .side-label { margin-bottom: 10px; color: var(--muted); font-size: 11px; font-weight: 760; letter-spacing: .08em; text-transform: uppercase; }
    .topic-list { display: grid; gap: 7px; }
    .topic-button { display: flex; align-items: center; width: 100%; padding: 10px 11px; border: 1px solid transparent; border-radius: 10px; background: transparent; color: #3b4b62; text-align: left; font-size: 13px; }
    .topic-button:hover, .topic-button:focus-visible { border-color: #cddcf5; background: var(--blue-soft); color: var(--navy); outline: none; }
    .topic-icon { width: 22px; color: var(--blue); font-weight: 800; }
    .new-session { width: 100%; padding: 10px 12px; border: 1px solid #bcd2f7; border-radius: 10px; background: var(--blue-soft); color: var(--navy); text-align: left; font-size: 13px; font-weight: 760; }
    .new-session:hover { border-color: #8bb0ef; box-shadow: 0 0 0 3px #e8f0ff; outline: none; }
    .sample-list { display: grid; gap: 7px; }
    .sample-button { display: block; width: 100%; padding: 9px 10px; border: 1px solid transparent; border-radius: 10px; background: transparent; color: #3b4b62; text-align: left; font-size: 12px; line-height: 1.45; }
    .sample-button:hover { border-color: #cddcf5; background: var(--blue-soft); color: var(--navy); outline: none; }
    .sample-button strong { display: block; color: var(--navy); font-size: 12px; }
    .sample-button span { display: block; margin-top: 2px; color: var(--muted); }
    .profile-grid { display: grid; gap: 9px; }
    .profile-field { display: grid; grid-template-columns: 42px 1fr; align-items: center; gap: 8px; color: #52657c; font-size: 12px; }
    .profile-select { width: 100%; padding: 7px 8px; border: 1px solid var(--line); border-radius: 8px; background: #fff; color: var(--ink); font-size: 12px; }
    .profile-note { margin: 9px 0 0; color: #9aa8bb; font-size: 10px; line-height: 1.45; }
    .safety-card { padding: 13px; border: 1px solid #d8e5f6; border-radius: 12px; background: #f7faff; color: #52657f; font-size: 12px; line-height: 1.6; }
    .safety-card strong { display: block; margin-bottom: 4px; color: var(--navy); }
    .conversation { display: flex; min-height: 680px; flex-direction: column; overflow: hidden; }
    .conversation-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 20px 24px; border-bottom: 1px solid var(--line); }
    .conversation-title { display: flex; align-items: center; gap: 10px; }
    .agent-avatar { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 11px; background: #e9f1ff; color: var(--blue); font-size: 13px; font-weight: 800; }
    .conversation-title h2 { margin: 0; font-size: 15px; }
    .conversation-title p { margin: 3px 0 0; color: var(--muted); font-size: 12px; }
    .conversation-actions { display: flex; align-items: center; gap: 10px; }
    .conversation-id { color: var(--muted); font-size: 11px; white-space: nowrap; }
    .clear-button { padding: 7px 9px; border: 1px solid var(--line); border-radius: 8px; background: #fff; color: #52657c; font-size: 11px; }
    .clear-button:hover { border-color: #bcd2f7; color: var(--navy); }
    .experiment-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 24px; border-bottom: 1px solid #eef2f7; background: #fbfcff; color: var(--muted); font-size: 11px; }
    .experiment-bar strong { color: var(--navy); }
    .messages { flex: 1; display: flex; flex-direction: column; gap: 16px; padding: 26px 28px; overflow-y: auto; }
    .message-row { display: flex; gap: 10px; max-width: 82%; }
    .message-row.user { align-self: flex-end; flex-direction: row-reverse; }
    .message-avatar { flex: 0 0 auto; display: grid; place-items: center; width: 28px; height: 28px; border-radius: 9px; background: #eef2f7; color: #5e7088; font-size: 11px; font-weight: 800; }
    .message-row.user .message-avatar { background: var(--navy); color: #fff; }
    .message-content { min-width: 0; }
    .message-meta { margin: 2px 0 5px; color: var(--muted); font-size: 11px; }
    .message-bubble { padding: 12px 14px; border: 1px solid var(--line); border-radius: 4px 14px 14px 14px; background: #fbfcfe; color: #34445b; font-size: 14px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
    .message-row.user .message-bubble { border-color: #c9dbfb; border-radius: 14px 4px 14px 14px; background: var(--blue); color: #fff; }
    .empty-state { margin: auto; padding: 26px; color: var(--muted); text-align: center; }
    .empty-state strong { display: block; margin-bottom: 6px; color: var(--navy); font-size: 14px; }
    .composer { padding: 16px 20px 20px; border-top: 1px solid var(--line); background: #fcfdff; }
    .composer-box { display: flex; align-items: flex-end; gap: 10px; padding: 8px 8px 8px 14px; border: 1px solid #ced9e8; border-radius: 14px; background: #fff; transition: border-color .15s, box-shadow .15s; }
    .composer-box:focus-within { border-color: #8bb0ef; box-shadow: 0 0 0 3px #e8f0ff; }
    textarea { width: 100%; min-height: 52px; max-height: 140px; resize: vertical; border: 0; outline: 0; color: var(--ink); line-height: 1.55; }
    textarea::placeholder { color: #9aa8bb; }
    .send-button { flex: 0 0 auto; padding: 10px 16px; border: 0; border-radius: 10px; background: var(--navy); color: #fff; font-size: 13px; font-weight: 760; }
    .send-button:hover { background: #24558d; }
    .send-button:disabled { cursor: wait; opacity: .55; }
    .composer-hint { margin: 9px 2px 0; color: var(--muted); font-size: 11px; }
    .inspector { padding: 22px 18px; }
    .inspector-section { padding-bottom: 20px; border-bottom: 1px solid var(--line); }
    .inspector-section + .inspector-section { padding-top: 20px; }
    .decision-card { padding: 14px; border: 1px solid #dce5f0; border-radius: 13px; background: #fbfcfe; }
    .decision-label { margin-bottom: 7px; color: var(--muted); font-size: 11px; font-weight: 760; letter-spacing: .08em; text-transform: uppercase; }
    .decision-value { color: var(--navy); font-size: 14px; font-weight: 800; }
    .decision-detail { margin-top: 7px; color: #62728a; font-size: 12px; line-height: 1.55; }
    .result-list { display: grid; gap: 9px; margin: 12px 0 0; padding: 0; list-style: none; }
    .result-item { display: flex; justify-content: space-between; gap: 10px; color: #52657c; font-size: 12px; }
    .result-item strong { color: var(--navy); font-weight: 700; text-align: right; }
    .guard-list { display: grid; gap: 9px; margin: 0; padding: 0; list-style: none; }
    .guard-item { display: flex; align-items: flex-start; gap: 8px; color: #52657c; font-size: 12px; line-height: 1.45; }
    .guard-check { color: var(--green); font-weight: 900; }
    .footer-note { padding: 0 28px 24px; color: #9aa8bb; font-size: 11px; text-align: center; }
    .error-banner { display: none; margin: 0 28px; padding: 10px 12px; border: 1px solid #f0d0cc; border-radius: 10px; background: #fff7f6; color: #a03f35; font-size: 12px; line-height: 1.5; }
    .error-banner.visible { display: block; }
    @media (max-width: 1060px) { .workspace { grid-template-columns: 210px minmax(0, 1fr); } .inspector { display: none; } }
    @media (max-width: 720px) { .topbar { height: 64px; padding: 0 16px; } .topbar-meta { gap: 0; } .topbar-meta > span:not(.status-pill) { display: none; } .workspace { width: 100%; margin: 0; display: block; } .sidebar { display: none; } .conversation { min-height: calc(100vh - 64px); border: 0; border-radius: 0; box-shadow: none; } .conversation-head { padding: 16px; } .conversation-id { display: none; } .messages { padding: 20px 16px; } .message-row { max-width: 92%; } .composer { padding: 12px 12px 16px; } .footer-note { padding: 0 16px 16px; } }
  </style>
</head>
<body>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">SC</div>
        <div><div class="brand-name">Support Copilot</div><div class="brand-subtitle">面向小型团队的智能客服入口</div></div>
      </div>
      <div class="topbar-meta"><span>安全演示通道</span><span class="status-pill"><span class="status-dot"></span>服务在线</span></div>
    </header>
    <main class="workspace">
      <aside class="panel sidebar">
        <p class="eyebrow">Experiment desk</p>
        <h1>快速试跑客服分流</h1>
        <p class="sidebar-intro">选择一个样例或输入自己的问题。每次提交都会展示自动回复、人工升级和依据状态，方便比较不同问题的处理边界。</p>
        <button id="new-session" class="new-session" type="button">＋ 新建试验会话</button>
        <div class="side-section"><div class="side-label"><span>一键试跑</span><span>4 条</span></div><div class="sample-list">
          <button class="sample-button" type="button" data-example="如何重置密码？"><strong>密码与登录</strong><span>应命中中文 FAQ 自动回复</span></button>
          <button class="sample-button" type="button" data-example="我想退款"><strong>退款与账单</strong><span>查看政策依据与回复边界</span></button>
          <button class="sample-button" type="button" data-example="如何导出文档？"><strong>知识库检索</strong><span>验证文档导出路径是否有依据</span></button>
          <button class="sample-button" type="button" data-example="我希望转人工处理。"><strong>人工接管</strong><span>验证用户主动请求如何分流</span></button>
        </div></div>
        <div class="side-section"><div class="side-label"><span>试验档案</span><span>本标签页有效</span></div><div class="profile-grid">
          <label class="profile-field"><span>方案</span><select id="profile-plan" class="profile-select"><option value="personal">Personal</option><option value="team" selected>Team</option><option value="enterprise">Enterprise</option></select></label>
          <label class="profile-field"><span>地区</span><select id="profile-region" class="profile-select"><option value="US" selected>US</option><option value="CN">中国</option><option value="EU">EU</option><option value="APAC">APAC</option></select></label>
          <label class="profile-field"><span>角色</span><select id="profile-role" class="profile-select"><option value="member" selected>Member</option><option value="admin">Admin</option><option value="owner">Owner</option></select></label>
        </div><p class="profile-note">仅发送方案、地区和角色等非敏感选择，不是账号登录，也不会保存密码。</p></div>
        <div class="side-section"><div class="safety-card"><strong>为什么有时不会直接回答？</strong>只有找到足够可靠的帮助中心依据，系统才会生成自动回复；没有依据或用户要求人工时，会保守升级。</div></div>
      </aside>
      <section class="panel conversation" aria-label="客服实验对话">
        <div class="conversation-head"><div class="conversation-title"><div class="agent-avatar">AI</div><div><h2>Support Copilot</h2><p>知识库分流助手 · 必要时建议人工接管</p></div></div><div class="conversation-actions"><span class="conversation-id">Web channel · beta</span><button id="clear-session" class="clear-button" type="button">清空记录</button></div></div>
        <div class="experiment-bar"><span>当前会话：<strong id="session-label">新建试验</strong></span><span>已提交 <strong id="message-count">0</strong> 次</span></div>
        <div id="messages" class="messages" aria-live="polite"><div class="empty-state"><strong>从左侧样例开始，或直接描述问题</strong><span>每条结果都会回到同一套确定性分流与 grounding 安全门。</span></div>
        </div>
        <div id="error-banner" class="error-banner" role="alert"></div>
        <form id="composer" class="composer"><div class="composer-box"><textarea id="ticket-text" rows="2" maxlength="2000" placeholder="例如：我无法登录账号，应该怎么办？"></textarea><button id="send-button" class="send-button" type="submit">发送</button></div><div class="composer-hint">Enter 发送 · Shift+Enter 换行 · 请不要填写密码、身份证号或其他敏感信息。</div></form>
        <div class="footer-note">公开实验通道只提供信息分流，不替代人工客服或业务系统的最终判断。</div>
      </section>
      <aside class="panel inspector">
        <div class="inspector-section"><p class="eyebrow">Decision guard</p><h2>本次结果</h2><div class="decision-card"><div class="decision-label">等待试验</div><div id="decision-value" class="decision-value">尚未提交问题</div><div id="decision-detail" class="decision-detail">提交后显示分流结论和面向用户的原因。</div><ul class="result-list"><li class="result-item"><span>依据状态</span><strong id="grounding-value">—</strong></li><li class="result-item"><span>后续动作</span><strong id="next-step-value">—</strong></li></ul></div></div>
        <div class="inspector-section"><h2>实验记录</h2><ul class="result-list"><li class="result-item"><span>最近问题</span><strong id="last-question">—</strong></li><li class="result-item"><span>当前档案</span><strong id="profile-summary">Team · US · Member</strong></li><li class="result-item"><span>记录位置</span><strong>当前浏览器标签页</strong></li></ul></div>
        <div class="inspector-section"><h2>安全边界</h2><ul class="guard-list"><li class="guard-item"><span class="guard-check">✓</span><span>自动回复必须有帮助中心证据支持</span></li><li class="guard-item"><span class="guard-check">✓</span><span>不确定的问题不会强行回答</span></li><li class="guard-item"><span class="guard-check">✓</span><span>当前版本不调用外部模型、不执行动作</span></li><li class="guard-item"><span class="guard-check">✓</span><span>人工请求不会伪装成已完成转接</span></li></ul></div>
        <div class="inspector-section"><h2>后续接入</h2><p class="muted" style="font-size:12px;line-height:1.6;">网页、微信小程序或企业微信后续都可以复用同一条客服会话协议；身份和真人收件箱将在有真实后端后再接入。</p></div>
      </aside>
    </main>
  </div>
  <script>
    const STORAGE_KEY = 'support-copilot-demo-session-v2';
    const messages = document.getElementById('messages');
    const form = document.getElementById('composer');
    const input = document.getElementById('ticket-text');
    const sendButton = document.getElementById('send-button');
    const errorBanner = document.getElementById('error-banner');
    const decisionValue = document.getElementById('decision-value');
    const decisionDetail = document.getElementById('decision-detail');
    const groundingValue = document.getElementById('grounding-value');
    const nextStepValue = document.getElementById('next-step-value');
    const lastQuestion = document.getElementById('last-question');
    const messageCount = document.getElementById('message-count');
    const sessionLabel = document.getElementById('session-label');
    const profilePlan = document.getElementById('profile-plan');
    const profileRegion = document.getElementById('profile-region');
    const profileRole = document.getElementById('profile-role');
    const profileSummary = document.getElementById('profile-summary');
    const decisionLabels = { AUTO_REPLY: '可以先参考这条回复', ESCALATE_L1: '建议人工进一步确认', ESCALATE_L2: '需要人工优先处理', UNKNOWN: '暂时无法自动判断' };
    const nextLabels = { customer_can_continue: '用户可继续', human_review_recommended: '建议人工处理', priority_human_review_recommended: '优先人工处理' };
    let submitted = 0;

    function profile() { return { plan: profilePlan.value, region: profileRegion.value, role: profileRole.value }; }
    function updateProfileSummary() { profileSummary.textContent = `${profilePlan.value[0].toUpperCase()}${profilePlan.value.slice(1)} · ${profileRegion.value} · ${profileRole.value[0].toUpperCase()}${profileRole.value.slice(1)}`; }

    function addMessage(role, text) {
      const row = document.createElement('div');
      row.className = 'message-row ' + role;
      const avatar = document.createElement('div');
      avatar.className = 'message-avatar';
      avatar.textContent = role === 'user' ? '我' : 'AI';
      const content = document.createElement('div');
      content.className = 'message-content';
      const meta = document.createElement('div');
      meta.className = 'message-meta';
      meta.textContent = role === 'user' ? '你 · 刚刚' : 'Support Copilot · 刚刚';
      const bubble = document.createElement('div');
      bubble.className = 'message-bubble';
      bubble.textContent = text;
      content.append(meta, bubble);
      row.append(avatar, content);
      messages.appendChild(row);
      messages.scrollTop = messages.scrollHeight;
    }

    function persist() { try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ html: messages.innerHTML, submitted, last: lastQuestion.textContent })); } catch (_) {} }
    function restore() { try { const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null'); if (!saved || !saved.html || saved.html.includes('empty-state')) return; messages.innerHTML = saved.html; submitted = Number(saved.submitted || 0); messageCount.textContent = String(submitted); lastQuestion.textContent = saved.last || '—'; sessionLabel.textContent = '已恢复试验'; } catch (_) {} }
    function resetSession() { sessionStorage.removeItem(STORAGE_KEY); messages.innerHTML = '<div class="empty-state"><strong>从左侧样例开始，或直接描述问题</strong><span>每条结果都会回到同一套确定性分流与 grounding 安全门。</span></div>'; submitted = 0; messageCount.textContent = '0'; lastQuestion.textContent = '—'; sessionLabel.textContent = '新建试验'; decisionValue.textContent = '尚未提交问题'; decisionDetail.textContent = '提交后显示分流结论和面向用户的原因。'; groundingValue.textContent = '—'; nextStepValue.textContent = '—'; clearError(); input.focus(); }

    function showError(text) { errorBanner.textContent = text; errorBanner.classList.add('visible'); }
    function clearError() { errorBanner.textContent = ''; errorBanner.classList.remove('visible'); }

    async function submitTicket(text) {
      const response = await fetch('/customer/tickets', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify({ ticket_text: text, profile: profile() }) });
      let body = {};
      try { body = await response.json(); } catch (_) { body = {}; }
      if (!response.ok) throw new Error(body.detail || '客服入口暂时不可用，请稍后再试。');
      const label = decisionLabels[body.decision] || '已收到问题';
      decisionValue.textContent = label;
      decisionDetail.textContent = body.reason || '系统已完成本次分流。';
      groundingValue.textContent = body.grounding_safe ? '已命中帮助中心' : '未形成安全自动回复';
      nextStepValue.textContent = nextLabels[body.next_step] || '需要进一步确认';
      lastQuestion.textContent = text.length > 28 ? text.slice(0, 28) + '…' : text;
      submitted += 1; messageCount.textContent = String(submitted); sessionLabel.textContent = '进行中';
      addMessage('assistant', body.reply || '这个问题需要人工进一步核验，我不会在缺少依据时替你做出承诺。'); persist();
    }

    async function run(text) { if (!text || sendButton.disabled) return; clearError(); addMessage('user', text); input.value = ''; sendButton.disabled = true; sendButton.textContent = '处理中…'; try { await submitTicket(text); } catch (error) { showError(error.message); } finally { sendButton.disabled = false; sendButton.textContent = '发送'; input.focus(); } }
    form.addEventListener('submit', (event) => { event.preventDefault(); run(input.value.trim()); });
    input.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); } });

    document.querySelectorAll('[data-example]').forEach((button) => button.addEventListener('click', () => run(button.dataset.example)));
    document.getElementById('new-session').addEventListener('click', resetSession);
    document.getElementById('clear-session').addEventListener('click', resetSession);
    [profilePlan, profileRegion, profileRole].forEach((select) => select.addEventListener('change', updateProfileSummary));
    updateProfileSummary(); restore();
  </script>
</body>
</html>"""
