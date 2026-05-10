# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

# toolchain-quickjs — Nanvix GCC toolchain + host GCC for QuickJS
# cross-compilation.  Published as ghcr.io/nanvix/toolchain-quickjs.

FROM ghcr.io/nanvix/toolchain-gcc:sha-34a3641

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
    && rm -rf /var/lib/apt/lists/*
