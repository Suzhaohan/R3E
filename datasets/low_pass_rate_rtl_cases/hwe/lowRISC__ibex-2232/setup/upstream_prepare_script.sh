#!/bin/bash
set -euo pipefail

cd /home/ibex
git checkout 667fd20d2ede51caececccbcbda3652074424ce2
git submodule sync --recursive
git submodule update --init --recursive

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  git \
  make \
  g++ \
  flex \
  bison \
  libelf-dev \
  zlib1g-dev \
  wget \
  xz-utils

set -a
source ci/vars.env
set +a

mkdir -p /tools/verilator
chmod 777 /tools/verilator
cd /tmp
rm -f "verilator-${VERILATOR_VERSION}.tar.gz"
wget -q "https://storage.googleapis.com/verilator-builds/verilator-${VERILATOR_VERSION}.tar.gz"
tar -C /tools/verilator -xzf "verilator-${VERILATOR_VERSION}.tar.gz"

cat > /etc/profile.d/ibex-tools-path.sh <<EOF
export PATH=/tools/verilator/${VERILATOR_VERSION}/bin:\$PATH
EOF

export PATH="/tools/verilator/${VERILATOR_VERSION}/bin:$PATH"

cd /home/ibex
git rev-parse HEAD > /tmp/ibex_base_commit
