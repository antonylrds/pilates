data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

# Imagem Ubuntu 24.04 aarch64 mais recente compatível com a shape A1.
data "oci_core_images" "ubuntu_arm" {
  compartment_id           = var.tenancy_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

resource "random_password" "postgres" {
  length  = 32
  special = false
}

resource "random_password" "platform_admin" {
  length  = 24
  special = false
}

resource "oci_core_instance" "api" {
  compartment_id      = var.tenancy_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "pilates-api"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = var.ocpus
    memory_in_gbs = var.memory_gb
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_arm.images[0].id
    boot_volume_size_in_gbs = var.boot_volume_gb
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = false # o IP público é a reserva abaixo, que sobrevive a recriações da VM
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
      domain               = var.domain
      api_image            = var.api_image
      web_image            = var.web_image
      cors_origins         = jsonencode(var.cors_origins)
      secret_key           = random_password.secret_key.result
      postgres_password    = random_password.postgres.result
      platform_admin_email = var.platform_admin_email
      platform_admin_pass  = random_password.platform_admin.result
      compose              = base64encode(file("${path.module}/deploy/docker-compose.yml"))
    }))
  }

  lifecycle {
    # Trocar a imagem do SO ou o cloud-init recriaria a VM (e apagaria o disco). Mudanças aqui são deliberadas.
    ignore_changes = [source_details[0].source_id, metadata["user_data"]]
  }
}

data "oci_core_vnic_attachments" "api" {
  compartment_id = var.tenancy_ocid
  instance_id    = oci_core_instance.api.id
}

data "oci_core_private_ips" "api" {
  vnic_id = data.oci_core_vnic_attachments.api.vnic_attachments[0].vnic_id
}

resource "oci_core_public_ip" "api" {
  compartment_id = var.tenancy_ocid
  lifetime       = "RESERVED"
  display_name   = "pilates-api"
  private_ip_id  = data.oci_core_private_ips.api.private_ips[0].id
}
