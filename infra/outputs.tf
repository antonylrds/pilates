output "public_ip" {
  description = "Aponte o registro A de var.domain para este IP."
  value       = oci_core_public_ip.api.ip_address
}

output "ssh" {
  value = "ssh ubuntu@${oci_core_public_ip.api.ip_address}"
}

output "api_url" {
  value = "https://${var.domain}"
}

output "platform_admin_email" {
  value = var.platform_admin_email
}

output "platform_admin_password" {
  description = "tofu output -raw platform_admin_password"
  value       = random_password.platform_admin.result
  sensitive   = true
}
