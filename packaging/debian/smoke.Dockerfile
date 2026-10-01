ARG UBUNTU_VERSION
FROM ubuntu:${UBUNTU_VERSION}

ENV DEBIAN_FRONTEND=noninteractive TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl git gcc make pkg-config xz-utils \
        libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
        libffi-dev liblzma-dev uuid-dev \
        python3 procps util-linux xvfb xauth x11-apps ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN curl --fail --location --proto '=https' --tlsv1.2 \
        https://www.python.org/ftp/python/3.14.7/Python-3.14.7.tar.xz \
        --output /tmp/Python-3.14.7.tar.xz \
    && echo '3b48dac8fb59f62eaa67ac83c1eb12bda1b7a08406dd286e252c11a66be27f81  /tmp/Python-3.14.7.tar.xz' | sha256sum --check --strict \
    && tar -xf /tmp/Python-3.14.7.tar.xz -C /tmp \
    && cd /tmp/Python-3.14.7 \
    && ./configure --prefix=/opt/gx-smoke-python --with-ensurepip=no \
    && make -j2 \
    && make altinstall \
    && /opt/gx-smoke-python/bin/python3.14 -c 'import bz2, ctypes, hashlib, lzma, ssl, tomllib; import sys; assert sys.version_info[:3] == (3, 14, 7)' \
    && rm -rf /tmp/Python-3.14.7 /tmp/Python-3.14.7.tar.xz

ENV GX_SMOKE_PYTHON=/opt/gx-smoke-python/bin/python3.14
