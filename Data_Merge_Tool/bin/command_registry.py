COMMAND_ALIASES = {
    "help": "hp",
    "status": "st",
    "load-package": "lp",
    "load-json": "lj",
    "load-image": "li",
    "preview": "pv",
    "report": "rp",
    "commit": "cm",
    "rebuild": "rb",
    "discard": "dc",
    "clear": "cl",
    "sync-web-schema": "sw",
    "push": "ps",
    "push-data": "pd",
    "push-cold": "pc",
    "check-env": "ce",
    "exit": "ex",
}

COMMAND_DESCRIPTIONS = {
    "help": "查看命令说明",
    "status": "查看当前 staging 与会话状态",
    "load-package": "载入 RelayPackage（独占 staging）",
    "load-json": "载入 JSON 数据到手动 staging",
    "load-image": "载入图片到手动 staging",
    "preview": "预览当前 staging 摘要",
    "report": "查看最近一次报告",
    "commit": "将当前 staging 正式写入仓库",
    "rebuild": "登记待重建的 Merge 目标",
    "discard": "丢弃当前 staging",
    "clear": "清空命令上下文，不清 staging",
    "sync-web-schema": "同步 Web schema 缓存",
    "push": "执行完整冷归档与 Data 推送流程",
    "push-data": "仅执行 Data 仓库 git 推送",
    "push-cold": "仅执行冷仓库归档上传",
    "check-env": "检查本地、git 与 GitHub 环境",
    "exit": "退出工具",
}

COMMAND_HELP_DETAILS = {
    "help": {
        "summary": "查看命令总览，或展开指定命令的详细帮助。",
        "usage": [
            {"syntax": "hp", "desc": "显示全部命令总览。"},
            {"syntax": "help", "desc": "与 hp 相同。"},
            {"syntax": "hp <command>", "desc": "显示某个命令的详细帮助；支持命令全名或别名。"},
            {"syntax": "hp all", "desc": "按顺序展开全部命令的详细帮助。"},
        ],
        "arguments": [
            {"name": "<command>", "desc": "命令全名或别名，例如 rebuild / rb。"},
        ],
        "notes": [
            "空参数时输出命令总览。",
            "all 或 --all 会展开全部命令的详细说明。",
            "推荐在不确定参数格式时先执行 hp <command>。",
        ],
        "examples": ["hp", "hp rebuild", "hp rb", "hp all"],
        "related": ["status", "report"],
    },
    "status": {
        "summary": "输出当前会话状态、staging 统计、阻断数量与 push 周期累计信息。",
        "usage": [{"syntax": "st", "desc": "输出当前会话状态。"}],
        "notes": [
            "该命令不会修改任何 staging 内容。",
            "可用于确认当前模式、pending 数量、blocking 数量以及 session_id。",
        ],
        "examples": ["st"],
        "related": ["preview", "report", "help"],
    },
    "load-package": {
        "summary": "载入标准 RelayPackage；该模式为独占 staging。",
        "usage": [
            {"syntax": "lp", "desc": "扫描 source_data/relay_packages，并在交互列表中选择一个标准包。"},
            {"syntax": "lp <zip文件名>", "desc": "直接载入指定 zip 包。"},
            {"syntax": "lp <目录名>", "desc": "直接载入指定目录包。"},
        ],
        "arguments": [
            {"name": "<zip文件名>", "desc": "位于 source_data/relay_packages 下的 zip 包文件名或相对路径。"},
            {"name": "<目录名>", "desc": "位于 source_data/relay_packages 下的标准包目录名或相对路径。"},
        ],
        "notes": [
            "当前 staging 不为空时不可执行。请先 commit 或 discard。",
            "载入 zip 时会先解压到 workspace/tmp_packages，再读取有效包根目录。",
            "包内各级 INDEX.json 会被跳过；图片按 world + class + kind + id 聚组处理。",
        ],
        "examples": ["lp", "lp package_20260411.zip", "lp test_package_dir"],
        "related": ["preview", "report", "commit", "discard"],
    },
    "load-json": {
        "summary": "从 source_data/json_inputs 载入 JSON 要素到手动 staging。",
        "usage": [
            {"syntax": "lj", "desc": "等价于 lj all。"},
            {"syntax": "lj all", "desc": "载入 json_inputs 下可扫描到的全部 JSON。"},
            {"syntax": "lj <文件名或相对路径>", "desc": "仅载入指定 JSON 文件。"},
        ],
        "arguments": [
            {"name": "<文件名或相对路径>", "desc": "相对于 source_data/json_inputs 的路径，也可直接写文件名。"},
        ],
        "notes": [
            "load-json 属于手动叠加模式，可多次执行并累加到当前 staging。",
            "当前 staging 为 package 独占模式时不可执行。",
            "载入后会立即生成新的预校验报告。",
        ],
        "examples": ["lj", "lj all", "lj update_20260411.json", "lj zth/roads/part_01.json"],
        "related": ["load-image", "preview", "report", "commit"],
    },
    "load-image": {
        "summary": "从 source_data/image_inputs 载入图片并自动尝试绑定到现有要素 ID。",
        "usage": [
            {"syntax": "li", "desc": "等价于 li all。"},
            {"syntax": "li all", "desc": "载入 image_inputs 下可扫描到的全部图片。"},
            {"syntax": "li <文件名或相对路径>", "desc": "仅载入指定图片文件。"},
        ],
        "arguments": [
            {"name": "<文件名或相对路径>", "desc": "相对于 source_data/image_inputs 的路径，也可直接写文件名。"},
        ],
        "notes": [
            "load-image 属于手动叠加模式，可与 load-json 叠加使用。",
            "当前 staging 为 package 独占模式时不可执行。",
            "无法自动绑定到目标要素的图片会被跳过并写入 warning。",
            "若当前会话已将同 ID 标记删除，则该图片会被阻断。",
        ],
        "examples": ["li", "li all", "li RLE_0001_1.jpg", "li zth/roads/RLE_0001_2.png"],
        "related": ["load-json", "preview", "report", "commit"],
    },
    "preview": {
        "summary": "输出当前 staging 摘要，包括待写入 Split、图片、删除与 Merge 目标统计。",
        "usage": [{"syntax": "pv", "desc": "显示当前 staging 摘要。"}],
        "notes": [
            "该命令不会写库，也不会改变 staging。",
            "适合在 commit 前快速核对载入结果与当前问题数量。",
        ],
        "examples": ["pv"],
        "related": ["status", "report", "commit"],
    },
    "report": {
        "summary": "显示最近一次报告内容。优先顺序通常为 precheck、commit、push。",
        "usage": [{"syntax": "rp", "desc": "输出最近一次可用报告的正文。"}],
        "notes": [
            "若存在最新预校验报告，会优先显示该报告。",
            "当前无可用报告时会提示“当前没有可显示的报告”。",
        ],
        "examples": ["rp"],
        "related": ["preview", "status", "commit"],
    },
    "commit": {
        "summary": "将当前 staging 正式写入仓库；source 与 merge 两类 pending 会在同一次 commit 中分别处理。",
        "usage": [{"syntax": "cm", "desc": "执行一次正式写库。"}],
        "notes": [
            "当前没有待提交内容时不可执行。",
            "存在 blocking 问题时不可执行；请先执行 report 查看详情。",
            "当存在 source pending 时，会写入 Data_Spilt / Picture / Delete。",
            "当存在 merge pending 时，会写入 Data_Merge。",
        ],
        "examples": ["cm"],
        "related": ["preview", "report", "rebuild", "discard"],
    },
    "rebuild": {
        "summary": "登记待重建的 Merge 目标；真正写入 Data_Merge 的动作发生在后续 commit 中。",
        "usage": [
            {"syntax": "rb --all", "desc": "将当前 dirty_merge_targets 全部登记为待重建目标。"},
            {"syntax": "rb <world> <class>", "desc": "登记普通类目录重建。"},
            {"syntax": "rb <world> <class> <kind>", "desc": "登记特殊类 kind 目录重建。"},
        ],
        "arguments": [
            {"name": "<world>", "desc": "世界代码目录名，例如 zth。"},
            {"name": "<class>", "desc": "类别目录名，例如 RLE。"},
            {"name": "<kind>", "desc": "特殊类子目录名，例如 station。"},
        ],
        "notes": [
            "rebuild 只负责登记目标，不直接写 Merge 文件。",
            "通常在完成一次 source commit 后，再执行 rebuild，然后再次 commit。",
            "参数格式非法时会写入 blocking。",
        ],
        "examples": ["rb --all", "rb zth RLE", "rb zth ISG station"],
        "related": ["commit", "preview", "status", "report"],
    },
    "discard": {
        "summary": "丢弃当前 staging，并清理当前会话里由 package 解压产生的临时目录。",
        "usage": [{"syntax": "dc", "desc": "放弃当前 staging。"}],
        "notes": [
            "该命令会清空 pending_split、pending_pictures、pending_delete 与 pending_merge。",
            "会话日志与历史报告不会被删除。",
        ],
        "examples": ["dc"],
        "related": ["commit", "clear", "status"],
    },
    "clear": {
        "summary": "清空命令上下文，但不清 staging。",
        "usage": [{"syntax": "cl", "desc": "清理当前命令上下文。"}],
        "notes": [
            "该命令不会删除当前 staging，也不会影响已载入的数据。",
            "适合在多次操作后重置命令上下文描述信息。",
        ],
        "examples": ["cl"],
        "related": ["status", "discard"],
    },
    "sync-web-schema": {
        "summary": "同步本地 Web schema 缓存，用于刷新 world 映射、特殊类与 feature class 注册。",
        "usage": [{"syntax": "sw", "desc": "同步 web_schema/source 中的 schema 缓存。"}],
        "notes": [
            "优先读取 web_schema/source/data_tool_schema.json。",
            "若该文件不存在，则回退解析 featureFormats.ts。",
            "同步结果会更新 web_schema/cache 下的 world_map.json、special_class_rules.json 等缓存文件。",
        ],
        "examples": ["sw"],
        "related": ["status", "check-env"],
    },
    "push": {
        "summary": "执行完整推送流程：冷归档、清理本地运行期输入、写入 push log、git commit、git pull --rebase、git push。",
        "usage": [{"syntax": "ps", "desc": "执行完整 push。"}],
        "notes": [
            "执行前要求当前 staging 为空，且不存在 blocking 问题。",
            "会将 source_data 与运行日志打包上传到冷仓库 Release。",
            "成功后会清理 source_data、workspace 和 latest reports 的部分运行期内容。",
            "Data 仓库提交阶段会强制确保 push log 进入暂存区与本地提交。",
        ],
        "examples": ["ps"],
        "related": ["push-data", "push-cold", "check-env", "status"],
    },
    "push-data": {
        "summary": "仅执行 Data 仓库 git 提交与推送，不做冷归档。",
        "usage": [{"syntax": "pd", "desc": "执行仅数据仓库推送。"}],
        "notes": [
            "执行前要求当前 staging 为空，且不存在 blocking 问题。",
            "会生成 push log，并通过 git add / commit / pull --rebase / push 提交到 Data 仓库。",
            "适用于冷归档已完成、只需补做 Data 仓库提交的场景。",
        ],
        "examples": ["pd"],
        "related": ["push", "push-cold", "check-env"],
    },
    "push-cold": {
        "summary": "仅执行冷仓库归档上传，不进行 Data 仓库 git 推送。",
        "usage": [{"syntax": "pc", "desc": "执行仅冷归档上传。"}],
        "notes": [
            "执行前要求当前 staging 为空，且不存在 blocking 问题。",
            "会打包 source_data 与运行日志，并上传到 ColdToolArchive 的月度 Release。",
            "成功后会清理本地运行期输入与临时目录，并写入 push log。",
        ],
        "examples": ["pc"],
        "related": ["push", "push-data", "check-env"],
    },
    "check-env": {
        "summary": "检查本地运行环境、git 状态与 GitHub 相关配置，并输出环境检查报告。",
        "usage": [{"syntax": "ce", "desc": "执行环境检查。"}],
        "notes": [
            "建议在首次使用、切换机器或排查 push 失败时执行。",
            "检查结果会写入 reports/latest 环境检查报告。",
        ],
        "examples": ["ce"],
        "related": ["push", "push-data", "push-cold", "sync-web-schema"],
    },
    "exit": {
        "summary": "退出工具；若当前仍有未提交 staging，会保留本次会话日志。",
        "usage": [{"syntax": "ex", "desc": "退出工具。"}, {"syntax": "exit", "desc": "与 ex 相同。"}],
        "notes": [
            "退出前会尝试清理 package zip 解压产生的临时目录。",
            "若当前仍存在未提交 staging，会给出提示但不会自动 discard。",
        ],
        "examples": ["ex", "exit"],
        "related": ["status", "discard"],
    },
}

ALIAS_TO_COMMAND = {v: k for k, v in COMMAND_ALIASES.items()}
VALID_COMMANDS = list(COMMAND_ALIASES.keys())


def resolve_command_name(name):
    key = (name or "").strip()
    if not key:
        return None
    if key in COMMAND_ALIASES:
        return key
    return ALIAS_TO_COMMAND.get(key)
