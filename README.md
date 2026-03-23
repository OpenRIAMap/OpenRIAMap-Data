# RelayPackage 与新数据仓库规范（Phase 0 协议冻结版）

> 版本：v1  
> 状态：Phase 0 冻结协议  
> 范围：仓库结构、RelayPackage 结构、INDEX / Delete 格式、图片命名、Merge 分片、校验规则、组件职责边界

---

## 1. 目的

本规范用于定义新数据仓库体系与 RelayPackage 工作流的冻结协议。

它是以下部分共享的统一基线：

- 正式数据仓库
- RelayPackage
- RelayPackage Refresh Component（包刷新组件）
- Data_Merge_Tool
- 前端图层管理 / 工作流导出逻辑

本规范的目标是标准化：

- 要素的 **新增 / 覆盖 / 删除**
- 基于 **ID** 的要素与图片绑定关系
- 基于包的传递、校验、入库与 Merge 重建流程

---

## 2. 核心语义

### 2.1 要素状态

系统中只允许存在三种操作状态：

- **新增**
- **覆盖**
- **删除**

定义如下：

- 一个新出现的要素 JSON = **新增**
- 一个已有要素 JSON 被替换 = **覆盖**
- 一个已有要素的图片集合被替换、增加或重排 = **覆盖**
- 将一个已有要素 ID 从系统中移除 = **删除**

---

### 2.2 图片语义

图片不作为独立业务对象处理。

图片始终被视为：

**从属于某个要素 ID 的附属资源**

因此：

- 图片更新不作为第四种操作类型
- 所有图片更新统一并入要素的 **覆盖**

---

### 2.3 主键

要素的唯一主键为：

- **ID**

要素与图片之间的绑定关系仅依赖：

- **ID**

---

## 3. 正式仓库结构

### 3.1 顶层仓库结构

```text
/Data_Spilt
/Data_Merge
/Picture
/Data_Merge_Tool
```

该顶层结构在正式仓库中冻结。

---

### 3.2 Data_Spilt

#### 用途
- 源数据层
- 人工可维护层
- 单要素单文件存储层

#### 目录规则
- 普通类：`world/class/id.json`
- 特殊类（`ISG / ISL / ISP`）：`world/class/kind/id.json`

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

### 3.3 Data_Merge

#### 用途
- 网站运行读取层
- 分片存储层
- 由 Tool 自动生成的层

#### 目录规则
- 结构与 `Data_Spilt` 镜像一致
- 数据文件采用固定长度分片：`chunk_xxx.json`

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
- `Data_Merge` 不允许人工编辑
- `Data_Merge` 只能由正式 Tool 重建

---

### 3.4 Picture

#### 用途
- 要素附属图片资源层

#### 目录规则
- 与 `Data_Spilt` 使用相同层级结构
- 图片目录名 = 要素 ID
- 图片文件名 = `ID_n.ext`

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

## 4. RelayPackage 结构

### 4.1 RelayPackage 顶层结构

```text
RelayPackage/
  INDEX.json
  Delete.json
  Data_Spilt/
  Picture/
```

#### 强制规则
- RelayPackage 中不得包含 `Data_Merge`
- RelayPackage 只承载增量内容
- RelayPackage 允许人工编辑，但最终是否合法以刷新组件 / Tool 校验结果为准

---

### 4.2 RelayPackage 语义

- `Data_Spilt/`：本次 **新增** 或 **覆盖** 的要素 JSON
- `Picture/`：本次 **新增** 或 **覆盖** 的图片文件
- `Delete.json`：待删除的要素 ID
- `INDEX.json`：包摘要与元信息

---

## 5. INDEX 规范

### 5.1 Data_Spilt 分类目录 INDEX

#### 适用位置
- `Data_Spilt/{world}/{class}/INDEX.json`
- `Data_Spilt/{world}/{class}/{kind}/INDEX.json`

#### 固定字段
```json
{
  "version": 12,
  "itemCount": 358,
  "updatedAt": "2026-03-21T15:42:00+08:00",
  "items": [
    "RLE_0001",
    "RLE_0002",
    "RLE_0003"
  ]
}
```

#### 字段定义
- `version`：该分类目录版本号
- `itemCount`：该目录中要素总数
- `updatedAt`：最近更新时间
- `items`：该目录下全部要素 ID 列表

---

### 5.2 Data_Merge 分类目录 INDEX

#### 适用位置
- `Data_Merge/{world}/{class}/INDEX.json`
- `Data_Merge/{world}/{class}/{kind}/INDEX.json`

#### 固定字段
```json
{
  "version": 12,
  "itemCount": 358,
  "updatedAt": "2026-03-21T15:42:00+08:00",
  "items": [
    "RLE_0001",
    "RLE_0002"
  ],
  "chunkSize": 200,
  "chunkCount": 2,
  "chunks": [
    {
      "file": "chunk_001.json",
      "itemCount": 200,
      "items": [
        "RLE_0001",
        "RLE_0002"
      ]
    },
    {
      "file": "chunk_002.json",
      "itemCount": 158,
      "items": [
        "RLE_0201",
        "RLE_0202"
      ]
    }
  ]
}
```

#### 字段定义
- `version`
- `itemCount`
- `updatedAt`
- `items`
- `chunkSize`
- `chunkCount`
- `chunks`

其中 `chunks` 的每个条目必须包含：
- `file`
- `itemCount`
- `items`

---

### 5.3 Data_Spilt / Data_Merge 根目录 INDEX

#### 适用位置
- `Data_Spilt/INDEX.json`
- `Data_Merge/INDEX.json`

#### 固定字段
```json
{
  "version": 7,
  "updatedAt": "2026-03-21T15:42:00+08:00"
}
```

#### 字段定义
- `version`
- `updatedAt`

根 INDEX 不承载明细列表。

---

### 5.4 Picture 分类目录 INDEX

#### 适用位置
- `Picture/{world}/{class}/INDEX.json`
- `Picture/{world}/{class}/{kind}/INDEX.json`

#### 固定字段
```json
{
  "version": 12,
  "itemCount": 120,
  "updatedAt": "2026-03-21T15:42:00+08:00",
  "mapping": {
    "RLE_0001": [
      "RLE_0001/RLE_0001_1.jpg",
      "RLE_0001/RLE_0001_2.jpg"
    ],
    "RLE_0002": [
      "RLE_0002/RLE_0002_1.png"
    ]
  }
}
```

#### 字段定义
- `version`
- `itemCount`
- `updatedAt`
- `mapping`

其中：
- `itemCount` = 有图片记录的要素 ID 数量
- `mapping` = `ID -> 图片相对路径列表`

---

### 5.5 Picture 根目录 INDEX

#### 适用位置
- `Picture/INDEX.json`

#### 固定字段
```json
{
  "version": 7,
  "updatedAt": "2026-03-21T15:42:00+08:00"
}
```

---

### 5.6 RelayPackage INDEX

#### 固定字段
```json
{
  "version": 1,
  "packageId": "PKG_20260321_1542_001",
  "createdAt": "2026-03-21T15:42:00+08:00",
  "operator": "Yiqi Zhu",
  "splitFileCount": 12,
  "pictureFileCount": 27,
  "deleteCount": 3,
  "toolVersion": "1.0",
  "note": "zth RLE and STA update"
}
```

#### 字段定义
- `version`
- `packageId`
- `createdAt`
- `operator`
- `splitFileCount`
- `pictureFileCount`
- `deleteCount`
- `toolVersion`
- `note`

说明：
- `note` 为可选字段
- 其余字段建议视为必填

---

## 6. Delete 规范

### 6.1 固定字段
```json
{
  "markedAt": "2026-03-21T15:42:00+08:00",
  "items": [
    "RLE_0001",
    "RLE_0002",
    "STA_0103"
  ]
}
```

### 6.2 字段定义
- `markedAt`：删除标记生成时间
- `items`：待删除要素 ID 列表

### 6.3 删除语义
正式 Tool 执行删除时，必须：

1. 删除 `Data_Spilt` 中对应 JSON
2. 删除 `Picture` 中对应 ID 图片目录
3. 重建受影响的 `Data_Merge`
4. 更新受影响的 `INDEX` 文件

删除策略冻结为：

- **物理删除**

---

## 7. 图片命名规则

### 7.1 目录命名
图片目录名必须为：

- `ID`

示例：
```text
RLE_0001/
```

### 7.2 文件命名
图片文件名必须为：

- `ID_n.ext`

示例：
```text
RLE_0001_1.jpg
RLE_0001_2.jpg
```

### 7.3 冻结规则
- 不设置封面图概念
- 图片顺序完全由 `_n` 表示
- 前端上传时必须自动重命名
- Tool / Refresh Component 按此规则校验

---

## 8. Merge 分片规则

### 8.1 分片策略
- 分片长度为**固定全局值**
- v1 不支持按类配置不同分片长度
- v1 不支持直接对 chunk 内局部编辑
- v1 以**受影响目录级**重建 `Data_Merge`

### 8.2 分片文件名
chunk 文件统一使用：

```text
chunk_001.json
chunk_002.json
```

### 8.3 分片元数据
`Data_Merge/INDEX.json` 必须记录：
- `chunkSize`
- `chunkCount`
- `chunks[].file`
- `chunks[].itemCount`
- `chunks[].items`

---

## 9. 时间、排序与版本规则

### 9.1 时间格式
所有时间戳字段统一使用：

- **ISO 8601**
- **UTC+8**
- 建议精确到分钟或秒
- 推荐格式：`2026-03-21T15:42:00+08:00`

适用字段：
- `updatedAt`
- `createdAt`
- `markedAt`

---

### 9.2 稳定排序
以下 `items` 列表建议以稳定的字符串升序写出：

- `Data_Spilt INDEX.items`
- `Data_Merge INDEX.items`
- `Data_Merge INDEX.chunks[].items`
- `Delete.json.items`

冻结原则：
- Tool 输出必须稳定
- Refresh Component 输出必须稳定

---

### 9.3 版本规则
- Tool 每次成功写入一个受影响分类目录时，该目录 `version + 1`
- Tool 每次成功写入一个根目录时，根目录 `version + 1`
- Refresh Component 的重建不改变 `RelayPackage/INDEX.json.version` 的 schema 含义
- `RelayPackage/INDEX.json.version` 表示**结构版本**，不是包内容修订号

---

## 10. RelayPackage Refresh Component

### 10.1 定位
刷新组件只处理：

- **当前 RelayPackage 本身**

不得直接修改正式仓库。

---

### 10.2 职责
刷新组件必须：

1. 扫描当前包内容
2. 重建包级 `INDEX.json`
3. 执行包内预校验
4. 输出高可读报告
5. 可选重新打包为 zip

---

### 10.3 输入
- 当前 RelayPackage 目录

### 10.4 输出
- 更新后的 `RelayPackage/INDEX.json`
- `check_report.md`
- 可选 `check_report.json`
- 可选 zip 包

### 10.5 部署原则
冻结为：
- 外部统一维护程序
- 包内只可包含启动入口
- 不将完整正式可执行程序复制进每个包

---

## 11. 正式 Tool 边界

### 11.1 正式 Tool 负责
1. 读取包
2. 预校验
3. 应用新增 / 覆盖
4. 执行删除
5. 重建 Merge
6. 更新 INDEX 文件
7. 输出正式报告

### 11.2 正式 Tool 不负责
- 前端缓存管理
- 手工编辑 UI 逻辑
- 网站 UI 渲染
- 包内图片排序交互

---

## 12. 校验与冲突检测

### 12.1 问题分级
预校验问题冻结为两级：

- **阻断型**
- **警告型**

---

### 12.2 阻断型问题
默认必须阻止直接应用：

- JSON 非法
- 目录层级错误
- 文件名与内部 ID 不一致
- 图片文件名不符合 `ID_n`
- 同一包内同 ID 冲突且无法判定
- 缺失必需包文件

---

### 12.3 警告型问题
可以提示后允许继续：

- 图片编号不连续
- 覆盖已有要素
- 覆盖已有图片
- 删除目标不存在
- 图片目录为空
- 包内 INDEX 与实际文件不一致但可重建

---

### 12.4 报告格式
冻结的人类可读主报告为：

- `check_report.md`

可选附加输出：
- `check_report.json`

---

## 13. 前端导出职责边界

### 13.1 前端职责
前端图层管理 / 工作流端后续必须支持：

- 新增 / 覆盖 JSON 的本地缓存
- 图片本地缓存
- 图片自动重命名为 `ID_n.ext`
- 删除标记列表维护
- 自动导出 RelayPackage
- 自动生成 `RelayPackage/INDEX.json`
- 自动生成 `Delete.json`

### 13.2 前端不得直接处理
- 正式仓库写入
- 正式 Merge 重建
- 正式 INDEX 重建

这些职责冻结为 Tool 侧。

---

## 14. Phase 0 完成标准

当以下内容全部确认后，Phase 0 视为完成：

1. 正式仓库顶层结构
2. RelayPackage 结构
3. 全部 INDEX schema
4. Delete schema
5. 图片命名规则
6. Merge 分片规则
7. Refresh Component 职责
8. 正式 Tool 边界
9. 校验问题分级
10. 时间 / 排序 / 版本规则

---

## 15. Phase 0 之后固定开发顺序

协议冻结后，推荐顺序固定为：

1. **Phase 1：建立新仓库骨架**
2. **Phase 2：实现 Data_Merge_Tool**
3. **Phase 3：实现 RelayPackage Refresh Component**
4. **Phase 4：准备并测试样例包**
5. **Phase 5：接入前端图层管理 / 工作流导出**

---

## 16. 建议的最小示例布局

```text
Data_Spilt/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      RLE_0001.json

Data_Merge/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      chunk_001.json

Picture/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      RLE_0001/
        RLE_0001_1.jpg

RelayPackage/
  INDEX.json
  Delete.json
  Data_Spilt/
  Picture/
```

---

## 17. 备注

- 本规范中继续使用 `Data_Spilt` 这一拼写，以保持与当前协议一致。
- 如果未来仓库决定将 `Data_Spilt` 更名为 `Data_Split`，应视为一个独立的协议变更与迁移步骤，而不是在 Phase 0 内隐式调整。

---
