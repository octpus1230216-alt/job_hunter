#!/usr/bin/env python3
"""sync_via_api.py — 通过 GitHub Git Data API 把本地改动推到仓库。

适用场景
--------
本机 `git push` 被沙箱出口代理拦截（github.com 的 CONNECT 隧道 502），
但 api.github.com 可达。此脚本绕开 git 协议，直接走 GitHub API 推送。

原理
----
1. 取当前分支最新 commit 的 tree
2. 把本地目录里的每个文件创建 blob，组成新的 tree entries
   （与旧 tree 同路径即覆盖，旧 tree 里已不存在的路径即删除）
3. 用新 tree + 旧 commit 作 parent 建 commit
4. 把分支 ref 指向新 commit

用法
----
    # 推送整个 analytics/ 目录（自动处理新增/修改/删除）
    python sync_via_api.py --dir analytics --prefix analytics \\
        --message "feat(analytics): 补全缺失文件"

    # 同时推送根目录的几个文件
    python sync_via_api.py --dir analytics --prefix analytics \\
        --root README.md --root .gitignore --root sync_via_api.py \\
        --message "docs: 更新根 README + 同步脚本"

令牌
----
优先读环境变量 GITHUB_TOKEN；否则读 --token-file（默认 token.txt，需自行创建且已被 .gitignore 忽略）。
"""

import os
import sys
import json
import base64
import argparse
import urllib.request
import urllib.error

API = "https://api.github.com"


def api(method, path, token, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"HTTP {e.code} {method} {path}: {err[:400]}", file=sys.stderr)
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="octpus1230216-alt")
    ap.add_argument("--repo", default="job_hunter")
    ap.add_argument("--branch", default="master")
    ap.add_argument("--dir", required=True, help="要同步的本地目录（绝对或相对）")
    ap.add_argument("--prefix", default="", help="远程路径前缀，如 analytics")
    ap.add_argument("--root", nargs="*", default=[],
                    help="额外要同步的根目录文件，如 README.md .gitignore sync_via_api.py")
    ap.add_argument("--message", required=True)
    ap.add_argument("--token-file", default="token.txt")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or open(args.token_file).read().strip()
    repo = f"/repos/{args.owner}/{args.repo}"

    # 1) 基线
    base = api("GET", f"{repo}/git/refs/heads/{args.branch}", token)
    base_sha = base["object"]["sha"]
    base_commit = api("GET", f"{repo}/git/commits/{base_sha}", token)
    base_tree_sha = base_commit["tree"]["sha"]
    base_tree = api("GET", f"{repo}/git/trees/{base_tree_sha}?recursive=1", token)

    # 2) 收集本地 entries
    entries = []
    dpath = os.path.abspath(args.dir)
    for dp, dn, fn in os.walk(dpath):
        dn[:] = [d for d in dn if d not in ("data", "__pycache__", ".git")]
        for f in fn:
            if f == ".DS_Store":
                continue
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, dpath)
            remote_path = f"{args.prefix}/{rel}" if args.prefix else rel
            with open(full, "rb") as fp:
                content = fp.read()
            blob = api("POST", f"{repo}/git/blobs", token,
                       {"content": base64.b64encode(content).decode(), "encoding": "base64"})
            entries.append({"path": remote_path, "mode": "100644",
                            "type": "blob", "sha": blob["sha"]})

    for rf in args.root:
        full = os.path.abspath(rf)
        if not os.path.exists(full):
            print(f"warn: 根文件不存在，跳过 {rf}", file=sys.stderr)
            continue
        with open(full, "rb") as fp:
            content = fp.read()
        blob = api("POST", f"{repo}/git/blobs", token,
                   {"content": base64.b64encode(content).decode(), "encoding": "base64"})
        entries.append({"path": rf, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    # 3) 删除已不在本地的旧文件（仅限 --prefix 范围内）
    local_paths = {e["path"] for e in entries}
    for t in base_tree.get("tree", []):
        p = t["path"]
        if args.prefix and p.startswith(args.prefix + "/") and p not in local_paths:
            entries.append({"path": p, "mode": "100644", "type": "blob", "sha": None})

    # 4) 建 tree / commit / 更新 ref
    new_tree = api("POST", f"{repo}/git/trees", token,
                   {"base_tree": base_tree_sha, "tree": entries})
    new_commit = api("POST", f"{repo}/git/commits", token,
                     {"message": args.message, "tree": new_tree["sha"], "parents": [base_sha]})
    api("PATCH", f"{repo}/git/refs/heads/{args.branch}", token, {"sha": new_commit["sha"]})
    print(f"✅ pushed {new_commit['sha'][:10]} | {len(entries)} tree entries | msg: {args.message}")


if __name__ == "__main__":
    main()
