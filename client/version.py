#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CK3-DirectLAN 开源版版本号定义"""

import os
import sys

DEFAULT_VERSION = "1.0.0"


def get_app_version() -> str:
    try:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        v_file = os.path.join(base_dir, "version.txt")
        if os.path.isfile(v_file):
            with open(v_file, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
    except Exception:
        pass
    return DEFAULT_VERSION


APP_VERSION = get_app_version()
