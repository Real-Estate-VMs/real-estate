terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "0.8.3"
    }
  }
}

provider "libvirt" {
  uri = "qemu:///system"
}

locals {
  vms = ["generator", "processing", "bigdata", "monitoring"]

  vm_config = {
    generator  = { memory = 1024, vcpu = 1 }
    processing = { memory = 2048, vcpu = 2 }
    bigdata    = { memory = 1024, vcpu = 1 }
    monitoring = { memory = 2048, vcpu = 2 }
  }
}

resource "libvirt_volume" "ubuntu_base" {
  name   = "ubuntu-24.04-base.qcow2"
  pool   = "default"
  source = "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
  format = "qcow2"
}

resource "libvirt_volume" "vm_disk" {
  count = length(local.vms)

  name           = "${local.vms[count.index]}.qcow2"
  pool           = "default"
  base_volume_id = libvirt_volume.ubuntu_base.id
  format         = "qcow2"
  size           = 10737418240
}

resource "libvirt_cloudinit_disk" "init" {
  count = length(local.vms)

  name = "${local.vms[count.index]}-cloudinit.iso"
  pool = "default"

  user_data = templatefile("${path.module}/cloud_init.cfg", {
    hostname = local.vms[count.index]
    ssh_key  = trimspace(file(pathexpand("~/.ssh/devops_lab.pub")))
  })
}

resource "libvirt_domain" "vm" {
  count = length(local.vms)

  name   = local.vms[count.index]
  memory = local.vm_config[local.vms[count.index]].memory
  vcpu   = local.vm_config[local.vms[count.index]].vcpu

  cloudinit = libvirt_cloudinit_disk.init[count.index].id

  network_interface {
    network_name   = "default"
    wait_for_lease = true
  }

  disk {
    volume_id = libvirt_volume.vm_disk[count.index].id
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }
}

output "ips" {
  value = {
    for i, vm in libvirt_domain.vm : local.vms[i] => try(vm.network_interface[0].addresses[0], "pending")
  }
}
