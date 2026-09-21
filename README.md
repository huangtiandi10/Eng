# CET6 500

本项目是一个本地运行的 CET6 学习工具，包含词汇、写作和听力训练。

## 启动

需要 Python 3.11+，无第三方依赖：

```bash
python3 server.py
```

然后打开 <http://127.0.0.1:8765>。

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

