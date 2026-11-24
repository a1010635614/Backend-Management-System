#!/usr/bin/env bash
# Public linux/amd64 image references verified against the official source on 2026-11-24.
# Load after the same Flow task has completed Docker Login. No credentials belong in this file.
export PYTHON_BUILD_IMAGE=crpi-fdci37tiun8k5nzb.cn-hangzhou.personal.cr.aliyuncs.com/kongqi-blog/base-python@sha256:1475c4f5b6bcb7d35e57661d6f5d7429ec4041275633c15f2b49350ac898276d
export NODE_BUILD_IMAGE=crpi-fdci37tiun8k5nzb.cn-hangzhou.personal.cr.aliyuncs.com/kongqi-blog/base-node@sha256:d20a7b8b4184bf74fe77499b5460a3d69e582bc733d50287e40c3fe791764851
export POSTGRES_TEST_IMAGE=crpi-fdci37tiun8k5nzb.cn-hangzhou.personal.cr.aliyuncs.com/kongqi-blog/base-postgres@sha256:5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e
