# syntax=docker/dockerfile:1
#
# Runtime image for the KiCAD MCP server.
#
# The official kicad/kicad image already has what the *tools* need -- kicad-cli
# 9.0.9 and a pcbnew-capable Python 3.11. It does not have what the *server*
# needs:
#
#   - Node.js                       -- the MCP server itself
#   - the packages in requirements.txt  -- the Python command layer
#   - a JRE 21+                     -- the autoroute tool shells out to Freerouting
#   - freerouting.jar               -- ditto
#
# This layer adds all four.
#
# Build:
#   docker build -t kicad-mcp:9.0 .
#
# The server code is not baked in -- it is bind-mounted at run time (see
# .mcp.json), so edits to dist/ take effect without a rebuild. Rebuild only
# when requirements.txt, the versions below, or the base image change.

# Node 20, borrowed from the official image rather than installed from
# NodeSource. Both bases are Debian bookworm, so the copied binary links against
# the glibc already present in the KiCad image.
FROM node:20-bookworm-slim AS node

# Debian bookworm does not ship a JDK new enough for Freerouting (its OpenJDK
# tops out at 17), so take the JRE from Temurin instead of mixing in a
# third-party apt repo. The KiCad base is bookworm, so the glibc matches.
#
# The version must match what the pinned FREEROUTING_VERSION was compiled for,
# not the "Java 21+" the release notes have claimed since 2.x: v2.4.1 is built
# by Temurin 25 and its classes are major version 69, which a 21 JVM refuses
# with UnsupportedClassVersionError. `check_freerouting` reads the requirement
# out of the JAR, so it reports the mismatch rather than a bare failure.
FROM eclipse-temurin:25-jre AS jre

FROM kicad/kicad:9.0

# Asset naming changed at v2.1: releases up to 2.0.1 published
# `freerouting-<v>-executable.jar`, later ones just `freerouting-<v>.jar`.
ARG FREEROUTING_VERSION=2.4.1

USER root

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

COPY --from=jre /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=/opt/java/openjdk/bin:$PATH

# Debian 12 marks the system Python as externally managed, so the requirements
# go into a venv. The base image has the `venv` module but neither the
# ensurepip bootstrap nor pip itself, so both packages are needed -- without
# python3-venv, `python3 -m venv` fails with "ensurepip is not available".
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-venv python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --system-site-packages is required, not cosmetic: it is how the venv still
# sees pcbnew, wxPython and numpy out of KiCad's own dist-packages.
RUN python3 -m venv --system-site-packages /opt/kicad-mcp-venv

COPY requirements.txt /tmp/requirements.txt
RUN /opt/kicad-mcp-venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# The autorouter looks here by default (see DEFAULT_FREEROUTING_JAR in
# python/commands/freerouting.py); FREEROUTING_JAR overrides it.
RUN mkdir -p /home/kicad/.kicad-mcp \
    && curl -fsSL -o /home/kicad/.kicad-mcp/freerouting.jar \
        "https://github.com/freerouting/freerouting/releases/download/v${FREEROUTING_VERSION}/freerouting-${FREEROUTING_VERSION}.jar" \
    && chown -R kicad:kicad /home/kicad/.kicad-mcp

# The base image runs as the unprivileged `kicad` user (uid 1000), which is what
# makes the bind-mounted workspace writable without --user gymnastics. The
# .kicad-mcp directory above is owned by root; this drops the jar to a mode the
# kicad user can still read.
RUN chmod 755 /home/kicad/.kicad-mcp && chmod 644 /home/kicad/.kicad-mcp/freerouting.jar

USER kicad

# Sanity checks. Fail the build rather than the first tool call if the venv
# cannot see KiCad's libraries.
# `skip` is the import name of the kicad-skip distribution.
RUN /opt/kicad-mcp-venv/bin/python -c "import pcbnew, sexpdata, skip, fitz, cairosvg, PIL; print('pcbnew', pcbnew.GetBuildVersion())" \
    && java -version

# The jar is checked by class-file version, not merely for existence. A JVM
# older than the class version refuses every class with
# UnsupportedClassVersionError, and it does so at load time in ~0.1s -- which
# is how an image shipping a Java 21 JRE beside a Java 25 jar passed this
# check and then failed every routing attempt. Comparing the numbers makes
# that mismatch a build failure.
RUN set -eu; \
    jar=/home/kicad/.kicad-mcp/freerouting.jar; \
    test -s "$jar"; \
    need=$(/opt/kicad-mcp-venv/bin/python -c \
        "import zipfile; print(int.from_bytes(zipfile.ZipFile('$jar').read('app/freerouting/Freerouting.class')[6:8], 'big') - 44)"); \
    have=$(java -version 2>&1 | awk -F'"' '/ version /{print $2}' | cut -d. -f1); \
    echo "freerouting.jar needs Java $need; this JRE is $have"; \
    [ "$have" -ge "$need" ]; \
    echo "freerouting.jar present and loadable"
