#!/bin/bash
set -e

INST_IMG="$1"
echo $INST_IMG
SIZE="${SIZE:-25G}"

if [ "$EUID" -ne 0 ]; then
	echo "Please use sudo to run this script"
	exit 1
fi

help () {
	echo "usage: $0 [installer image] [output disk image]"
}

if [ -z "$INST_IMG" ]; then
	help
	exit 1
fi
echo "test1"
os_partition() {
    while read -r name fstype mountpoint; do
        if [ "$fstype" = "ext4" ]; then
            if  [ "$mountpoint" = "/" ]; then
                echo "/dev/$name"
                return
            fi
        fi
    done < <(lsblk -n -l -o NAME,FSTYPE,MOUNTPOINT)
    exit 1
}

get_partition() {
  echo "test2"
  BD=""
  ESP_PART=""
  RP_PART=""
  PART=$(os_partition)
  echo $PART 
 
  if echo "$PART" | grep -q "sd"; then
    BD=$(echo "$PART" | cut -c6-8)
    ESP_PART="/dev/${BD}1"
    RP_PART="/dev/${BD}2"
    echo "Find boot disk ${BD}"
    echo "Find RP ${RP_PART}"
  elif echo "$PART" | grep -q "mmc"; then
    BD=$(echo "$PART" | cut -c6-12)
    ESP_PART="/dev/${BD}p1"
    RP_PART="/dev/${BD}p2"
    echo "Find boot disk ${BD}"
    echo "Find RP ${RP_PART}"
  elif echo "$PART" | grep -q "nvme"; then
    BD=$(echo "$PART" | cut -c6-12)
    ESP_PART="/dev/${BD}p1"
    RP_PART="/dev/${BD}p2"
    echo "Find boot disk ${BD}"
    echo "Find RP ${RP_PART}"
  elif echo "$PART" | grep -q "md"; then
    BD=$(echo "$PART" | cut -c6-10)
    ESP_PART="/dev/${BD}p1"
    RP_PART="/dev/${BD}p2"
    echo "Find boot disk ${BD}"
    echo "Find RP ${RP_PART}"
  else
    echo "Fail to find boot disk !!!"
    exit 1
  fi
}
get_partition

#clean RP and ESP partition content
mount $RP_PART  /mnt
rm -rf /mnt/*
umount /mnt


MOUNT_POINT=$(findmnt -n -o TARGET "$ESP_PART")

if [ -z "$MOUNT_POINT" ]; then
    echo "EFI partition is not mounted. Mounting to /mnt..."
    sudo mount "$ESP_PART" /mnt
    MOUNT_POINT="/mnt"
else
    echo "EFI partition is already mounted at $MOUNT_POINT"
fi

echo "Cleaning up $MOUNT_POINT..."
sudo rm -rf "$MOUNT_POINT"/*

# If we mounted it manually, unmount it
if [ "$MOUNT_POINT" = "/mnt" ]; then
    sudo umount /mnt
    echo "Umounted /mnt"
fi

echo "ESP partition ($ESP_PART) has been cleaned."

#deploy image to RP and ESP
WORKDIR=$(mktemp -d)
defer_2 () {
	rm -rf "$WORKDIR"
}
trap defer_2 EXIT

ESP_DIR="$WORKDIR/esp"
RP_DIR="$WORKDIR/rp"
INST_IMG_DIR="$WORKDIR/inst_img"
mkdir -p "$ESP_DIR" "$RP_DIR" "$INST_IMG_DIR"

mount -o loop "$INST_IMG" "$INST_IMG_DIR"
defer_3 () {
	umount "$INST_IMG_DIR"
	defer_2
}
trap defer_3 EXIT

mount "$ESP_PART" "$ESP_DIR"
defer_4 () {
	umount "$ESP_DIR"
	defer_3
}
trap defer_4 EXIT

mount "$RP_PART" "$RP_DIR"
defer_5 () {
	umount "$RP_DIR"
	defer_4
}
trap defer_5 EXIT

rsync -av --no-links "$INST_IMG_DIR"/ "$RP_DIR"
cp -rv "$RP_DIR/EFI" "$ESP_DIR/"

#change boot entry
mount $RP_PART  /mnt
cp -r ./reset-stress /mnt/cloud-configs
reset_partuuid=$(lsblk -n -o PARTUUID "$RP_PART")
echo "Update the grub.cfg to boot from the reset partition"
sed -i "s/reset-media/reset-stress autoinstall rp-partuuid=${reset_partuuid}/" /mnt/boot/grub/grub.cfg
sed -i "s/timeout=-1/timeout=3/" /mnt/boot/grub/grub.cfg
umount /mnt




