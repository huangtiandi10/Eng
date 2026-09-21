# CET6 500

本项目是一个本地运行的 CET6 学习工具，包含词汇、写作和听力训练。

## 启动

需要 Python 3.11+，无第三方依赖：

```bash
python3 server.py
```

然后打开 <http://127.0.0.1:8765>。

## Mac 服务端与 Windows 客户端

Mac 应作为唯一数据源运行服务。首次启动会在 `config.yaml` 的 `server.access_token` 中生成访问令牌；令牌只需要输入一次，浏览器会保存在本机。

要允许 Windows 访问，在 Mac 的 `config.yaml` 中设置：

```yaml
server:
  host: 0.0.0.0
  port: 8765
  access_token: "替换为你的长随机令牌"
```

然后在 Windows 浏览器打开 Mac 的地址，例如 `http://192.168.1.20:8765`。跨网络使用时建议通过 Tailscale 连接，并使用 Mac 的 Tailscale 地址；不要把 8765 端口直接暴露到公网。

`data/study.db` 和 `config.yaml` 是服务端私有文件，不要复制到 Windows，也不要提交到 Git。请为 `data/` 配置 Time Machine 或其他定期备份。

第一次使用前可以复制配置模板：

```bash
cp config.example.yaml config.yaml
```

没有配置 AI Key 时，写作模块仍会提供本地基础检查，但不会调用远程模型。

## 数据和词库

学习记录保存在 `data/study.db`，不会上传。`data/words.json` 是当前内置的 CET6 核心词汇种子，字段设计兼容后续导入完整公开词表。词库来源与许可证在 `data/SOURCE.md` 中记录。

下载并导入 2345 条公开 CET6 词汇：

```bash
python3 scripts/download_vocabulary.py
```
