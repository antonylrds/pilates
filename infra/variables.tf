variable "region" {
  description = "Região OCI (a home region da conta; o Always Free só existe nela)."
  type        = string
}

variable "tenancy_ocid" {
  description = "OCID da tenancy (compartimento raiz)."
  type        = string
}

variable "ssh_public_key" {
  description = "Chave pública SSH autorizada na VM (usuário ubuntu)."
  type        = string
}

variable "ssh_allowed_cidr" {
  description = "CIDR com acesso SSH à VM. Use o seu IP (x.x.x.x/32); evite 0.0.0.0/0."
  type        = string
}

variable "domain" {
  description = "Domínio do app (front + API na mesma origem), com registro A para o public_ip. O Caddy emite o HTTPS dele. Vazio = <ip>.sslip.io (DNS gratuito)."
  type        = string
  default     = ""
}

variable "api_image" {
  description = "Imagem da API (arm64) no registry. Ex.: ghcr.io/usuario/pilates-api:latest"
  type        = string
}

variable "web_image" {
  description = "Imagem do front (arm64, Caddy + build estático) no registry. Ex.: ghcr.io/usuario/pilates-web:latest"
  type        = string
}

variable "cors_origins" {
  description = "Origens extras permitidas (CORS). Vazio: front e API ficam na mesma origem. Útil p/ o app mobile ou dev local apontando para a API."
  type        = list(string)
  default     = []
}

variable "platform_admin_email" {
  description = "E-mail do usuário da plataforma (cria estúdios)."
  type        = string
}

variable "ocpus" {
  description = "OCPUs da VM A1. Always Free atual: 2 OCPU / 12 GB (confira em docs.oracle.com/iaas/Content/FreeTier/resourceref.htm)."
  type        = number
  default     = 2
}

variable "memory_gb" {
  description = "Memória da VM A1 em GB (Always Free atual: 12)."
  type        = number
  default     = 12
}

variable "boot_volume_gb" {
  description = "Disco de boot em GB (Always Free: 200 GB no total entre volumes)."
  type        = number
  default     = 100
}
