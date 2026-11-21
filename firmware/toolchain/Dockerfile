# Firmware build toolchain for agent-bench: Arm GNU 12.2.Rel1 (Debian bookworm's gcc-arm-none-eabi is the
# upstream 12.2.Rel1 release), CMake and Ninja, installed from a Debian snapshot on a digest-pinned base image.
# The packages are pinned to exact versions, so the same recipe gives the same compiler and the same ELFs.
#
# Build:  docker build -t agent-bench/arm-gcc:12.2.rel1-1 firmware/toolchain
# (tools/build-firmware.py builds it when the image is missing.)
ARG BASE_IMAGE=debian@sha256:60eac759739651111db372c07be67863818726f754804b8707c90979bda511df
FROM ${BASE_IMAGE}

ARG BASE_IMAGE
ARG DEBIAN_SNAPSHOT=20260623T000000Z
LABEL agent-bench.toolchain.base-image="${BASE_IMAGE}" \
      agent-bench.toolchain.debian-snapshot="${DEBIAN_SNAPSHOT}"

RUN printf '%s\n' \
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} bookworm main" \
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} bookworm-updates main" \
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT} bookworm-security main" \
        > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends \
        gcc-arm-none-eabi=15:12.2.rel1-1 \
        binutils-arm-none-eabi=2.40-2+18+b1 \
        libnewlib-arm-none-eabi=3.3.0-1.3+deb12u1 \
        libstdc++-arm-none-eabi-newlib=15:12.2.rel1-1+23 \
        cmake=3.25.1-1 \
        ninja-build=1.11.1-2~deb12u1 \
        git=1:2.39.5-0+deb12u3 \
        ca-certificates=20230311+deb12u1 \
        python3=3.11.2-1+b1 \
    && rm -rf /var/lib/apt/lists/* \
    # Assert the expected upstream release so a silent distro bump fails the build
    # loudly instead of changing the images.
    && arm-none-eabi-gcc --version | grep -q "12\.2" \
    && cmake --version && ninja --version

# Deterministic builds: pin timestamps (the toolchain cmake file strips absolute paths).
ENV SOURCE_DATE_EPOCH=1700000000

WORKDIR /work
