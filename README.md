Codename: Punch Kicker
======================

![Codename: Punch Kicker](PunchKicker.png)

Punchkicker is a simple, opinionated self-initialization kickstart system for Alpine Linux, especially on AWS, and especialy for cluster nodes (eg, k3s on Alipine, aka "Kubical").

It works by having a small init script (in the case of AWS, provided as user-data to be executed by tiny-ec2-init), which mounts an NFS (EFS on AWS) filesystem and executes the initialization scripts from there.

It's very much a work in progress, and is currently in flux between it's previous main focus for settig up Nomad-based clusters to K3s clusters.

I guarantee that it is at least as polished an professional as Abed's Punch Kicker costume.