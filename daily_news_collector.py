#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日新闻收集脚本 - 信息技术与教育领域
每天早上 9:00（北京时间）通过 GitHub Actions 自动运行
敏感信息通过环境变量注入，不再硬编码在文件中
"""

import os
import json
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import List, Dict

import requests


# ==================== 配置区域 ====================
# 敏感信息从环境变量读取（由 GitHub Secrets 注入）

EMAIL_CONFIG = {
    "smtp_server": os.getenv("SMTP_SERVER", "smtp.qq.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", "465")),
    "sender_email": os.getenv("SENDER_EMAIL", ""),
    "sender_name": os.getenv("SENDER_NAME", "新闻助手"),
    "sender_password": os.getenv("SENDER_PASSWORD", ""),
    "receiver_email": os.getenv("RECEIVER_EMAIL", ""),
}

TIANAPI_CONFIG = {
    "api_key": os.getenv("TianAPI_KEY", ""),
    "base_url": "https://apis.tianapi.com",
    "api_name": "generalnews",
}

# 教育和信息技术相关的关键词
KEYWORDS = [
    "教育", "学校", "大学", "高校", "教师", "学生", "教学", "学习",
    "人工智能", "AI", "机器学习", "大数据", "云计算", "物联网",
    "互联网", "5G", "芯片", "科技", "技术", "数字化", "智能化",
    "ChatGPT", "大模型", "LLM", "AIGC", "自动驾驶", "新能源",
    "机器人", "量子", "卫星", "航天",
]

# 非敏感配置可以从 JSON 文件加载（可选）
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "news_config.json")

# 日志保存目录（GitHub Actions 中通过 artifact 上传）
LOG_DIR = os.path.join(os.path.dirname(__file__), "news_logs")

# =================================================


class NewsCollector:
    """新闻收集器类"""

    def __init__(self):
        self.news_items: List[Dict] = []
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def load_config(self):
        """加载非敏感配置文件（可选）"""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                email_cfg = config.get("email", {})
                for key in ("smtp_server", "smtp_port"):
                    if key in email_cfg and not os.getenv(
                        key.upper() if key != "smtp_port" else "SMTP_PORT"
                    ):
                        if key == "smtp_port":
                            EMAIL_CONFIG[key] = int(email_cfg[key])
                        else:
                            EMAIL_CONFIG[key] = email_cfg[key]

    def search_news(self) -> List[Dict]:
        """从天行数据 API 获取新闻"""
        yesterday = datetime.now() - timedelta(days=1)
        yesterday_chinese = yesterday.strftime("%Y年%m月%d日")
        news_list: List[Dict] = []

        try:
            url = f"{TIANAPI_CONFIG['base_url']}/{TIANAPI_CONFIG['api_name']}/index"
            params = {
                "key": TIANAPI_CONFIG["api_key"],
                "num": 50,
                "page": 1,
            }

            print(f"正在调用天行数据 API: {url}")
            response = requests.get(url, params=params, timeout=15)

            if response.status_code == 200:
                data = response.json()

                if data.get("code") == 200 and "result" in data:
                    news_items = data["result"].get("newslist", [])

                    for item in news_items:
                        title = item.get("title", "")
                        description = item.get("description", "")

                        is_relevant = any(
                            keyword in title or keyword in description
                            for keyword in KEYWORDS
                        )

                        if is_relevant:
                            ctime = item.get("ctime", "")
                            date_str = (
                                ctime.split()[0] if ctime else yesterday_chinese
                            )

                            news_list.append({
                                "title": title,
                                "summary": (
                                    description[:200] + "..."
                                    if description
                                    else "暂无摘要"
                                ),
                                "source": item.get("source", "未知来源"),
                                "date": date_str,
                                "url": item.get("url", ""),
                            })

                    news_list = news_list[:12]

            print(f"API 返回代码: {data.get('code')}, 消息: {data.get('msg')}")

        except Exception as e:
            print(f"获取新闻时出错: {e}")
            news_list = [
                {
                    "title": f"新闻收集暂时不可用 - {yesterday_chinese}",
                    "summary": f"错误信息: {str(e)}，请稍后检查...",
                    "source": "系统提示",
                    "date": yesterday_chinese,
                    "url": "https://www.baidu.com",
                }
            ]

        self.news_items = news_list
        return news_list

    def format_news_report(self, news_data: List[Dict]) -> str:
        """格式化新闻报告为 HTML 邮件"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y年%m月%d日")
        today = datetime.now().strftime("%Y年%m月%d日")
        now_time = datetime.now().strftime("%H:%M")

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif; background: #f5f7fa; margin: 0; padding: 20px; color: #333; }}
  .container {{ max-width: 680px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); overflow: hidden; }}
  .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; padding: 28px 30px; text-align: center; }}
  .header h1 {{ margin: 0; font-size: 22px; letter-spacing: 2px; }}
  .header .date {{ margin-top: 8px; font-size: 13px; opacity: 0.9; }}
  .summary-bar {{ background: #f0f4ff; padding: 12px 30px; font-size: 13px; color: #555; border-bottom: 1px solid #e8ecf1; }}
  .news-list {{ padding: 10px 24px; }}
  .news-item {{ padding: 16px 0; border-bottom: 1px solid #f0f0f0; }}
  .news-item:last-child {{ border-bottom: none; }}
  .news-item .index {{ display: inline-block; background: #667eea; color: #fff; width: 24px; height: 24px; line-height: 24px; text-align: center; border-radius: 50%; font-size: 12px; margin-right: 8px; vertical-align: middle; }}
  .news-item .title {{ font-size: 16px; font-weight: 600; color: #222; margin: 6px 0; }}
  .news-item .title a {{ color: #222; text-decoration: none; }}
  .news-item .title a:hover {{ color: #667eea; }}
  .news-item .summary {{ font-size: 13px; color: #666; line-height: 1.6; margin: 6px 0; }}
  .news-item .meta {{ font-size: 12px; color: #999; }}
  .footer {{ background: #fafbfc; padding: 20px 30px; text-align: center; font-size: 12px; color: #aaa; border-top: 1px solid #e8ecf1; }}
  .footer a {{ color: #667eea; text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📰 信息技术与教育 · 每日简报</h1>
    <div class="date">{yesterday} 新闻汇总</div>
  </div>
  <div class="summary-bar">
    📅 整理时间：{today} {now_time} &nbsp;|&nbsp; 📊 共收录 <b>{len(news_data)}</b> 条相关新闻
  </div>
  <div class="news-list">
"""

        for i, news in enumerate(news_data, 1):
            url_link = (
                f'<a href="{news["url"]}" target="_blank">{news["title"]}</a>'
                if news["url"]
                else news["title"]
            )
            html += f"""
    <div class="news-item">
      <div><span class="index">{i}</span><span class="meta">来源：{news['source']}</span></div>
      <div class="title">{url_link}</div>
      <div class="summary">{news['summary']}</div>
    </div>"""

        html += f"""
  </div>
  <div class="footer">
    本简报由自动化脚本通过 <a href="https://github.com/features/actions">GitHub Actions</a> 定时生成<br>
    内容仅供参考，请以官方发布为准 · 如有疑问请联系 zqha@vip.163.com
  </div>
</div>
</body>
</html>"""

        return html

    def send_email(self, subject: str, html_content: str) -> bool:
        """发送 HTML 邮件"""
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = formataddr(
                (EMAIL_CONFIG["sender_name"], EMAIL_CONFIG["sender_email"])
            )
            msg["To"] = EMAIL_CONFIG["receiver_email"]
            msg["Subject"] = subject

            plain_text = (
                f"每日新闻简报 - 共 {len(self.news_items)} 条新闻。"
                "请使用支持 HTML 的邮件客户端查看完整内容。"
            )
            msg.attach(MIMEText(plain_text, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            with smtplib.SMTP_SSL(
                EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]
            ) as server:
                server.login(
                    EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"]
                )
                server.sendmail(
                    EMAIL_CONFIG["sender_email"],
                    [EMAIL_CONFIG["receiver_email"]],
                    msg.as_string(),
                )

            print(f"✅ 邮件已成功发送到 {EMAIL_CONFIG['receiver_email']}")
            return True

        except Exception as e:
            print(f"❌ 邮件发送失败：{e}")
            return False

    def save_log(self, report_html: str):
        """保存日志到本地文件（在 GitHub Actions 中会上传为 artifact）"""
        os.makedirs(LOG_DIR, exist_ok=True)
        log_file = os.path.join(
            LOG_DIR, f"news_{datetime.now().strftime('%Y%m%d')}.txt"
        )

        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y年%m月%d日")
        plain = f"每日新闻简报 - {yesterday}\n{'=' * 50}\n\n"
        for i, news in enumerate(self.news_items, 1):
            plain += f"[{i}] {news['title']}\n"
            plain += f"    来源: {news['source']}\n"
            plain += f"    链接: {news['url']}\n"
            plain += f"    摘要: {news['summary']}\n\n"

        with open(log_file, "w", encoding="utf-8") as f:
            f.write(plain)

        print(f"📝 日志已保存到：{log_file}")

    def run(self):
        """主运行函数"""
        print("🚀 开始收集每日新闻...")

        if not TIANAPI_CONFIG["api_key"]:
            print("❌ 错误：未设置 TianAPI_KEY 环境变量！")
            return
        if not EMAIL_CONFIG["sender_password"]:
            print("❌ 错误：未设置 SENDER_PASSWORD 环境变量！")
            return

        self.load_config()

        print("📰 正在从天行数据获取新闻...")
        news_data = self.search_news()
        print(f"✅ 共收集到 {len(news_data)} 条新闻")

        report_html = self.format_news_report(news_data)

        self.save_log(report_html)

        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y年%m月%d日")
        subject = f"📰 信息技术与教育领域新闻简报 - {yesterday}"
        success = self.send_email(subject, report_html)

        if success:
            print("✨ 任务完成！邮件已发送。")
        else:
            print("⚠️ 任务部分完成：邮件发送失败，请检查配置。")
            exit(1)


def main():
    collector = NewsCollector()
    collector.run()


if __name__ == "__main__":
    main()
