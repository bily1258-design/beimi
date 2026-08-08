import requests
import re
import time
from datetime import datetime
import os
from bs4 import BeautifulSoup

class NodeCrawler:
    def __init__(self):
        self.base_url = "https://www.mibei77.com"
        self.session = requests.Session()
        # 设置请求头模拟浏览器访问
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def get_latest_article_url(self):
        """获取最新文章的URL"""
        try:
            print("正在访问网站首页...")
            response = self.session.get(self.base_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 查找最新文章的链接
            # 根据网站结构，最新文章通常在首页的显眼位置
            article_links = []
            
            # 方法1: 查找包含日期的链接
            date_pattern = r'/\d{4}/\d{2}/'
            for link in soup.find_all('a', href=True):
                href = link['href']
                if re.search(date_pattern, href) and href.startswith('/'):
                    full_url = self.base_url + href
                    article_links.append(full_url)
            
            # 方法2: 查找文章标题链接
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.startswith(self.base_url) and re.search(r'\d{4}/\d{2}/', href):
                    article_links.append(href)
            
            # 去重并返回最新的链接
            unique_links = list(set(article_links))
            if unique_links:
                # 假设链接中包含日期，按日期排序取最新的
                unique_links.sort(reverse=True)
                latest_url = unique_links[0]
                print(f"找到最新文章链接: {latest_url}")
                return latest_url
            
            # 如果上述方法没找到，尝试直接构造今天的文章链接
            today = datetime.now().strftime("%Y/%m")
            today_url = f"{self.base_url}/{today}/"
            print(f"尝试访问今日文章目录: {today_url}")
            
            response = self.session.get(today_url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if href.startswith(f'/{today}/') and href.endswith('.html'):
                        return self.base_url + href
            
            return None
            
        except requests.RequestException as e:
            print(f"获取最新文章链接时出错: {e}")
            return None
    
    def extract_subscription_link(self, article_url):
        """从文章中提取订阅链接"""
        try:
            print(f"正在访问文章: {article_url}")
            response = self.session.get(article_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 查找包含订阅链接的文本
            content_text = soup.get_text()
            
            # 查找订阅链接模式
            subscription_patterns = [
                r'https://mm\.mibei77\.com/\d{6}/[^"\'\s]+\.txt',
                r'v2ray订阅链接[^"]*?(https?://[^\s]+)',
                r'订阅链接[^"]*?(https?://[^\s]+)',
                r'https://[^"\'\s]*?\.txt'
            ]
            
            for pattern in subscription_patterns:
                matches = re.findall(pattern, content_text)
                for match in matches:
                    if 'mibei77.com' in match and match.endswith('.txt'):
                        print(f"找到订阅链接: {match}")
                        return match
            
            # 如果没有找到，尝试在链接标签中查找
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'mibei77.com' in href and href.endswith('.txt'):
                    print(f"在链接中找到订阅链接: {href}")
                    return href
            
            return None
            
        except requests.RequestException as e:
            print(f"提取订阅链接时出错: {e}")
            return None
    
    def download_subscription_content(self, subscription_url):
        """下载订阅链接的内容"""
        try:
            print(f"正在下载订阅内容: {subscription_url}")
            response = self.session.get(subscription_url, timeout=10)
            response.raise_for_status()
            
            content = response.text
            print(f"成功下载订阅内容，长度: {len(content)} 字符")
            return content
            
        except requests.RequestException as e:
            print(f"下载订阅内容时出错: {e}")
            return None
    
    def run(self):
        """执行完整的爬取流程"""
        print("开始执行节点爬取任务...")
        print(f"当前时间: {datetime.now()}")
        
        # 获取最新文章链接
        article_url = self.get_latest_article_url()
        if not article_url:
            print("无法获取最新文章链接")
            return False
        
        # 提取订阅链接
        subscription_url = self.extract_subscription_link(article_url)
        if not subscription_url:
            print("无法提取订阅链接")
            return False
        
        # 下载订阅内容
        content = self.download_subscription_content(subscription_url)
        if not content:
            print("无法下载订阅内容")
            return False
        
        # 保存内容到文件
        with open('subscription.txt', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("任务执行成功！")
        return True

if __name__ == "__main__":
    crawler = NodeCrawler()
    success = crawler.run()
    exit(0 if success else 1)
