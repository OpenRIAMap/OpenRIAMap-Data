# Data_Merge_Tool v2（World 映射 / 冲突报告 / 进度提示版）

本版本基于 `Data_Merge_Tool_v2_realwrite_zh_autobind` 继续增强。

## 主要新增

- 公共策略配置文件 `config/policy_config.json`
- 本地 Web 规则目录 `web_schema/`
- 写库目录通过 `world_map.json` 解析，不再直接把 `World` 数值当目录名
- JSON 重复 ID 冲突详情增强
- 统一终端分隔线与进度提示
- `sync-web-schema` 命令
- 新增文件均带中文注释，便于后续手动修改

## 运行方式

双击：
- `launch_tool.bat`

或命令行执行：
```bat
python bin\tool.py
```


## 本次增量修复

- 提交 Split / Picture / Merge 后，会同步更新对应 world 层级的 `INDEX.json`
- world 层级 `INDEX.json` 格式为：

```json
{
  "version": 1,
  "updatedAt": "2026-03-26T22:12:18+08:00"
}
```
