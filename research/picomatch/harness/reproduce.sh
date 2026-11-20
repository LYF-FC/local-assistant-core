#!/usr/bin/env bash
# Experimental, research-only. Run from an empty scratch directory OUTSIDE any MVP working tree:
#   bash reproduce.sh /path/to/empty/scratch
# Needs: node >=22, npm, git, patch, network to registry.npmjs.org and github.com (public, read-only).
set -euo pipefail
W=${1:?scratch dir}; H=$(cd "$(dirname "$0")" && pwd); R=$H/..
mkdir -p "$W"/{v,h,res,patches} && cd "$W"
cp "$H"/*.cjs h/ ; cp "$R"/patches/*.patch patches/
npm pack picomatch@4.0.7 --ignore-scripts >/dev/null
echo "expected archive sha256: 697b463be3cdbd9ffc8f4194fd5019a69ddf95875fb703d78b2b115cc9e740a8"; sha256sum picomatch-4.0.7.tgz
mkdir -p orig && tar xzf picomatch-4.0.7.tgz -C orig
for v in stock pr237 pr238 pr254; do rm -rf v/$v; cp -r orig/package v/$v; [ $v = stock ] || (cd v/$v && patch -p1 --fuzz=0 -s < ../../patches/$v.patch); done
# PR #55 head (closed, historical): git fetch https://github.com/LYF-FC/local-assistant-core refs/pull/55/head
#   then: git show FETCH_HEAD:frontend/vendor/picomatch/picomatch-4.0.7-upstream-254.tgz > p.tgz (sha256 30d3e22f...9543) -> extract to v/pr55
for v in stock pr254 pr237 pr238; do node --max-old-space-size=2500 h/run.cjs v/$v res/$v.json; done
node h/compare.cjs res pr254 pr237 pr238
node h/redos_driver.cjs res/redos.json stock pr254 pr237 pr238   # 3 s wall-clock kill + 2.5 GB ulimit per child
