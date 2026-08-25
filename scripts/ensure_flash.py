#!/usr/bin/env python3
"""确保 Horizon config 模型固定在 deepseek-v4-flash。

背景（2026-08-21）：用户因 DeepSeek Pro 提价太贵，决定早报固定用 flash。
原 cron 流程「切 flash → 跑 → 切回 pro」导致 agent 崩溃时模型卡在 flash/pro 不一致。
此脚本幂等地把 model 设为 flash，cron 每次运行前调用一次，崩溃也不影响后续。

用法: python3 scripts/ensure_flash.py
退出码: 0 = 已是 flash; 1 = 被改回 flash（原值非 flash）
"""
import json
import os
import sys

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "config.json")
TARGET = "deepseek-v4-flash"


def main() -> int:
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    current = cfg.get("ai", {}).get("model")
    if current == TARGET:
        print(f"OK: model 已是 {TARGET}")
        return 0
    cfg.setdefault("ai", {})["model"] = TARGET
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"FIXED: model 从 {current} 切回 {TARGET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
