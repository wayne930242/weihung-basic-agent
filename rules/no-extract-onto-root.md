---
description: "Agents never extract an archive onto /"
condition:
  - '(?:^|[\n;(`]|(?<!\\)[|&]|\b(?:then|do|else)\s)\s*(?:(?:sudo|nohup|time)\s+)*tar(?=[^\n;&|]*\s(?:-?[a-zA-Z]*x[a-zA-Z]*|--extract)(?:\s|$))(?=[^\n;&|]*\s(?:-C\s*|--directory[=\s])/(?:\s|$|[;&|]))'
  - '(?:^|[\n;(`]|(?<!\\)[|&])\s*cd\s+/\s*(?:&&|;)[^\n]*\btar\s'
  - '(?:^|[\n;(`]|(?<!\\)[|&])\s*(?:sudo\s+)?dpkg-deb\s+(?:-x|-X|--extract|--vextract)\s+\S+\s+/(?:\s|$|[;&|])'
  - '(?:^|[\n;(`]|(?<!\\)[|&])\s*(?:sudo\s+)?unzip\b[^\n;&|]*\s-d\s+/(?:\s|$|[;&|])'
scope: "tool:bash"
repeatMode: after-gap
repeatGap: 1
lesson: never extract any archive directly onto /
blocks:
  - tar -xpf /tmp/pkg/data.tar.xz -C /
  - sudo tar --extract -f a.tar --directory=/
  - cd / && tar xzf /tmp/x.tgz
  - dpkg-deb -x /tmp/dpkg.deb /
  - unzip /tmp/a.zip -d /
allows:
  - tar -xpf /tmp/pkg/data.tar.xz -C /tmp/pkg/root
  - sudo tar -C / -czf /tmp/etc-backup.tgz etc
  - dpkg-deb -x /tmp/dpkg.deb /tmp/dpkg-root
  - grep -n "tar -xpf" notes.md
---

Do not extract an archive onto `/`: unpacking a dpkg package there replaced the usrmerge `/lib` and `/sbin` symlinks with real directories, and a production host could no longer start any process.

Extract into a fresh temporary directory, inspect it, and copy only the files you need to their destinations.
