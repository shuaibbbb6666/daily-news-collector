#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日新闻收集脚本 — 信息技术与教育领域
+ GitHub 热门项目 Top 5
每天早上 9:00（北京时间）通过 GitHub Actions 自动运行
"""

import os
import json
import re
import smtplib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import List, Dict, Optional

import xml.etree.ElementTree as ET

import requests


# ==================== 配置 ====================

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

KEYWORDS = [
    # 科技核心
    "科技", "AI", "人工智能", "技术", "数据", "互联网", "信息",
    "手机", "电脑", "机器人", "芯片", "半导体", "5G", "6G", "通信",
    "网络", "软件", "硬件", "数码", "智能", "数字化", "智能化",
    # 前沿领域
    "航天", "卫星", "太空", "NASA", "SpaceX", "特斯拉", "新能源",
    "电池", "电动", "自动驾驶", "无人机", "3D打印", "量子", "纳米",
    "生物", "基因", "医疗", "科学", "研究", "发明", "专利",
    # AI & 大模型
    "ChatGPT", "GPT", "大模型", "LLM", "AIGC", "OpenAI", "Google",
    "微软", "苹果", "华为", "深度学习", "算法",
    # 互联网公司
    "小米", "字节", "腾讯", "阿里", "百度", "京东", "美团", "拼多多",
    "抖音", "微信", "支付宝", "电商", "支付",
    # 游戏/娱乐科技
    "游戏", "电竞", "虚拟", "元宇宙", "VR", "AR",
    # 安全 & 开发
    "安全", "隐私", "黑客", "漏洞", "创业", "融资", "上市", "投资",
    "编程", "开源", "GitHub", "代码", "Python", "云", "服务器",
    # 教育
    "教育", "学校", "大学", "高校", "学生", "教师", "教学", "课程", "专业",
]

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "news_config.json")
LOG_DIR = os.path.join(os.path.dirname(__file__), "news_logs")

# GitHub Trending 配置
GITHUB_TRENDING_DAYS = 7  # 抓取最近 N 天的热门项目
_36KR_FEED = "https://36kr.com/feed"  # 36氪 RSS

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# =================================================


def fetch_article_detail(url: str, timeout: int = 8) -> str:
    """从新闻原文 URL 提取详细描述（meta description 或首段文字）"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text

        # 尝试提取 og:description
        m = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html)
        if m:
            return m.group(1).strip()

        # 尝试提取 meta description
        m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html)
        if m:
            return m.group(1).strip()

        # 尝试提取第一段有意义的 <p> 文字
        # 去掉 script/style 标签
        cleaned = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        cleaned = re.sub(r'<style[^>]*>.*?</style>', '', cleaned, flags=re.DOTALL)
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', cleaned, flags=re.DOTALL)
        for p in paragraphs:
            text = re.sub(r'<[^>]+>', '', p).strip()
            # 过滤太短或明显不是正文的段落
            if len(text) > 30 and not text.startswith("<"):
                return text[:300]

        return ""
    except Exception:
        return ""


class NewsCollector:
    """新闻 + GitHub Trending 收集器"""

    def __init__(self):
        self.news_items: List[Dict] = []
        self.trending_repos: List[Dict] = []

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                email_cfg = config.get("email", {})
                for key in ("smtp_server", "smtp_port"):
                    if key in email_cfg:
                        if key == "smtp_port":
                            EMAIL_CONFIG[key] = int(email_cfg[key])
                        else:
                            EMAIL_CONFIG[key] = email_cfg[key]

    # ---------- 新闻 ----------

    def search_news(self) -> List[Dict]:
        """从天行数据 API 获取新闻，并发抓取详细描述"""
        yesterday = datetime.now() - timedelta(days=1)
        yesterday_chinese = yesterday.strftime("%Y年%m月%d日")
        news_list: List[Dict] = []

        try:
            url = f"{TIANAPI_CONFIG['base_url']}/{TIANAPI_CONFIG['api_name']}/index"
            params = {"key": TIANAPI_CONFIG["api_key"], "num": 50, "page": 1}
            print(f"调用天行数据 API: {url}")
            resp = requests.get(url, params=params, timeout=15)

            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()
            if data.get("code") == 200 and "result" in data:
                raw_items = data["result"].get("newslist", [])

                # 按关键词筛选
                for item in raw_items:
                    title = item.get("title", "")
                    desc = item.get("description", "")
                    if any(kw in title or kw in desc for kw in KEYWORDS):
                        ctime = item.get("ctime", "")
                        date_str = ctime.split()[0] if ctime else yesterday_chinese
                        news_list.append({
                            "title": title,
                            "summary": desc or "加载中...",
                            "source": item.get("source", "未知来源"),
                            "date": date_str,
                            "url": item.get("url", ""),
                        })

                # 取前 10 条
                news_list = news_list[:12]

                # 并发抓取详细描述
                if news_list:
                    print(f"筛选出 {len(news_list)} 条新闻，正在抓取详细描述...")
                    self._enrich_news_details(news_list)

            print(f"API 返回: code={data.get('code')}, msg={data.get('msg')}")

        except Exception as e:
            print(f"获取新闻出错: {e}")
            news_list = [{
                "title": f"新闻收集暂时不可用 - {yesterday_chinese}",
                "summary": str(e),
                "source": "系统提示",
                "date": yesterday_chinese,
                "url": "",
            }]

        self.news_items = news_list
        return news_list

    def _enrich_news_details(self, news_list: List[Dict]):
        """并发抓取每条新闻的详细描述"""
        def fetch_one(idx: int, item: Dict):
            url = item.get("url", "")
            if not url:
                return idx, item["summary"]
            detail = fetch_article_detail(url)
            if detail and len(detail) > len(item.get("summary", "")):
                return idx, detail
            return idx, item["summary"]

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(fetch_one, i, n): i for i, n in enumerate(news_list)}
            for future in as_completed(futures):
                try:
                    idx, summary = future.result()
                    if summary:
                        news_list[idx]["summary"] = summary
                except Exception:
                    pass

    # ---------- 36氪 ----------

    def search_36kr(self) -> List[Dict]:
        """从 36氪 RSS 获取最新科技新闻"""
        items: List[Dict] = []
        try:
            resp = requests.get(_36KR_FEED, headers=HEADERS, timeout=15)
            resp.encoding = "utf-8"
            root = ET.fromstring(resp.text)

            # RSS items are under channel/item
            channel = root.find("channel")
            if channel is None:
                print("36kr RSS: no channel found")
                return items

            count = 0
            for elem in channel.findall("item"):
                if count >= 5:
                    break
                title = (elem.findtext("title") or "").strip()
                link = (elem.findtext("link") or "").strip()
                desc = (elem.findtext("description") or "").strip()
                pub_date = (elem.findtext("pubDate") or "").strip()

                # 去掉 HTML 标签
                desc = re.sub(r"<[^>]+>", "", desc)[:250]
                if not title:
                    continue

                items.append({
                    "title": title,
                    "summary": desc or "暂无摘要",
                    "source": "36氪",
                    "date": pub_date[:16] if pub_date else "",
                    "url": link,
                })
                count += 1

            print(f"36kr RSS: {len(items)} articles")
        except Exception as e:
            print(f"36kr RSS error: {e}")

        return items

    # ---------- GitHub Trending ----------

    def search_github_trending(self) -> List[Dict]:
        """通过 GitHub Search API 获取最近一周最热门的项目"""
        since = (datetime.now() - timedelta(days=GITHUB_TRENDING_DAYS)).strftime("%Y-%m-%d")
        repos: List[Dict] = []

        try:
            url = "https://api.github.com/search/repositories"
            params = {
                "q": f"created:>={since}",
                "sort": "stars",
                "order": "desc",
                "per_page": 5,
            }
            print(f"调用 GitHub Search API: created:>={since}")
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)

            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()
            for item in data.get("items", [])[:5]:
                repos.append({
                    "name": item.get("full_name", ""),
                    "url": item.get("html_url", ""),
                    "description": item.get("description", "") or "暂无描述",
                    "stars": item.get("stargazers_count", 0),
                    "language": item.get("language", "Unknown"),
                    "topics": item.get("topics", [])[:5],
                    "forks": item.get("forks_count", 0),
                })

            # 补充每个项目的 README 摘要
            if repos:
                print(f"获取到 {len(repos)} 个热门项目，正在抓取简介...")
                self._enrich_repo_details(repos)

        except Exception as e:
            print(f"获取 GitHub Trending 出错: {e}")
            repos = []

        self.trending_repos = repos
        return repos

    def _enrich_repo_details(self, repos: List[Dict]):
        """获取每个仓库的 README 摘要"""
        def fetch_one(idx: int, repo: Dict):
            try:
                readme_url = f"https://api.github.com/repos/{repo['name']}/readme"
                resp = requests.get(readme_url, headers=HEADERS, timeout=8)
                if resp.status_code == 200:
                    import base64
                    content = base64.b64decode(resp.json().get("content", "")).decode("utf-8", errors="replace")
                    # 取 README 前 400 个非空字符作为摘要
                    clean = re.sub(r'[#*`>\[\]!()]', '', content)
                    clean = re.sub(r'\n{2,}', '\n', clean)
                    lines = [l.strip() for l in clean.split('\n') if len(l.strip()) > 20]
                    summary = " ".join(lines[:3])[:400]
                    return idx, summary
            except Exception:
                pass
            return idx, ""

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(fetch_one, i, r): i for i, r in enumerate(repos)}
            for future in as_completed(futures):
                try:
                    idx, readme_summary = future.result()
                    if readme_summary:
                        repos[idx]["readme_summary"] = readme_summary
                except Exception:
                    pass

    # ---------- 格式化 ----------

    def format_news_section(self) -> str:
        """生成新闻部分 HTML"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y年%m月%d日")
        html = f"""
    <!-- 新闻区块 -->
    <div class="section-header section-news">
      <span class="section-icon">📰</span> 信息技术与教育 · 昨日要闻
      <span class="section-date">{yesterday}</span>
    </div>
    <div class="news-list">
"""
        if not self.news_items:
            html += '<div class="empty-hint">今日暂无相关新闻</div>'
        else:
            for i, news in enumerate(self.news_items, 1):
                url_link = (
                    f'<a href="{news["url"]}" target="_blank">{news["title"]}</a>'
                    if news["url"] else news["title"]
                )
                html += f"""
      <div class="news-item">
        <div class="news-index">
          <span class="index-dot">{i}</span>
          <span class="news-source">{news['source']}</span>
        </div>
        <div class="news-title">{url_link}</div>
        <div class="news-summary">{news['summary']}</div>
      </div>"""
        html += "\n    </div>"
        return html

    def format_trending_section(self) -> str:
        """生成 GitHub Trending 部分 HTML"""
        html = f"""
    <!-- Trending 区块 -->
    <div class="section-header section-trending">
      <span class="section-icon">⭐</span> GitHub 本周热门项目 Top 5
      <span class="section-date">{GITHUB_TRENDING_DAYS} 日内新星</span>
    </div>
    <div class="trending-list">
"""
        if not self.trending_repos:
            html += '<div class="empty-hint">暂时无法获取 GitHub 热门项目</div>'
        else:
            for i, repo in enumerate(self.trending_repos, 1):
                topics_html = " ".join(
                    f'<span class="topic-tag">{t}</span>' for t in repo.get("topics", [])
                )
                readme_extra = ""
                if repo.get("readme_summary"):
                    readme_extra = (
                        f'<div class="repo-readme">📖 {repo["readme_summary"]}</div>'
                    )
                html += f"""
      <div class="repo-item">
        <div class="repo-rank">#{i}</div>
        <div class="repo-info">
          <div class="repo-name">
            <a href="{repo['url']}" target="_blank">{repo['name']}</a>
          </div>
          <div class="repo-desc">{repo['description']}</div>
          {readme_extra}
          <div class="repo-meta">
            <span class="repo-stars">⭐ {repo['stars']:,}</span>
            <span class="repo-forks">🔀 {repo['forks']:,}</span>
            <span class="repo-lang">📄 {repo['language']}</span>
            {topics_html}
          </div>
        </div>
      </div>"""
        html += "\n    </div>"
        return html

    def format_email_html(self) -> str:
        """生成完整 HTML 邮件"""
        today = datetime.now().strftime("%Y年%m月%d日")
        now_time = datetime.now().strftime("%H:%M")

        news_html = self.format_news_section()
        trending_html = self.format_trending_section()
        total_news = len(self.news_items)
        total_repos = len(self.trending_repos)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{ margin: 0; padding: 0; background: #f0f2f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; }}
  .container {{ max-width: 640px; margin: 0 auto; background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.06); }}
  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 40%, #0f3460 100%); color: #fff; padding: 32px 28px; text-align: center; }}
  .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; letter-spacing: 1px; }}
  .header .sub {{ margin-top: 6px; font-size: 12px; opacity: 0.7; }}
  .stats {{ display: flex; justify-content: center; gap: 24px; padding: 14px; background: #fafbfc; border-bottom: 1px solid #eee; }}
  .stats .stat {{ text-align: center; }}
  .stats .stat-num {{ font-size: 22px; font-weight: 700; color: #333; }}
  .stats .stat-label {{ font-size: 11px; color: #999; margin-top: 2px; }}
  .section-header {{ padding: 14px 24px; font-size: 15px; font-weight: 700; border-bottom: 2px solid #f0f0f0; display: flex; align-items: center; gap: 8px; }}
  .section-news {{ background: #fefefe; color: #333; }}
  .section-trending {{ background: #fffdf5; color: #333; border-top: 4px solid #f0e68c; }}
  .section-icon {{ font-size: 18px; }}
  .section-date {{ margin-left: auto; font-size: 11px; color: #aaa; font-weight: 400; }}
  .news-list {{ padding: 8px 20px; }}
  .news-item {{ padding: 14px 0; border-bottom: 1px solid #f5f5f5; }}
  .news-item:last-child {{ border-bottom: none; }}
  .news-index {{ display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }}
  .index-dot {{ display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; background: #1a1a2e; color: #fff; border-radius: 50%; font-size: 11px; font-weight: 600; flex-shrink: 0; }}
  .news-source {{ font-size: 11px; color: #aaa; }}
  .news-title {{ font-size: 15px; font-weight: 600; line-height: 1.5; margin-bottom: 5px; }}
  .news-title a {{ color: #1a1a2e; text-decoration: none; }}
  .news-title a:hover {{ color: #0f3460; text-decoration: underline; }}
  .news-summary {{ font-size: 13px; color: #555; line-height: 1.7; }}
  .trending-list {{ padding: 8px 20px; }}
  .repo-item {{ display: flex; gap: 14px; padding: 16px 0; border-bottom: 1px solid #f5f5f5; }}
  .repo-item:last-child {{ border-bottom: none; }}
  .repo-rank {{ font-size: 20px; font-weight: 800; color: #e2c044; min-width: 32px; line-height: 1.4; }}
  .repo-info {{ flex: 1; }}
  .repo-name {{ font-size: 15px; font-weight: 600; margin-bottom: 3px; }}
  .repo-name a {{ color: #0f3460; text-decoration: none; }}
  .repo-name a:hover {{ text-decoration: underline; }}
  .repo-desc {{ font-size: 13px; color: #555; line-height: 1.6; margin-bottom: 6px; }}
  .repo-readme {{ font-size: 12px; color: #777; line-height: 1.6; background: #f9fafb; padding: 8px 12px; border-radius: 6px; margin-bottom: 6px; border-left: 3px solid #e2c044; }}
  .repo-meta {{ font-size: 12px; color: #888; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }}
  .repo-stars {{ color: #e2a020; font-weight: 600; }}
  .repo-forks {{ color: #666; }}
  .repo-lang {{ color: #666; }}
  .topic-tag {{ display: inline-block; background: #eef2ff; color: #4a5fc1; padding: 1px 7px; border-radius: 10px; font-size: 11px; }}
  .empty-hint {{ text-align: center; padding: 30px; color: #bbb; font-size: 13px; }}
  .footer {{ background: #fafbfc; padding: 18px 24px; text-align: center; font-size: 11px; color: #bbb; border-top: 1px solid #eee; }}
  .footer a {{ color: #888; text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📬 科技早报</h1>
    <div class="sub">{today} {now_time} · 由 GitHub Actions 自动生成</div>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-num">{total_news}</div><div class="stat-label">📰 科技新闻</div></div>
    <div class="stat"><div class="stat-num">{total_repos}</div><div class="stat-label">⭐ 热门项目</div></div>
  </div>
  {news_html}
  {trending_html}
  <div class="footer">
    本邮件由自动化脚本通过 <a href="https://github.com/features/actions">GitHub Actions</a> 定时生成<br>
    内容仅供参考 · 数据来源：天行数据 & GitHub Search API
  </div>
</div>
</body>
</html>"""

    # ---------- 邮件 ----------

    def send_email(self, subject: str, html_content: str) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = formataddr((EMAIL_CONFIG["sender_name"], EMAIL_CONFIG["sender_email"]))
            msg["To"] = EMAIL_CONFIG["receiver_email"]
            msg["Subject"] = subject

            plain = f"科技早报 — 共 {len(self.news_items)} 条新闻 + {len(self.trending_repos)} 个热门项目。请使用支持 HTML 的客户端查看。"
            msg.attach(MIMEText(plain, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            with smtplib.SMTP_SSL(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as server:
                server.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
                server.sendmail(
                    EMAIL_CONFIG["sender_email"],
                    [EMAIL_CONFIG["receiver_email"]],
                    msg.as_string(),
                )

            print(f"✅ 邮件已发送到 {EMAIL_CONFIG['receiver_email']}")
            return True
        except Exception as e:
            print(f"❌ 邮件发送失败: {e}")
            return False

    # ---------- 日志 ----------

    def save_log(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        log_file = os.path.join(LOG_DIR, f"news_{datetime.now().strftime('%Y%m%d')}.txt")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y年%m月%d日")

        plain = f"科技早报 - {yesterday}\n{'=' * 50}\n\n"
        plain += "【📰 科技新闻】\n\n"
        for i, n in enumerate(self.news_items, 1):
            plain += f"[{i}] {n['title']}\n    来源: {n['source']}\n    {n['summary']}\n\n"

        plain += "【⭐ GitHub 热门项目】\n\n"
        for i, r in enumerate(self.trending_repos, 1):
            plain += f"#{i} {r['name']}  ⭐{r['stars']:,}\n    {r['description']}\n    {r['url']}\n\n"

        with open(log_file, "w", encoding="utf-8") as f:
            f.write(plain)
        print(f"📝 日志已保存: {log_file}")

    # ---------- 主流程 ----------

    def run(self):
        print("🚀 开始收集...")

        if not TIANAPI_CONFIG["api_key"]:
            print("❌ 未设置 TianAPI_KEY")
            return
        if not EMAIL_CONFIG["sender_password"]:
            print("❌ 未设置 SENDER_PASSWORD")
            return

        self.load_config()

        # 1. 36氪 RSS
        print("📰 Step 1/3: 抓取 36氪 科技新闻...")
        kr36_news = self.search_36kr()

        # 2. 天行数据新闻
        print("📰 Step 2/3: 从天行数据获取新闻...")
        self.search_news()

        # 将 36氪 新闻插入最前面
        for item in reversed(kr36_news):
            self.news_items.insert(0, item)
        # 总共保留 12 条
        self.news_items = self.news_items[:12]

        # 3. GitHub Trending
        print("⭐ Step 3/3: 抓取 GitHub 热门项目...")
        self.search_github_trending()

        # 3. 生成邮件
        html = self.format_email_html()

        # 4. 保存日志
        self.save_log()

        # 5. 发送
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y年%m月%d日")
        subject = f"📬 科技早报 - {yesterday}"
        ok = self.send_email(subject, html)

        if ok:
            print(f"✨ 完成！新闻 {len(self.news_items)} 条 + 项目 {len(self.trending_repos)} 个")
        else:
            print("⚠️ 邮件发送失败")
            exit(1)


def main():
    NewsCollector().run()


if __name__ == "__main__":
    main()
