# Reference emulator of the benchmark: upstream QEMU system mode (qemu-system-arm) as built by Debian 13.
# It runs as an external process in this container only: nothing of it is linked into, vendored by or
# redistributed with this repository (QEMU is GPL-2.0).
#
# Build:  docker build -t agent-bench/qemu-system-arm:10.0.13-1 qemu
# qemu/qemu-system-arm.lock.json records the SHA-256 of the installed binary; tools/run.py refuses an
# image whose binary differs.
ARG BASE_IMAGE=debian@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f
FROM ${BASE_IMAGE}

ARG BASE_IMAGE
ARG DEBIAN_SNAPSHOT=20261026T000000Z
LABEL agent-bench.qemu.base-image="${BASE_IMAGE}" \
      agent-bench.qemu.debian-snapshot="${DEBIAN_SNAPSHOT}"

RUN printf '%s\n' \
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} trixie main" \
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} trixie-updates main" \
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT} trixie-security main" \
        > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends qemu-system-arm=1:10.0.13+ds-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/* \
    && qemu-system-arm --version | head -1 \
    && qemu-system-arm -machine help | grep -E "^olimex-stm32-h405 "
