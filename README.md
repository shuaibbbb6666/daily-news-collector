# 📰 每日新闻收集器

每天早上 9:00（北京时间）自动收集信息技术与教育领域的新闻，并通过邮件发送。

## 工作原理

- **数据源**：[天行数据](https://www.tianapi.com/) generalnews API
- **关键词筛选**：教育、AI、大数据、云计算、芯片、5G 等 30+ 个关键词
- **调度方式**：GitHub Actions 定时触发（无需电脑开机）
- **邮件发送**：通过 QQ 邮箱 SMTP 发送 HTML 格式简报

## 项目结构

```
├── daily_news_collector.py      # 主脚本
├── news_config.json             # 非敏感配置（SMTP 服务器等）
├── requirements.txt             # Python 依赖
├── .github/workflows/
│   └── daily-news.yml           # GitHub Actions 工作流定义
└── news_logs/                   # 每次运行的日志（artifact 保留 30 天）
```

## 配置 Secrets

在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 中添加以下 Secrets：

| Secret 名称 | 说明 |
|-------------|------|
| `SENDER_EMAIL` | 发送邮件的 QQ 邮箱地址 |
| `SENDER_PASSWORD` | QQ 邮箱 SMTP 授权码 |
| `RECEIVER_EMAIL` | 接收新闻的邮箱地址 |
| `TianAPI_KEY` | 天行数据 API Key |

## 手动测试

在 GitHub 仓库的 **Actions** 标签页，选择「每日新闻收集」→ **Run workflow** 即可立即执行一次。

## 本地测试

```bash
# 设置环境变量
export SENDER_EMAIL="your_email@qq.com"
export SENDER_PASSWORD="your_smtp_code"
export RECEIVER_EMAIL="receiver@example.com"
export TianAPI_KEY="your_api_key"

# 安装依赖并运行
pip install -r requirements.txt
python daily_news_collector.py
```
