#!/bin/bash

# Preserve the dynamic /dev population provided by the deprecated balenalib
# base-image entrypoint. This requires the privileged container configuration
# used by the media-player service on balenaOS.

start_udev() {
  local temporary_mount=/tmp/_balena_dev_check
  local replacement_dev=/tmp/_balena_dev

  if [[ "${UDEV,,}" != "1" && "${UDEV,,}" != "true" && "${UDEV,,}" != "on" ]]; then
    return
  fi

  mkdir -p "$temporary_mount"
  if ! mount -t devtmpfs none "$temporary_mount" >/dev/null 2>&1; then
    rmdir "$temporary_mount"
    echo "[entrypoint] Unable to populate /dev: the container is not privileged"
    return
  fi
  umount "$temporary_mount"
  rmdir "$temporary_mount"

  mkdir -p "$replacement_dev"
  mount -t devtmpfs none "$replacement_dev"
  mkdir -p "$replacement_dev"/{shm,mqueue,pts}
  mount --move /dev/shm "$replacement_dev/shm"
  mount --move /dev/mqueue "$replacement_dev/mqueue"
  mount --move /dev/pts "$replacement_dev/pts"
  if [[ -e /dev/console ]]; then
    touch "$replacement_dev/console"
    mount --move /dev/console "$replacement_dev/console"
  fi
  umount /dev >/dev/null 2>&1 || true
  mount --move "$replacement_dev" /dev
  ln -sf /dev/pts/ptmx /dev/ptmx

  mkdir -p /sys/kernel/debug
  if ! mountpoint -q /sys/kernel/debug; then
    mount -t debugfs nodev /sys/kernel/debug || true
  fi

  if unshare --net /lib/systemd/systemd-udevd --daemon >/dev/null 2>&1; then
    udevadm trigger >/dev/null 2>&1
    echo "[entrypoint] udev started and device discovery triggered"
  else
    echo "[entrypoint] WARNING: unable to start udevd"
  fi
}

start_udev
exec "$@"
