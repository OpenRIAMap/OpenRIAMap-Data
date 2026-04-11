# OpenRIAMap-Data

> 当前工具版本：v5.7  
> 当前状态：正式维护版数据仓库  
> 适用范围：`Data_Spilt` / `Data_Merge` / `Picture` / `Data_Merge_Tool` / `RelayPackage` / 冷归档工作流

---

## 1. 仓库定位

`OpenRIAMap-Data` 是 OpenRIAMap 的正式数据仓库，用于维护：

- `Data_Spilt`：单要素源数据层
- `Data_Merge`：Web 侧读取层
- `Picture`：按要素 ID 管理的图片资源层
- `Data_Merge_Tool`：正式的数据维护、校验、重建、归档与推送工具

当前仓库已经不是单纯的协议草案仓库，而是 **“协议已经落地、工具已正式参与维护流程”** 的运行版仓库。

---

## 2. 顶层目录结构

```text
/Data_Spilt
/Data_Merge
/Picture
/Data_Merge_Tool
/docs
/README.md
```

### 2.1 目录职责

#### `Data_Spilt`
- 正式源数据层
- 单要素单文件存储
- 允许作为正式维护结果存在于仓库中
- 是 `Data_Merge` 的唯一重建来源

#### `Data_Merge`
- Web 运行读取层
- 以分片 `chunk_xxx.json` 形式存储
- 只能由 `Data_Merge_Tool` 重建
- 不应人工直接编辑

#### `Picture`
- 要素图片资源层
- 图片始终附属于某个要素 ID
- 与 `Data_Spilt` 的目录层级保持一致

#### `Data_Merge_Tool`
- 正式维护入口
- 负责：
  - 载入 JSON / 图片 / RelayPackage
  - 预校验
  - 写入 `Data_Spilt` / `Picture` / 删除结果
  - 登记并提交 `Data_Merge` 重建
  - 冷归档与 Git 推送

#### `docs`
- 补充说明与历史协议文档
- 其中旧的 Phase 0 文档可作为语义来源参考
- 当前仓库行为以本 README 与 Tool 实际实现为准

---

## 3. 核心语义

### 3.1 三种正式操作

系统中正式承认三种维护动作：

- 新增
- 覆盖
- 删除

含义如下：

- 新出现的要素 JSON：新增
- 已有要素 JSON 被替换：覆盖
- 已有要素图片集合被整体替换或补充：覆盖
- 已有要素 ID 从系统中移除：删除

### 3.2 图片不是独立业务对象

图片不作为独立业务类型单独管理。

图片始终被视为：

**某个要素 ID 的附属资源**

因此：

- 图片更新不被视为第四种操作类型
- 图片更新统一并入要素覆盖语义

### 3.3 主键与绑定关系

唯一主键为：

- `ID`

要素与图片之间的绑定关系也仅依赖：

- `ID`

---

## 4. 正式数据层结构规则

### 4.1 `Data_Spilt`

#### 用途
- 源数据层
- 单要素单文件层
- `Data_Merge` 的唯一重建来源

#### 目录规则
- 普通类：`world/class/id.json`
- 特殊类（如 `ISG / ISL / ISP`）：`world/class/kind/id.json`

#### 示例
```text
Data_Spilt/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      RLE_0001.json
    ISG/
      station/
        INDEX.json
        ISG_0001.json
```

---

### 4.2 `Data_Merge`

#### 用途
- Web 端运行读取层
- 分片缓存层
- 由 Tool 自动生成

#### 目录规则
- 结构与 `Data_Spilt` 镜像一致
- 数据文件命名为：`chunk_xxx.json`

#### 示例
```text
Data_Merge/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      chunk_001.json
      chunk_002.json
    ISG/
      station/
        INDEX.json
        chunk_001.json
```

#### 强制规则
- 不允许人工直接编辑 `Data_Merge`
- `Data_Merge` 只能由 `Data_Merge_Tool` 重建并提交

---

### 4.3 `Picture`

#### 用途
- 要素图片资源层

#### 目录规则
- 与 `Data_Spilt` 使用相同层级结构
- 图片目录名 = 要素 ID
- 图片文件名建议为：`ID_n.ext`

#### 示例
```text
Picture/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      RLE_0001/
        RLE_0001_1.jpg
        RLE_0001_2.jpg
    ISG/
      station/
        INDEX.json
        ISG_0001/
          ISG_0001_1.png
```

---

## 5. RelayPackage 结构与定位

### 5.1 顶层结构

```text
RelayPackage/
  INDEX.json
  Delete.json
  Data_Spilt/
  Picture/
```

### 5.2 语义

- `Data_Spilt/`：本次新增或覆盖的要素 JSON
- `Picture/`：本次新增或覆盖的图片
- `Delete.json`：待删除的要素 ID 列表
- `INDEX.json`：包摘要与元信息

### 5.3 强制规则

- RelayPackage 中不得包含 `Data_Merge`
- RelayPackage 只承载本次要传递的增量内容
- 最终是否可入库，以 Tool 校验结果为准

---

## 6. INDEX 与删除信息

### 6.1 INDEX 的作用

`INDEX.json` 用于描述目录层统计与更新时间，主要用于：

- 快速核对目录内容
- 标记版本变化
- 供工具或后续检查流程使用

### 6.2 当前维护原则

- 分类叶子目录会维护自己的 `INDEX.json`
- world 层目录会维护自己的 `INDEX.json`
- 根目录也会维护自己的 `INDEX.json`
- `Data_Merge_Tool` 在正式写库后会同步更新受影响目录的索引

### 6.3 删除信息

删除通过 `Delete.json` 或会话中的删除 staging 表达。

其语义是：

- 删除某个 ID 对应的要素
- 同时删除其关联图片目录
- 后续重建 Merge 时，不再包含该要素

---

## 7. Data_Merge_Tool 的目录结构

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

### 7.1 关键子目录职责

#### `bin/`
工具主代码目录。`tool.py` 为主入口。

#### `config/`
配置目录，包括运行配置和策略配置。

#### `source_data/`
运行期输入目录：

```text
source_data/
  json_inputs/
  image_inputs/
  relay_packages/
```

#### `reports/`
报告目录，包括 `latest` 与归档报告。

#### `logs/`
运行日志目录。

#### `workspace/`
运行期临时目录，用于：

- zip 解压
- 临时包构造
- 运行态缓存文件

#### `web_schema/`
Web schema 同步目录，包括 source 与 cache。

---

## 8. Tool 的两种正式载入模式

当前工具支持两种正式输入模式。

### 8.1 手动叠加模式

命令：

- `load-json` / `lj`
- `load-image` / `li`

特点：

- 可多次执行
- 内容叠加到当前 staging
- 适合手动整理一批 JSON + 图片后再统一提交

典型流程：

```text
lj all
li all
pv
rp
cm
rb --all
cm
ps
```

---

### 8.2 package 独占模式

命令：

- `load-package` / `lp`

特点：

- package 会独占当前 staging
- staging 非空时不可执行 `lp`
- 适合直接使用标准 RelayPackage 入库

典型流程：

```text
lp package_20260411.zip
pv
rp
cm
rb --all
cm
ps
```

---

### 8.3 二者互斥规则

- 当当前 staging 为 package 模式时，不允许再执行 `lj` / `li`
- 当当前 staging 已有手动叠加内容时，不允许再执行 `lp`
- 若要切换模式，应先 `commit` 或 `discard`

---

## 9. 完整数据维护流程

当前正式维护流程如下。

### 9.1 第一步：先做 Git 同步

先在仓库根目录执行：

```bash
git pull --rebase origin main
```

这一步是 **Git 操作**，不是 Tool 内部命令。

它的目的，是先把远端主线同步到本地，避免后续写库和推送时遇到远端提交冲突。

---

### 9.2 第二步：启动 Tool

可通过以下任一方式启动：

```bat
launch_tool.bat
```

或：

```bat
Data_Merge_Tool\launch_tool.bat
```

或直接执行：

```bat
python Data_Merge_Tool\bin\tool.py
```

---

### 9.3 第三步：载入数据

二选一：

#### 方式 A：手动叠加
```text
lj all
li all
```

#### 方式 B：标准包独占
```text
lp xxx.zip
```

---

### 9.4 第四步：检查 staging

常用命令：

- `pv`：查看当前 staging 摘要
- `rp`：查看最近一次报告
- `st`：查看当前会话状态

---

### 9.5 第五步：第一次 commit

执行：

```text
cm
```

这一步会把 source staging 正式写入：

- `Data_Spilt`
- `Picture`
- 删除结果

并更新受影响目录的 `INDEX.json`。

---

### 9.6 第六步：登记 Merge 重建目标

执行：

```text
rb --all
```

或指定目录：

```text
rb zth RLE
rb zth ISG station
```

**注意：当前实现中，`rebuild` 只是登记待重建目标，并不会立即写入 `Data_Merge`。**

---

### 9.7 第七步：第二次 commit

再次执行：

```text
cm
```

这一步才会真正把登记过的目标重建写入：

- `Data_Merge`

也就是说，当前正式语义是：

```text
source commit  ->  rebuild register  ->  merge commit
```

---

### 9.8 第八步：推送

根据需要选择：

- `ps`：完整冷归档 + Data 仓库推送
- `pc`：只做冷归档
- `pd`：只做 Data 仓库推送

---

## 10. pull 与 push 的真实语义

### 10.1 pull 会下载什么

这里所说的 pull 是：

```bash
git pull --rebase origin main
```

它会下载并同步：

- 远端 Data 仓库中已被 Git 跟踪的文件
- 包括 `Data_Spilt`、`Data_Merge`、`Picture`
- 包括 `Data_Merge_Tool` 的代码、配置与文档
- 包括根 `README.md` 与 `docs`

### 10.2 pull 不会下载什么

不会自动下载：

- `ColdToolArchive` Release 里的归档 zip
- 本地未被 Git 跟踪的临时文件
- workspace 运行期缓存

### 10.3 push 的三种模式

#### `push` / `ps`
完整流程：

1. 冷归档打包
2. 上传到冷仓库 Release
3. 清理本地运行期 source_data / workspace / 部分 latest 内容
4. 生成 push log
5. `git add` / `git commit`
6. `git pull --rebase`
7. `git push`

#### `push-cold` / `pc`
只执行：

- 冷归档打包与上传
- 本地运行期清理
- push log 记录

不执行：

- Data 仓库 git 推送

#### `push-data` / `pd`
只执行：

- Data 仓库提交与推送
- push log 进入 Git 提交

不执行：

- 冷归档上传

---

## 11. 命令总览

### 基础命令
- `help` / `hp`：查看命令说明
- `status` / `st`：查看当前会话状态
- `preview` / `pv`：查看 staging 摘要
- `report` / `rp`：查看最近一次报告
- `check-env` / `ce`：检查运行环境
- `exit` / `ex`：退出工具

### 输入相关
- `load-package` / `lp`
- `load-json` / `lj`
- `load-image` / `li`

### 写库相关
- `commit` / `cm`
- `rebuild` / `rb`
- `discard` / `dc`
- `clear` / `cl`
- `sync-web-schema` / `sw`

### 推送相关
- `push` / `ps`
- `push-data` / `pd`
- `push-cold` / `pc`

### 新帮助模式
当前版本支持：

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

---

## 12. rebuild / commit 的双阶段语义

这是当前实现中最需要明确的一点。

### 当前真实行为

- `rebuild`：登记待重建目标
- `commit`：真正写入 Merge

### 不要误解为

- `rebuild` 一执行就完成了 Merge 文件重建

### 推荐理解方式

把它理解为：

- `rebuild`：把待重建目录加入任务列表
- `commit`：执行这些重建任务并写入仓库

---

## 13. 报告、日志与冷归档

### 13.1 报告

报告主要存放在：

- `Data_Merge_Tool/reports/latest`
- `Data_Merge_Tool/reports/archive`

常见报告包括：

- 预校验报告
- commit 报告
- push 报告
- 环境检查报告

### 13.2 运行日志

日志主要在：

- `logs/session_*`
- `logs/push`

### 13.3 冷归档内容

冷归档通常包含：

- 当前 `source_data` 内容
- 当前运行日志
- 归档 manifest

### 13.4 push log 的特殊性

普通运行日志不一定进入 Data 仓库，但 push log 在当前实现中会被强制纳入 Git 提交，以便保留：

- 本次推送摘要
- 冷归档信息
- 提交与推送记录

这意味着：

- 以后再次 `git pull` 时，已提交的 push log 也会被拉到本地

---

## 14. Web schema 同步

当前 Tool 支持通过：

```text
sw
```

同步 Web schema 缓存。

### 当前同步逻辑

优先读取：

- `Data_Merge_Tool/web_schema/source/data_tool_schema.json`

若该文件不存在，再回退解析：

- `featureFormats.ts`

同步结果会更新：

- `world_map.json`
- `special_class_rules.json`
- `feature_classes.json`
- `workflow_kind_registry.json`

这一步的作用，是让 Tool 的：

- world 目录映射
- 特殊类判断
- feature class 识别

与 Web 端保持同步。

---

## 15. 常见问题

### Q1. 当前流程里有 `pull` 指令吗？
没有。

当前 `pull` 指的是 Git 命令：

```bash
git pull --rebase origin main
```

它不是 Tool 内部命令。

---

### Q2. 为什么 `rebuild` 后还要再 `commit` 一次？
因为当前实现中：

- `rebuild` 只登记目标
- 真正写入 Merge 发生在后续 `commit`

---

### Q3. `lp` 和 `lj/li` 为什么不能混用？
因为当前 staging 机制分为：

- 手动叠加模式
- package 独占模式

二者互斥，避免来源混杂、覆盖语义不清。

---

### Q4. `push` 和 `push-data` 有什么区别？

- `push`：冷归档 + Data 仓库推送
- `push-data`：仅 Data 仓库推送

---

### Q5. pull 之后为什么拿不到冷归档 zip？
因为冷归档 zip 在冷仓库 Release 中，不在当前 Data 仓库的 Git tree 里。

---

### Q6. 图片为什么按 ID 目录管理？
因为图片不是独立业务对象，而是某个要素 ID 的附属资源。按 ID 分组最符合：

- 覆盖语义
- 删除语义
- 包内整体替换语义

---

## 16. 当前版本说明

### 16.1 当前版本口径

- 当前 Tool 版本：`v5.7`
- 当前 README 描述的是 **当前实现口径**，不是仅限 Phase 0 草案口径

### 16.2 历史协议文档的地位

`docs/` 中保留的旧协议文档仍然是重要的语义来源，但若其描述与当前工具行为存在差异，应以：

1. 当前 Tool 实现
2. 本 README 的当前流程描述

为准。

---

## 17. 建议的日常使用顺序

推荐维护顺序如下：

```text
git pull --rebase origin main
启动 Tool
载入数据（lj/li 或 lp）
preview / report 检查
commit
rebuild
commit
push
```

若只想拆分执行，可使用：

```text
push-cold
push-data
```

分别完成冷归档与 Data 仓库推送。
