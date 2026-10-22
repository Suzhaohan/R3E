#!/bin/bash
set -euxo pipefail

cd /home/ibex

git fetch --all --tags
git checkout dd39ec0c91d13d6288e4f131a39d049ccfe32173
git submodule update --init --recursive

apt-get update
apt-get install -y verilator

cat > /etc/profile.d/ibex_pr907_env.sh <<'EOF'
export PATH="/opt/micromamba/envs/ibex/bin:/opt/micromamba/condabin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
EOF

export PATH="/opt/micromamba/envs/ibex/bin:/opt/micromamba/condabin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

git rev-parse HEAD > /tmp/ibex_pr907_baseline_commit.txt
