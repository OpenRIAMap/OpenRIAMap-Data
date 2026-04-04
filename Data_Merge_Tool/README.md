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


## 本次增量修复

- `load-package` 现在会跳过包内各级 `INDEX.json`，避免把索引文件误判成图片路径错误。
- 标准包中的图片会按 `world + class + kind + id` 聚合成图片组，并以“整体覆盖”语义 staged。
- `commit` 时，若包中明确包含某个 ID 的图片组，则会先删除旧图片目录，再按新包顺序整体重建。
- `report` 在存在阻断问题时，会优先显示 `precheck_report.md`，避免被 `preview_report.md` 覆盖。
- `sync-web-schema` 现在会优先读取 `web_schema/source/data_tool_schema.json`，缺失时再回退解析 `featureFormats.ts`。
