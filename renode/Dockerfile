# Reference emulator of the benchmark: official Antmicro Renode v1.17.0 (portable .NET Linux build).
# It runs as an external process in this container only: nothing of it is linked into, vendored by or
# redistributed with this repository (Renode is BSD-3-Clause).
#
# Build:  docker build -t agent-bench/renode:1.17.0-1 renode
# renode/renode.lock.json records the SHA-256 of the release archive and installed binary;
# tools/run_renode.py and tools/run.py refuse an image whose binary differs.
ARG BASE_IMAGE=debian@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f
FROM ${BASE_IMAGE}

ARG BASE_IMAGE
ARG DEBIAN_SNAPSHOT=20261026T000000Z
ARG RENODE_VERSION=1.17.0
ARG RENODE_ARCHIVE_SHA256=4ba7c68b59e2447f188ef4b4b112fcccd2802582c460beedceb63b84e5605a5f

LABEL agent-bench.renode.base-image="${BASE_IMAGE}" \
      agent-bench.renode.debian-snapshot="${DEBIAN_SNAPSHOT}" \
      agent-bench.renode.version="${RENODE_VERSION}"

RUN printf '%s\n' \
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} trixie main" \
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} trixie-updates main" \
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT} trixie-security main" \
        > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl libicu76 libssl3t64 zlib1g python3 \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fSL -o /tmp/renode.tar.gz \
       "https://github.com/renode/renode/releases/download/v${RENODE_VERSION}/renode-${RENODE_VERSION}.linux-portable.tar.gz" \
    && echo "${RENODE_ARCHIVE_SHA256}  /tmp/renode.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/renode \
    && tar -xzf /tmp/renode.tar.gz --strip-components=1 -C /opt/renode \
    && rm -f /tmp/renode.tar.gz \
    && ln -s /opt/renode/renode /usr/local/bin/renode \
    && renode --version \
    && printf '%s\n' \
        'mach create "warm"' \
        'machine LoadPlatformDescription @platforms/boards/stm32f4_discovery.repl' \
        'quit' \
        > /tmp/warm.resc \
    && renode --disable-xwt --plain --port -2 -e "include @/tmp/warm.resc" </dev/null \
    && rm -f /tmp/warm.resc
