import requests
import re
import time
import random
from datetime import datetime
import os
from bs4 import BeautifulSoup
import json

class EnhancedNodeCrawler:
    def __init__(self):
        self.base_url = "https://www.mibei77.com"
        self.session = requests.Session()
        # 设置更真实的浏览器请求头
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
        ]
        self.update_headers()
        
        # 重试配置
        self.max_retries = 3
        self.retry_delay = 5
    
    def update_headers(self):
        """更新请求头"""
        self.session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        })
    
    def make_request_with_retry(self, url, method='GET', **kwargs):
        """带重试的请求函数"""
        for attempt in range(self.max_retries):
            try:
                # 每次重试前更新User-Agent
                self.update_headers()
                
                # 添加随机延迟避免被识别为爬虫
                time.sleep(random.uniform(1, 3))
                
                response = self.session.request(method, url, timeout=15, **kwargs)
                
                # 检查是否被反爬虫
                if response.status_code == 403:
                    print(f"第{attempt + 1}次请求被拒绝(403)，可能是反爬虫机制")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                        continue
                
                response.raise_for_status()
                return response
                
            except requests.RequestException as e:
                print(f"第{attempt + 1}次请求失败: {e}")
                if attempt < self.max_retries - 1:
                    print(f"等待{self.retry_delay}秒后重试...")
                    time.sleep(self.retry_delay)
                else:
                    print("所有重试均失败")
                    raise
        
        return None
    
    def get_latest_article_url(self):
        """获取最新文章的URL"""
        try:
            print("正在访问网站首页...")
            response = self.make_request_with_retry(self.base_url)
            if not response:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 多种策略查找最新文章链接
            article_candidates = []
            
            # 策略1: 查找包含日期的链接
            date_pattern = r'/\d{4}/\d{2}/\d{8}.*\.html'
            for link in soup.find_all('a', href=True):
                href = link['href']
                if re.search(date_pattern, href):
                    if href.startswith('/'):
                        full_url = self.base_url + href
                        article_candidates.append(full_url)
                    elif href.startswith(self.base_url):
                        article_candidates.append(href)
            
            # 策略2: 查找文章列表区域
            common_selectors = [
                '.post-title a',
                '.entry-title a', 
                '.title a',
                'h2 a',
                'h3 a',
                'article h2 a',
                'article h3 a'
            ]
            
            for selector in common_selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href')
                    if href and (href.startswith('/') or href.startswith(self.base_url)):
                        if href.startswith('/'):
                            href = self.base_url + href
                        article_candidates.append(href)
            
            # 策略3: 查找最近的博客文章
            blog_patterns = [
                r'.*/\d{4}/\d{2}/.*\.html',
                r'.*/article/.*',
                r'.*/post/.*'
            ]
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                for pattern in blog_patterns:
                    if re.match(pattern, href):
                        if href.startswith('/'):
                            href = self.base_url + href
                        article_candidates.append(href)
            
            # 去重并排序
            unique_articles = list(set(article_candidates))
            if unique_articles:
                # 按URL中的日期排序（假设URL包含日期）
                def extract_date(url):
                    match = re.search(r'/(\d{4})/(\d{2})/(\d{8})', url)
                    if match:
                        return match.group(1) + match.group(2) + match.group(3)
                    return "00000000"
                
                unique_articles.sort(key=extract_date, reverse=True)
                latest_url = unique_articles[0]
                print(f"找到最新文章链接: {latest_url}")
                return latest_url
            
            print("未找到符合条件的文章链接")
            return None
            
        except Exception as e:
            print(f"获取最新文章链接时出错: {e}")
            return None
    
    def extract_subscription_link(self, article_url):
        """从文章中提取订阅链接"""
        try:
            print(f"正在访问文章: {article_url}")
            response = self.make_request_with_retry(article_url)
            if not response:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 获取文章内容文本
            content_text = soup.get_text()
            
            # 多种模式匹配订阅链接
            subscription_patterns = [
                r'https://mm\.mibei77\.com/\d{6}/[^"\'\s]+\.txt',
                r'v2ray订阅链接[^"]*?(https?://[^\s]+)',
                r'订阅链接[^"]*?(https?://[^\s]+)',
                r'免费节点订阅链接[^"]*?(https?://[^\s]+)',
                r'https://[^"\'\s]*?mibei77[^"\'\s]*?\.txt',
                r'https://[^"\'\s]*?\.txt'
            ]
            
            for pattern in subscription_patterns:
                matches = re.findall(pattern, content_text, re.IGNORECASE)
                for match in matches:
                    # 清理匹配结果
                    match = match.strip('.,;:!?')
                    if 'mibei77.com' in match and match.endswith('.txt'):
                        print(f"找到订阅链接: {match}")
                        return match
            
            # 在链接标签中查找
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'mibei77.com' in href and href.endswith('.txt'):
                    print(f"在链接标签中找到订阅链接: {href}")
                    return href
            
            # 在代码块中查找
            for code in soup.find_all('code'):
                code_text = code.get_text()
                if 'mibei77.com' in code_text and '.txt' in code_text:
                    matches = re.findall(r'https://[^\s]+\.txt', code_text)
                    for match in matches:
                        if 'mibei77.com' in match:
                            print(f"在代码块中找到订阅链接: {match}")
                            return match
            
            print("未找到订阅链接")
            return None
            
        except Exception as e:
            print(f"提取订阅链接时出错: {e}")
            return None
    
    def download_subscription_content(self, subscription_url):
        """下载订阅链接的内容"""
        try:
            print(f"正在下载订阅内容: {subscription_url}")
            response = self.make_request_with_retry(subscription_url)
            if not response:
                return None
            
            content = response.text
            print(f"成功下载订阅内容，长度: {len(content)} 字符")
            
            # 验证内容是否为有效的订阅格式
            if len(content.strip()) == 0:
                print("订阅内容为空")
                return None
            
            # 检查是否为base64编码的vmess链接或其他订阅格式
            if content.startswith('vmess://') or content.startswith('ss://') or content.startswith('trojan://'):
                print("检测到有效的节点订阅格式")
            elif 'vmess' in content.lower() or 'ss://' in content or 'trojan://' in content:
                print("检测到包含节点信息的订阅内容")
            else:
                print("警告：订阅内容可能不是标准的节点订阅格式")
            
            return content
            
        except Exception as e:
            print(f"下载订阅内容时出错: {e}")
            return None
    
    def save_status(self, success, article_url=None, subscription_url=None):
        """保存执行状态"""
        status = {
            'last_run': datetime.now().isoformat(),
            'success': success,
            'article_url': article_url,
            'subscription_url': subscription_url
        }
        with open('crawler_status.json', 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    
    def run(self):
        """执行完整的爬取流程"""
        print("开始执行增强版节点爬取任务...")
        print(f"当前时间: {datetime.now()}")
        
        try:
            # 获取最新文章链接
            article_url = self.get_latest_article_url()
            if not article_url:
                print("无法获取最新文章链接")
                self.save_status(False)
                return False
            
            # 提取订阅链接
            subscription_url = self.extract_subscription_link(article_url)
            if not subscription_url:
                print("无法提取订阅链接")
                self.save_status(False, article_url)
                return False
            
            # 下载订阅内容
            content = self.download_subscription_content(subscription_url)
            if not content:
                print("无法下载订阅内容")
                self.save_status(False, article_url, subscription_url)
                return False
            
            # 保存内容到文件
            with open('subscription.txt', 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 保存成功状态
            self.save_status(True, article_url, subscription_url)
            
            print("任务执行成功！")
            return True
            
        except Exception as e:
            print(f"任务执行过程中出现异常: {e}")
            self.save_status(False)
            return False

if __name__ == "__main__":
    crawler = EnhancedNodeCrawler()
    success = crawler.run()
    exit(0 if success else 1)
