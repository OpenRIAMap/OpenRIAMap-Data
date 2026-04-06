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

ALIAS_TO_COMMAND = {v: k for k, v in COMMAND_ALIASES.items()}
VALID_COMMANDS = list(COMMAND_ALIASES.keys())
