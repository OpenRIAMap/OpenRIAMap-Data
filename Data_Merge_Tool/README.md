# OpenRIAMap Data_Merge_Tool v5.7

本目录是 `OpenRIAMap-Data` 的正式工具子目录，用于完成：

- JSON / 图片 / RelayPackage 载入
- 预校验与报告输出
- `Data_Spilt` / `Picture` / 删除结果写入
- `Data_Merge` 重建登记与正式写入
- 冷归档与 Data 仓库推送

## 当前定位

从本版本开始，**完整架构、维护流程与命令说明请以仓库根目录 `README.md` 为准**。  
本文件只保留 Tool 目录层面的快速说明。

## 运行方式

双击：

```bat
launch_tool.bat
```

或命令行执行：

```bat
python bin\tool.py
```

## 当前命令帮助方式

工具内支持：

```text
hp
hp <command>
hp all
```

例如：

```text
hp rebuild
hp rb
hp push
hp lp
```

## 目录说明

```text
Data_Merge_Tool/
  README.md
  launch_tool.bat
  bin/
  config/
  logs/
  reports/
  samples/
  source_data/
  web_schema/
  workspace/
```

### `source_data/`
运行期输入目录：

```text
source_data/
  json_inputs/
  image_inputs/
  relay_packages/
```

### `reports/`
输出预校验、commit、push 与环境检查报告。

### `logs/`
保存 session 日志与 push 日志。

### `workspace/`
保存 zip 解压、临时归档构造与运行态缓存。

### `web_schema/`
保存 Web schema source 与 cache，用于 world 映射和规则同步。

## 当前维护流程摘要

推荐顺序：

```text
lj / li 或 lp
pv / rp / st
cm
rb --all
cm
ps
```

补充说明：

- `rebuild` 当前只登记 Merge 目标
- 真正写入 `Data_Merge` 发生在后续 `commit`
- `pull` 是 Git 操作，不是 Tool 内部命令

## 版本说明

当前 Tool 版本统一为：

- `v5.7`

若根目录 README 与本文件存在描述重复，以根目录 `README.md` 为主。
