# 📬 科技早报

每天早上 9:00（北京时间）自动发送邮件，包含：
- 📰 **昨日科技新闻** — 信息技术与教育领域，精确摘要
- ⭐ **GitHub Top 5 热门项目** — 本周最火的开源仓库，含 README 概述

无需电脑开机，GitHub Actions 云端执行。

## 项目结构

```
├── daily_news_collector.py      # 主脚本
├── news_config.json             # 非敏感配置
├── requirements.txt             # Python 依赖
├── .github/workflows/
│   └── daily-news.yml           # 定时触发配置
└── news_logs/                   # 运行日志（artifact）
```

## 配置 Secrets

仓库 Settings → Secrets and variables → Actions → New repository secret：

| Secret | 说明 |
|--------|------|
| `SENDER_EMAIL` | 发件 QQ 邮箱 |
| `SENDER_PASSWORD` | QQ 邮箱 SMTP 授权码 |
| `RECEIVER_EMAIL` | 收件邮箱 |
| `TianAPI_KEY` | 天行数据 API Key |

## 手动测试

Actions → 每日新闻收集 → Run workflow
