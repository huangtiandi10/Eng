# Vocabulary source

当前仓库内的 `words.json` 是用于首版离线运行的 CET6 核心词汇种子数据，按公开 CET6 高频词汇整理，不包含商业单词书的排版或受限内容。

完整词表使用 Qwerty Learner 项目的 `CET6_T.json`：

- Source: https://github.com/RealKai42/qwerty-learner/blob/master/public/dicts/CET6_T.json
- License: GPL-3.0（以原仓库声明为准）
- Records at verification: 2345
- Verified: 2026-09-21

第三方原始数据不提交到本仓库。运行下面的命令会下载到被 Git 忽略的 `data/cet6_source.json` 并导入本地 SQLite：

```bash
python3 scripts/download_vocabulary.py
```

导入采用 upsert，不会清除已有学习记录；内置种子词中更完整的例句和词组也会保留。
