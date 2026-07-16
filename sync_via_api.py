#!/usr/bin/env python3
"""sync_via_api.py — 通过 GitHub Git Data API 把本地改动推到仓库。

适用场景
--------
本机 `git push` 被沙箱出口代理拦截（github.com 的 CONNECT 隧道 502），
但 api.github.com 可达。此脚本绕开 git 协议，直接走 GitHub API 推送。

原理（稳健版）
------------
1. 取当前分支最新 commit 的完整 tree（recursive），建成 path -> entry 字典
   ——这样会保留仓库里其它文件（主项目 app.py / pages/ 等），不误删
2. 用本地目录里的文件覆盖/新增对应 entry（analytics/ 前缀下）
3. 用 --root 指定的根目录文件覆盖/新增对应 entry
4. 删除本地已不存在的 analytics/ 旧文件（--root 的删除一般不处理，极少需要）
5. 用「完整 entry 列表」建新 tree（不带 base_tree，避免同路径不替换的坑）
6. 以旧 commit 为 parent 建 commit，更新分支 ref

用法
----
    # 推送整个 analytics/ 目录（自动处理新增/修改/删除）
    python sync_via_api.py --dir analytics --prefix analytics \\
        --message "feat(analytics): ..."

    # 同时推送根目录的几个文件（如更新 README / .gitignore / 本脚本）
    python sync_via_api.py --dir analytics --prefix analytics \\
        --root README.md --root .gitignore --root sync_via_api.py \\
        --message "docs: ..."

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


def make_blob(repo, token, content):
    return api("POST", f"{repo}/git/blobs", token,
               {"content": base64.b64encode(content).decode(), "encoding": "base64"})["sha"]


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

    # 1) 基线完整 tree
    base = api("GET", f"{repo}/git/refs/heads/{args.branch}", token)
    base_sha = base["object"]["sha"]
    base_commit = api("GET", f"{repo}/git/commits/{base_sha}", token)
    base_tree_sha = base_commit["tree"]["sha"]
    base_tree = api("GET", f"{repo}/git/trees/{base_tree_sha}?recursive=1", token)

    entries = {t["path"]: {"path": t["path"], "mode": t["mode"],
                           "type": t["type"], "sha": t["sha"]}
               for t in base_tree.get("tree", [])}

    # 2) 覆盖/新增 analytics/ 下文件
    local_analytics = set()
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
            sha = make_blob(repo, token, content)
            entries[remote_path] = {"path": remote_path, "mode": "100644",
                                    "type": "blob", "sha": sha}
            local_analytics.add(remote_path)

    # 3) 覆盖/新增根目录文件
    for rf in args.root:
        full = os.path.abspath(rf)
        if not os.path.exists(full):
            print(f"warn: 根文件不存在，跳过 {rf}", file=sys.stderr)
            continue
        with open(full, "rb") as fp:
            content = fp.read()
        sha = make_blob(repo, token, content)
        entries[rf] = {"path": rf, "mode": "100644", "type": "blob", "sha": sha}

    # 4) 删除本地已不存在的 analytics/ 旧文件
    for p in list(entries):
        if args.prefix and p.startswith(args.prefix + "/") and p not in local_analytics:
            del entries[p]

    # 5) 用完整 entry 列表建新 tree（不带 base_tree，确保同路径必替换）
    tree_list = list(entries.values())
    new_tree = api("POST", f"{repo}/git/trees", token, {"tree": tree_list})
    new_commit = api("POST", f"{repo}/git/commits", token,
                     {"message": args.message, "tree": new_tree["sha"], "parents": [base_sha]})
    api("PATCH", f"{repo}/git/refs/heads/{args.branch}", token, {"sha": new_commit["sha"]})
    print(f"✅ pushed {new_commit['sha'][:10]} | {len(tree_list)} tree entries | msg: {args.message}")


if __name__ == "__main__":
    main()
