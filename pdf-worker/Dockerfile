FROM debian:trixie-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev libseccomp-dev && rm -rf /var/lib/apt/lists/*
COPY guard.c /src/guard.c
RUN gcc -O2 -Wall -Wextra -Werror -D_FORTIFY_SOURCE=2 -fstack-protector-strong -Wl,-z,relro,-z,now /src/guard.c -lseccomp -o /pdf-guard

FROM python:3.12-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils libseccomp2 && rm -rf /var/lib/apt/lists/* && groupadd --gid 10001 parser && useradd --uid 10001 --gid parser --no-create-home parser && install -d -m 0700 -o parser -g parser /run/butler-pdf && dpkg-query -W > /opt/parser-packages.txt
COPY --from=build /pdf-guard /usr/local/bin/pdf-guard
COPY worker.py /opt/worker.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
CMD ["python", "/opt/worker.py"]
