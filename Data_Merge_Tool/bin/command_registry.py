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

ALIAS_TO_COMMAND = {v: k for k, v in COMMAND_ALIASES.items()}
VALID_COMMANDS = list(COMMAND_ALIASES.keys())
