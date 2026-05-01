#!/usr/bin/env python3
"""
代码审核机器人 - 主入口 v2.0
对提交的代码进行安全、合规、Bug 检测，生成带评分的审核报告

支持：
- Issue 正文中的代码块审核
- PR diff 差异代码审核
- 评分机制（0-100）
- 恶意代码检测（含严重等级）
- 敏感信息泄露检测
- 代码复杂度分析
"""

import os
import sys
import json
import re
import subprocess
import tempfile
import hashlib
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ─── 常量 ───────────────────────────────────────────────

CST = timezone(timedelta(hours=8))

SCORE_PASS = 70
SCORE_WARN = 50

# 恶意代码模式: (正则, 描述, 严重等级, 修复建议)
MALICIOUS_PATTERNS = [
    # 命令注入
    (r"os\.system\s*\(", "命令注入: os.system",
     "HIGH", "避免使用 os.system，改用 subprocess.run(shell=False)"),
    (r"subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True",
     "命令注入: subprocess shell=True",
     "HIGH", "将 shell=True 改为 shell=False，避免 shell 注入"),
    (r"eval\s*\(", "代码执行: eval",
     "CRITICAL", "禁止使用 eval，它可执行任意代码，用 ast.literal_eval 替代"),
    (r"exec\s*\(", "代码执行: exec",
     "CRITICAL", "禁止使用 exec，它可执行任意代码"),
    (r"__import__\s*\(", "动态导入: __import__",
     "HIGH", "避免动态导入，如需导入请使用 importlib.import_module"),
    (r"compile\s*\(", "代码编译: compile",
     "HIGH", "避免使用 compile 编译动态代码"),

    # 反序列化
    (r"pickle\.loads?\s*\(", "不安全反序列化: pickle",
     "CRITICAL", "pickle 可执行任意代码，改用 json 或 safer alternatives"),
    (r"marshal\.loads?\s*\(", "不安全反序列化: marshal",
     "CRITICAL", "marshal 不安全，不要用于不可信数据"),
    (r"shelve\.open\s*\(", "不安全反序列化: shelve",
     "MEDIUM", "shelve 基于 pickle，注意不要加载不可信数据"),

    # 文件操作
    (r"open\s*\(\s*['\"]/", "绝对路径文件操作",
     "MEDIUM", "避免硬编码绝对路径，使用相对路径或配置"),
    (r"os\.remove\s*\(", "文件删除: os.remove",
     "MEDIUM", "使用前检查路径合法性，防止路径遍历"),
    (r"shutil\.rmtree\s*\(", "目录删除: shutil.rmtree",
     "HIGH", "确认目标路径，防止误删重要目录"),
    (r"glob\.glob\s*\(\s*['\"]/", "路径遍历风险: glob",
     "LOW", "注意 glob 匹配结果，防止路径遍历"),

    # 网络操作
    (r"requests\.(get|post)\s*\([^)]*verify\s*=\s*False",
     "禁用 SSL 验证",
     "HIGH", "不应禁用 SSL 验证，会导致中间人攻击风险"),
    (r"urllib\.request\.urlopen\s*\(",
     "原始 HTTP 请求: urllib",
     "LOW", "建议使用 requests 库，更安全易用"),
    (r"socket\.",
     "底层网络操作: socket",
     "MEDIUM", "确保连接目标和数据经过验证"),

    # 权限/信息泄露
    (r"os\.chmod\s*\(\s*[^,]+,\s*0o777",
     "过度宽松的文件权限: 0777",
     "MEDIUM", "避免设置 0777 权限，最小权限原则"),

    # 环境变量
    (r"environ\s*\[", "环境变量访问",
     "LOW", "确认不会泄露敏感环境变量（API Key、密码等）"),

    # 其他
    (r"getattr\s*\(\s*[^,]+,\s*['\"]__",
     "动态属性访问: getattr __",
     "HIGH", "避免访问 dunder 属性，可能导致意外行为"),
    (r"setattr\s*\(\s*[^,]+,\s*['\"]__",
     "动态属性修改: setattr __",
     "HIGH", "避免修改 dunder 属性，可能导致意外行为"),
    (r"type\s*\(\s*[^)]+\)\s*\.__",
     "反射操作",
     "MEDIUM", "确认反射操作的目标可控"),
]

# 敏感信息模式: (正则, 描述)
SECRET_PATTERNS = [
    (r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]{4,}['\"]",
     "硬编码密码 (password=)"),
    (r"(?i)(api[_-]?key|apikey)\s*=\s*['\"][^'\"]{8,}['\"]",
     "硬编码 API Key"),
    (r"(?i)(secret|token|auth)\s*=\s*['\"][^'\"]{8,}['\"]",
     "硬编码密钥/令牌 (secret/token/auth=)"),
    (r"(?i)(sk-|pk_)[a-zA-Z0-9]{20,}",
     "疑似 OpenAI / Stripe API Key"),
    (r"ghp_[a-zA-Z0-9]{36}",
     "GitHub Personal Access Token"),
    (r"gho_[a-zA-Z0-9]{36}",
     "GitHub OAuth Token"),
    (r"glpat-[a-zA-Z0-9\-]{20,}",
     "GitLab Personal Access Token"),
    (r"(?i)AKIA[0-9A-Z]{16}",
     "AWS Access Key"),
    (r"(?i)AIza[0-9A-Za-z\-_]{35}",
     "Google API Key"),
    (r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----",
     "私钥文件内容"),
]


# ─── GitHub 交互 ─────────────────────────────────────────

def get_event_payload():
    """读取 GitHub Actions 事件 payload"""
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return None
    with open(event_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_issue_content():
    """获取 Issue 中的内容，返回 (title, body, username)"""
    payload = get_event_payload()
    if not payload or "issue" not in payload:
        return None, None, None
    title = payload["issue"].get("title", "")
    body = payload["issue"].get("body", "")
    # 获取提交用户名
    user = payload["issue"].get("user", {})
    username = user.get("login", "未知用户")
    return title, body, username


def get_pr_changed_files():
    """获取 PR 中变更的文件内容"""
    payload = get_event_payload()
    if not payload or "pull_request" not in payload:
        return []

    pr = payload["pull_request"]
    base_sha = pr.get("base", {}).get("sha", "")

    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    if not token or not repo:
        print("缺少 GITHUB_TOKEN 或 GITHUB_REPOSITORY")
        return []

    # 获取变更文件列表
    changed_files = []
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/pulls/{payload['number']}/files",
             "--paginate", "--jq", '.[].filename'],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "GH_TOKEN": token}
        )
        if result.returncode == 0:
            filenames = result.stdout.strip().split("\n")
            for fn in filenames:
                fn = fn.strip()
                if fn and fn.endswith(".py"):
                    # 获取文件内容
                    content_result = subprocess.run(
                        ["gh", "api", f"repos/{repo}/contents/{fn}",
                         "--jq", '.content'],
                        capture_output=True, text=True, timeout=30,
                        env={**os.environ, "GH_TOKEN": token}
                    )
                    if content_result.returncode == 0:
                        import base64
                        try:
                            content = base64.b64decode(content_result.stdout.strip()).decode("utf-8")
                            changed_files.append((fn, content))
                        except Exception:
                            pass
    except Exception as e:
        print(f"获取 PR 文件失败: {e}")

    return changed_files


# ─── 代码提取 ────────────────────────────────────────────

def extract_code_from_markdown(text):
    """从 Markdown 中提取代码块，返回 [(语言, 代码, 起始行), ...]"""
    blocks = []
    for match in re.finditer(r"```(\w*)\n(.*?)```", text, re.DOTALL):
        lang = match.group(1) or "text"
        code = match.group(2)
        line_no = text[:match.start()].count("\n") + 1
        blocks.append((lang, code, line_no))
    return blocks


# ─── 检查引擎 ────────────────────────────────────────────

def run_bandit(code_path):
    """Bandit 安全扫描"""
    try:
        result = subprocess.run(
            ["bandit", "-f", "json", "-ll", "-r", code_path],
            capture_output=True, text=True, timeout=60
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            return data.get("results", [])
        return []
    except Exception:
        return []


def run_ruff(code_path):
    """Ruff 代码风格检查"""
    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format=json", code_path],
            capture_output=True, text=True, timeout=60
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
        return []
    except Exception:
        return []


def run_pylint(code_path):
    """Pylint Bug 检测"""
    # 先生成 pylint 配置禁用过于严格的规则
    try:
        result = subprocess.run(
            ["pylint", "--output-format=json", "--disable=C0114,C0115,C0116,C0301,C0303,C0304,C0305,W0611,W0612,W0613,W0621,W0622,R0401,R0801,R0901,R0903,R0911,R0912,R0913,R0914,R0915,R1702,R1705,E0401,E1101,W0603",
             code_path],
            capture_output=True, text=True, timeout=120
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
        return []
    except Exception:
        return []


def check_malicious(code):
    """恶意代码模式检测"""
    findings = []
    for pattern, desc, severity, fix in MALICIOUS_PATTERNS:
        matches = list(re.finditer(pattern, code, re.MULTILINE))
        if matches:
            # 计算行号
            lines = []
            for m in matches:
                line = code[:m.start()].count("\n") + 1
                lines.append(line)
            findings.append({
                "desc": desc,
                "severity": severity,
                "lines": lines[:3],  # 最多显示3处
                "fix": fix,
                "count": len(matches),
            })
    return findings


def check_secrets(code):
    """敏感信息泄露检测"""
    findings = []
    for pattern, desc in SECRET_PATTERNS:
        matches = list(re.finditer(pattern, code))
        if matches:
            lines = []
            for m in matches:
                line = code[:m.start()].count("\n") + 1
                lines.append(line)
            # 脱敏显示匹配内容
            findings.append({
                "desc": desc,
                "lines": lines[:3],
                "count": len(matches),
            })
    return findings


def analyze_complexity(code):
    """代码复杂度分析"""
    lines = code.strip().split("\n")
    total_lines = len(lines)
    blank_lines = sum(1 for l in lines if not l.strip())
    comment_lines = sum(1 for l in lines if l.strip().startswith("#"))
    code_lines = total_lines - blank_lines - comment_lines

    # 估算圈复杂度（简化版：统计分支关键字）
    branch_keywords = re.findall(
        r"\b(if|elif|else|for|while|try|except|with|and|or)\b", code
    )
    cyclomatic = max(1, len(branch_keywords))

    # 函数数量
    func_count = len(re.findall(r"def\s+\w+\s*\(", code))
    class_count = len(re.findall(r"class\s+\w+", code))

    return {
        "total_lines": total_lines,
        "code_lines": code_lines,
        "blank_lines": blank_lines,
        "comment_lines": comment_lines,
        "comment_ratio": round(comment_lines / max(total_lines, 1) * 100, 1),
        "cyclomatic": cyclomatic,
        "func_count": func_count,
        "class_count": class_count,
    }


# ─── 评分系统 ────────────────────────────────────────────

def calculate_score(malicious, secrets, bandit, ruff, pylint, complexity):
    """计算代码评分 (0-100)"""
    score = 100
    deductions = []

    # 恶意代码扣分（重罚）
    severity_scores = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 8, "LOW": 3}
    for f in malicious:
        d = severity_scores.get(f["severity"], 5)
        score -= d
        deductions.append(f"{f['desc']}: -{d} ({f['severity']})")

    # 敏感信息扣分
    for f in secrets:
        d = 15
        score -= d
        deductions.append(f"{f['desc']}: -{d}")

    # Bandit 扣分
    for issue in bandit:
        severity = issue.get("issue_severity", "LOW")
        d = severity_scores.get(severity, 3)
        score -= d
        deductions.append(f"Bandit: {issue.get('issue_text', '?')}: -{d}")

    # Ruff 扣分（每10个问题扣2分，上限10分）
    if ruff:
        d = min(len(ruff) * 0.2, 10)
        score -= d
        if d > 0:
            deductions.append(f"Ruff: {len(ruff)} 个问题: -{round(d)}")

    # Pylint 扣分（error 重罚，warning 轻罚）
    for issue in pylint:
        if issue.get("type") == "error":
            score -= 3
        else:
            score -= 1

    # 复杂度扣分
    if complexity["cyclomatic"] > 20:
        score -= 5
        deductions.append(f"圈复杂度过高 ({complexity['cyclomatic']}): -5")
    if complexity["code_lines"] > 500:
        score -= 3
        deductions.append(f"代码行数过多 ({complexity['code_lines']}行): -3")
    if complexity["comment_ratio"] < 5 and complexity["code_lines"] > 30:
        score -= 3
        deductions.append(f"注释不足 ({complexity['comment_ratio']}%): -3")

    score = max(0, min(100, round(score)))
    return score, deductions


# ─── 报告生成 ────────────────────────────────────────────

def severity_icon(severity):
    """根据严重等级返回图标"""
    return {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(severity, "⚪")


def score_badge(score):
    """根据分数返回徽章"""
    if score >= 90:
        return "🟢 优秀"
    elif score >= SCORE_PASS:
        return "🟡 良好"
    elif score >= SCORE_WARN:
        return "🟠 需改进"
    else:
        return "🔴 不合格"


def generate_report(username, code_name, code_content, malicious, secrets, bandit, ruff, pylint, complexity):
    """生成单个代码块的审核报告"""
    score, deductions = calculate_score(malicious, secrets, bandit, ruff, pylint, complexity)
    report = []

    # 标题 - 新格式
    report.append(f"## 🤖 AI代码审核报告 for {username}")
    report.append("")
    report.append("您好！我已经对你提交的插件代码进行了初步自动化审核，作为初步参考:")
    report.append("")
    report.append(f"**审核时间**: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**代码来源**: {code_name}")
    report.append(f"**代码评分**: **{score}/100** {score_badge(score)}")
    report.append("")

    # 总览卡片
    total_critical = sum(1 for f in malicious if f["severity"] == "CRITICAL")
    total_high = sum(1 for f in malicious if f["severity"] == "HIGH")
    total_medium = sum(1 for f in malicious if f["severity"] == "MEDIUM")
    total_low = sum(1 for f in malicious if f["severity"] == "LOW")
    total_secrets = len(secrets)
    total_bandit = len(bandit)
    total_ruff = len(ruff)
    total_bugs = sum(1 for b in pylint if b.get("type") == "error")

    report.append("### 📊 审核总览")
    report.append("")
    report.append(f"| 检查项 | 结果 |")
    report.append(f"|--------|------|")
    report.append(f"| 🔴 严重问题 | {total_critical} |")
    report.append(f"| 🟠 高危问题 | {total_high} |")
    report.append(f"| 🟡 中危问题 | {total_medium} |")
    report.append(f"| 🟢 低危问题 | {total_low} |")
    report.append(f"| 🔑 敏感信息 | {total_secrets} |")
    report.append(f"| 🔒 安全扫描 (Bandit) | {total_bandit} |")
    report.append(f"| 📋 代码风格 (Ruff) | {total_ruff} |")
    report.append(f"| 🐛 Bug (Pylint) | {total_bugs} |")
    report.append(f"| 📏 代码行数 | {complexity['code_lines']} |")
    report.append(f"| 🔄 圈复杂度 | {complexity['cyclomatic']} |")
    report.append(f"| 💬 注释比例 | {complexity['comment_ratio']}% |")
    report.append("")

    # 恶意代码详情
    if malicious:
        report.append("<details>")
        report.append("<summary><b>⚠️ 恶意代码检测（点击展开详情）</b></summary>")
        report.append("")
        for f in malicious:
            icon = severity_icon(f["severity"])
            report.append(f"#### {icon} {f['desc']}")
            report.append(f"- **严重等级**: {f['severity']}")
            report.append(f"- **出现次数**: {f['count']} 次")
            report.append(f"- **行号**: {', '.join(str(l) for l in f['lines'])}")
            report.append(f"- **修复建议**: {f['fix']}")
            report.append("")
        report.append("</details>")
        report.append("")

    # 敏感信息详情
    if secrets:
        report.append("<details>")
        report.append("<summary><b>🔑 敏感信息检测（点击展开详情）</b></summary>")
        report.append("")
        for f in secrets:
            report.append(f"- **{f['desc']}**: 出现 {f['count']} 次，行号 {', '.join(str(l) for l in f['lines'])}")
        report.append("")
        report.append("</details>")
        report.append("")

    # Bandit 详情
    if bandit:
        report.append("<details>")
        report.append("<summary><b>🔒 Bandit 安全扫描详情（点击展开）</b></summary>")
        report.append("")
        for issue in bandit[:10]:
            sev = issue.get("issue_severity", "LOW")
            report.append(f"- {severity_icon(sev)} **{issue.get('issue_text', '?')}** (行 {issue.get('line_number', '?')}, {issue.get('issue_cwe', {}).get('id', '')})")
        if len(bandit) > 10:
            report.append(f"- *...还有 {len(bandit) - 10} 个问题*")
        report.append("")
        report.append("</details>")
        report.append("")

    # Ruff 详情
    if ruff:
        report.append("<details>")
        report.append("<summary><b>📋 Ruff 代码风格详情（点击展开）</b></summary>")
        report.append("")
        for item in ruff[:10]:
            loc = item.get("location", {})
            report.append(f"- {item.get('type', '?')} 行 {loc.get('row', '?')}: {item.get('message', '')} ({item.get('code', '')})")
        if len(ruff) > 10:
            report.append(f"- *...还有 {len(ruff) - 10} 个问题*")
        report.append("")
        report.append("</details>")
        report.append("")

    # Pylint 详情
    bug_items = [b for b in pylint if b.get("type") in ("error", "warning")]
    if bug_items:
        report.append("<details>")
        report.append("<summary><b>🐛 Pylint Bug 检测详情（点击展开）</b></summary>")
        report.append("")
        for item in bug_items[:10]:
            icon = "❌" if item.get("type") == "error" else "⚠️"
            report.append(f"- {icon} 行 {item.get('line', '?')}, 列 {item.get('column', '?')}: {item.get('message', '')} ({item.get('symbol', '')})")
        if len(bug_items) > 10:
            report.append(f"- *...还有 {len(bug_items) - 10} 个问题*")
        report.append("")
        report.append("</details>")
        report.append("")

    # 评分扣分明细
    if deductions:
        report.append("<details>")
        report.append("<summary><b>📝 评分扣分明细（点击展开）</b></summary>")
        report.append("")
        report.append(f"| 扣分项 | 分值 |")
        report.append(f"|--------|------|")
        for d in deductions:
            # 提取 -N
            match = re.search(r"(-\d+)", d)
            val = match.group(1) if match else "?"
            reason = d.split(":")[0] if ":" in d else d
            report.append(f"| {reason} | {val} |")
        report.append(f"| **最终得分** | **{score}/100** |")
        report.append("")
        report.append("</details>")
        report.append("")

    # 总结
    report.append("### 📋 审核结论")
    report.append("")
    if score >= SCORE_PASS and total_critical == 0 and total_secrets == 0:
        report.append(f"✅ **审核通过** — 代码评分 **{score}/100**，质量良好。")
        if total_high + total_medium > 0:
            report.append(f"建议修复 {total_high + total_medium} 个中高危问题后合并。")
    elif score >= SCORE_WARN and total_critical == 0:
        report.append(f"⚠️ **审核通过（有警告）** — 代码评分 **{score}/100**，建议修复后合并。")
        report.append(f"共发现 {total_high + total_medium} 个高危/中危问题。")
    else:
        report.append(f"❌ **审核未通过** — 代码评分 **{score}/100**，存在严重问题。")
        if total_critical > 0:
            report.append(f"- 发现 **{total_critical}** 个严重问题，必须修复！")
        if total_secrets > 0:
            report.append(f"- 发现 **{total_secrets}** 处疑似敏感信息泄露，必须处理！")

    report.append("")
    report.append("---")
    report.append("*此报告由 Code Review Bot v2.0 自动生成 | 审核标准参考 OWASP Top 10 + PEP 8*")

    return "\n".join(report), score


# ─── 主函数 ──────────────────────────────────────────────

def main():
    payload = get_event_payload()
    event_name = os.environ.get("EVENT_NAME", "unknown")

    # 获取用户名
    username = "未知用户"
    if event_name == "pull_request":
        username = get_pr_username()
    else:
        _, _, username = get_issue_content()

    all_reports = []
    total_score = 0
    code_count = 0

    if event_name == "pull_request":
        # PR 模式：审核变更文件
        changed_files = get_pr_changed_files()
        if not changed_files:
            print("未找到变更的 Python 文件")
            sys.exit(1)

        for filename, content in changed_files:
            with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
                f.write(content)
                tmp_path = f.name

            try:
                malicious = check_malicious(content)
                secrets = check_secrets(content)
                bandit = run_bandit(tmp_path)
                ruff = run_ruff(tmp_path)
                pylint = run_pylint(tmp_path)
                complexity = analyze_complexity(content)

                report_text, score = generate_report(username, filename, content, malicious, secrets, bandit, ruff, pylint, complexity)
                all_reports.append(report_text)
                total_score += score
                code_count += 1
            finally:
                os.unlink(tmp_path)

    else:
        # Issue 模式：审核代码块
        title, body, username = get_issue_content()
        if not body:
            print("未找到代码内容")
            sys.exit(1)

        code_blocks = extract_code_from_markdown(body)
        if not code_blocks:
            print("未在 Issue 中找到代码块")
            sys.exit(1)

        for i, (lang, code, line_no) in enumerate(code_blocks):
            ext = {"python": ".py", "py": ".py"}.get(lang.lower(), ".txt")
            code_name = f"代码块 #{i + 1} ({lang})"

            with tempfile.NamedTemporaryFile(suffix=ext, mode="w", delete=False, encoding="utf-8") as f:
                f.write(code)
                tmp_path = f.name

            try:
                malicious = check_malicious(code)
                secrets = check_secrets(code)
                bandit_results = []
                ruff_results = []
                pylint_results = []

                if lang.lower() in ("python", "py"):
                    bandit_results = run_bandit(tmp_path)
                    ruff_results = run_ruff(tmp_path)
                    pylint_results = run_pylint(tmp_path)

                complexity = analyze_complexity(code)

                report_text, score = generate_report(username, code_name, code, malicious, secrets, bandit_results, ruff_results, pylint_results, complexity)
                all_reports.append(report_text)
                total_score += score
                code_count += 1
            finally:
                os.unlink(tmp_path)

    # 合并所有报告
    if not all_reports:
        print("没有可审核的代码")
        sys.exit(1)

    final_report = "\n\n---\n\n".join(all_reports)

    if code_count > 1:
        avg_score = round(total_score / code_count)
        header = f"## 📊 综合评分: **{avg_score}/100** {score_badge(avg_score)}\n\n"
        header += f"共审核 **{code_count}** 段代码\n\n---\n\n"
        final_report = header + final_report

    # 保存报告
    report_file = Path("review_report.md")
    report_file.write_text(final_report, encoding="utf-8")
    print(f"审核报告已生成: {report_file}")


if __name__ == "__main__":
    main()
