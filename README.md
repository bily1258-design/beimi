# 节点订阅自动更新器 (beimi)

多源免费节点聚合: 每天自动抓取米贝 + 多个公开订阅源, 合并去重后生成 Clash 订阅和通用 Base64 订阅, 通过 jsDelivr CDN 提供固定地址。

## 📡 订阅地址 (jsDelivr CDN, 国内可访问)

**Clash / Mihomo (推荐)**:
```
https://cdn.jsdelivr.net/gh/bily1258-design/beimi@main/output/clash.yaml
https://cdn.jsdelivr.net/gh/bily1258-design/beimi@main/output/subscribe.txt
```
> 两个都是 Clash/Mihomo 可直接导入的 YAML 配置 (subscribe.txt 与 clash.yaml 内容一致)。mihomo 内核只认 YAML, 不认 base64 订阅, 请勿把 base64 地址喂给 Clash 客户端。

**V2Ray / 通用 Base64 (v2rayNG 等)**:
```
https://cdn.jsdelivr.net/gh/bily1258-design/beimi@main/output/subscribe_b64.txt
```
**明文 URI (调试用)**:
```
https://cdn.jsdelivr.net/gh/bily1258-design/beimi@main/output/subscribe_plain.txt
```

> Clash Verge Rev / Mihomo / ClashX / 小火箭(经 Sub-Store) 里粘贴上面地址即可, 每天自动更新。
> 老版 Clash 内核不认 vless/trojan 新字段, 请用 Meta 内核客户端。

## 🔧 工作流程

1. **米贝爬虫** (`enhanced_crawler.py`): 爬 mibei77.com 最新文章 → 提取订阅链接 → 下载节点
2. **多源合并** (`merge_subscriptions.py`): 米贝 + 远程源 (v2raynode / FreeNodes / tonygyf 等) → 解析 (vless/vmess/trojan/ss/hysteria2) → 按 server+port 去重 → 输出 `output/clash.yaml` + `output/subscribe.txt`
3. **GitHub Actions**: 每天 8:00 / 20:00 (北京时间) 自动执行并提交

## ⚙️ 改订阅源

编辑 `merge_subscriptions.py` 顶部 `SOURCES` 数组, 添加/删除源即可:

```python
SOURCES = [
    "https://raw.githubusercontent.com/xxx/xxx/main/result/nodetotal.txt",  # 纯 URI 文本源
    "https://raw.githubusercontent.com/xxx/xxx/main/clash.yaml",            # Clash yaml 源
]
```

优先使用别人的 raw 订阅文件 (txt / yaml), 比爬 HTML 页面稳定得多。某个源挂了不影响其他源。

## 🚀 手动触发

仓库 → Actions → Update Subscription → Run workflow

## ⚠️ 注意事项

- GitHub Actions 在美国跑, 测速不代表国内实际速度, 节点能连上出网即可
- 免费节点会失效, 建议配合客户端自动更新 (每天至少一次)
