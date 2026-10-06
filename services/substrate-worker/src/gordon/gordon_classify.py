#!/usr/bin/env python3
"""Classify one Gordon windows.csv (CWND-vs-RTT) into a CCA label + JSON vote.

Thin wrapper over Gordon's own rule-based classifier (Scripts/tcpClassify.py).
Emits the Fig-13-style result: {"cca": <label>, "windows_csv": ...}.
"""

import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "Scripts"))
import tcpClassify  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print("usage: gordon_classify.py <windows.csv>", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1]
    try:
        label = tcpClassify.classify(path)
    except Exception as e:  # noqa: BLE001
        label = f"error:{e}"
    out = {"tool": "gordon", "windows_csv": path, "cca": label}
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    main()
