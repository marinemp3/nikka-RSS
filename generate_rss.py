#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
中国の求人情報RSSフィード生成スクリプト
対象: https://chinajob.mohrss.gov.cn/c/2021-06-04/308283.shtml
エントリ数: HTMLの上部から100件を抽出（日付順ではない）
"""

import os
import sys
import time
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ========== 設定 ==========
TARGET_URL = "https://chinajob.mohrss.gov.cn/c/2021-06-04/308283.shtml"
RSS_FILENAME = "rss.xml"
FEED_TITLE = "中国 求人情報 RSS"
FEED_LINK = "https://github.com/YOUR_USERNAME/china-job-rss"  # ← あなたのGitHubユーザー名に変更
FEED_DESCRIPTION = "中国の政府系求人サイトの最新求人情報（上部100件）"
FEED_LANGUAGE = "ja"

# 中国標準時（CST = UTC+8）
CHINA_TZ = timezone(timedelta(hours=8))

# 最大エントリ数（HTMLの上部から100件）
MAX_ENTRIES = 100


def setup_driver() -> webdriver.Chrome:
    """SeleniumのChromeドライバを設定（ヘッドレスモード）"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=ja")
    chrome_options.add_argument("--remote-debugging-port=9222")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
    except Exception:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver


def get_page_content(url: str) -> str:
    """Seleniumでページを取得し、HTMLを返す"""
    driver = setup_driver()
    try:
        print(f"[ステッカー] ページ読み込み中: {url}")
        driver.get(url)
        
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # 追加の待機（動的コンテンツ読み込み用）
        time.sleep(3)
        
        html = driver.page_source
        print("[ステッカー] ページ取得成功")
        return html
        
    except TimeoutException:
        print("[ステッカー] ページ読み込みタイムアウト")
        raise
    except Exception as e:
        print(f"[ステッカー] エラー発生: {e}")
        raise
    finally:
        driver.quit()


def extract_date(text: str) -> str:
    """テキストから日付っぽい文字列を抽出"""
    if not text:
        return ""
    
    # 様々な日付形式に対応
    patterns = [
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{4}/\d{2}/\d{2})',
        r'(\d{4}\.\d{2}\.\d{2})',
        r'(\d{4})年(\d{1,2})月(\d{1,2})日',
        r'(\d{4})年(\d{1,2})月',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            if len(match.groups()) == 1:
                return match.group(1)
            elif len(match.groups()) == 3:
                year, month, day = match.groups()
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            elif len(match.groups()) == 2:
                year, month = match.groups()
                return f"{year}-{month.zfill(2)}"
    
    return ""


def parse_jobs(html: str) -> List[Dict[str, str]]:
    """
    HTMLから求人情報をパースする
    戻り値: HTMLの表示順序（上部から）でリストを返す
    """
    soup = BeautifulSoup(html, 'html.parser')
    jobs = []
    
    print("[ステッカー] 求人情報を抽出中...")
    
    # 方法1: テーブル構造から抽出（中国政府サイトの一般的な形式）
    tables = soup.find_all('table')
    print(f"  - テーブル数: {len(tables)}")
    
    for table_idx, table in enumerate(tables):
        rows = table.find_all('tr')
        for row in rows:
            # 行内のリンクを探す
            links = row.find_all('a', href=True)
            if not links:
                continue
            
            # 行内のテキストを取得（日付情報用）
            row_text = row.get_text(strip=True)
            
            for link in links:
                title = link.get_text(strip=True)
                href = link.get('href')
                
                # タイトルが空または短すぎる場合はスキップ
                if not title or len(title) < 3:
                    continue
                
                # URLを絶対パスに変換
                if href.startswith('/'):
                    href = f"https://chinajob.mohrss.gov.cn{href}"
                elif not href.startswith('http'):
                    href = f"https://chinajob.mohrss.gov.cn/{href}"
                
                # 日付情報を抽出
                pub_date = extract_date(row_text)
                
                # 重複を防ぐ（同じURLはスキップ）
                if any(job['link'] == href for job in jobs):
                    continue
                
                jobs.append({
                    'title': title,
                    'link': href,
                    'description': title,
                    'pub_date': pub_date
                })
                
                # 100件に達したら早期終了
                if len(jobs) >= MAX_ENTRIES:
                    print(f"  [ステッカー] {MAX_ENTRIES}件に達したため、抽出を終了します")
                    return jobs
    
    # 方法2: テーブル以外の構造から抽出（方法1で見つからなかった場合）
    if not jobs:
        print("  - テーブルから見つかりませんでした。別の方法を試します...")
        
        # すべてのリンクを取得
        all_links = soup.find_all('a', href=True)
        print(f"  - 全リンク数: {len(all_links)}")
        
        for link in all_links:
            title = link.get_text(strip=True)
            href = link.get('href')
            
            if not title or len(title) < 5:
                continue
            
            # 親要素から日付を抽出
            parent_text = ""
            parent = link.parent
            if parent:
                parent_text = parent.get_text(strip=True)
            
            # URLを絶対パスに変換
            if href.startswith('/'):
                href = f"https://chinajob.mohrss.gov.cn{href}"
            elif not href.startswith('http'):
                href = f"https://chinajob.mohrss.gov.cn/{href}"
            
            # 日付を抽出
            pub_date = extract_date(parent_text or title)
            
            # 重複をチェック
            if any(job['link'] == href for job in jobs):
                continue
            
            jobs.append({
                'title': title,
                'link': href,
                'description': title,
                'pub_date': pub_date
            })
            
            if len(jobs) >= MAX_ENTRIES:
                print(f"  [ステッカー] {MAX_ENTRIES}件に達したため、抽出を終了します")
                break
    
    # [ステッカー] ソートは行わず、抽出した順序（HTMLの表示順）をそのまま保持
    print(f"[ステッカー] HTMLの上部から {len(jobs)}件の求人情報を抽出しました（最大{MAX_ENTRIES}件）")
    return jobs


def generate_rss(jobs: List[Dict[str, str]], output_file: str = RSS_FILENAME) -> None:
    """RSSフィードを生成"""
    fg = FeedGenerator()
    fg.title(FEED_TITLE)
    fg.link(href=FEED_LINK, rel='alternate')
    fg.description(f"{FEED_DESCRIPTION}（{len(jobs)}件）")
    fg.language(FEED_LANGUAGE)
    fg.lastBuildDate(datetime.now(CHINA_TZ))
    
    # 各求人情報をRSSアイテムとして追加（抽出順序を維持）
    for job in jobs:
        # 日付をパース（なければ現在時刻を使用）
        pub_date = datetime.now(CHINA_TZ)
        if job.get('pub_date'):
            date_str = job['pub_date'].strip()
            if date_str:
                try:
                    # 様々な日付形式に対応
                    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d']:
                        try:
                            pub_date = datetime.strptime(date_str, fmt)
                            pub_date = pub_date.replace(tzinfo=CHINA_TZ)
                            break
                        except ValueError:
                            continue
                except:
                    pass
        
        guid = job['link']
        
        fe = fg.add_entry()
        fe.title(job['title'])
        fe.link(href=job['link'], rel='alternate')
        fe.description(job['description'])
        fe.guid(guid, permalink=True)
        fe.pubDate(pub_date)
    
    fg.rss_file(output_file, pretty=True)
    print(f"[ステッカー] RSSフィードを生成しました: {output_file}")
    print(f"[ステッカー] アイテム数: {len(jobs)}（HTML上部から抽出）")


def debug_html_structure(html: str) -> None:
    """デバッグ用：HTML構造を分析して表示"""
    soup = BeautifulSoup(html, 'html.parser')
    print("\n" + "=" * 50)
    print("[ステッカー] HTML構造デバッグ情報")
    print("=" * 50)
    
    # テーブル情報
    tables = soup.find_all('table')
    print(f"テーブル数: {len(tables)}")
    for i, table in enumerate(tables[:3]):  # 最初の3つだけ表示
        rows = table.find_all('tr')
        print(f"  テーブル{i+1}: {len(rows)}行")
        if rows:
            first_row = rows[0].get_text(strip=True)[:100]
            print(f"    最初の行: {first_row}...")
    
    # リンク情報
    links = soup.find_all('a', href=True)
    print(f"\nリンク数: {len(links)}")
    for i, link in enumerate(links[:10]):  # 最初の10個だけ表示
        title = link.get_text(strip=True)
        href = link.get('href')
        if title and len(title) > 3:
            print(f"  {i+1}. {title[:50]}... -> {href}")
    
    # IDやクラス情報
    important_elements = ['word', 'content', 'main', 'list', 'job']
    for elem_id in important_elements:
        element = soup.find(id=elem_id)
        if element:
            print(f"\nID='{elem_id}' が見つかりました")
    
    print("=" * 50 + "\n")


def main():
    """メイン関数"""
    print("=" * 50)
    print("[ステッカー] 中国求人情報 RSS ジェネレーター")
    print(f"[ステッカー] 実行時刻: {datetime.now(CHINA_TZ).strftime('%Y-%m-%d %H:%M:%S')} (中国時間)")
    print(f"[ステッカー] 抽出方法: HTMLの上部から {MAX_ENTRIES}件")
    print("=" * 50)
    
    try:
        # ページを取得
        html = get_page_content(TARGET_URL)
        
        # デバッグ情報（初回実行時に有効にすることを推奨）
        # debug_html_structure(html)
        
        # 求人情報を抽出（HTMLの表示順で）
        jobs = parse_jobs(html)
        
        if not jobs:
            print("[ステッカー] 求人情報が見つかりませんでした。")
            print("[ステッカー] ヒント: debug_html_structure(html) のコメントを外して構造を確認してください")
            sys.exit(1)
        
        # RSSを生成
        generate_rss(jobs)
        
        print("=" * 50)
        print("[ステッカー] 完了しました！")
        print(f"[ステッカー] RSSファイル: {RSS_FILENAME}")
        
    except Exception as e:
        print(f"[ステッカー] エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
