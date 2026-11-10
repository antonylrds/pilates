terraform {
  required_version = ">= 1.8"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Estado local por padrão. Em equipe, mova para um bucket do OCI Object Storage (backend "s3" compatível)
  # e habilite a criptografia de estado do OpenTofu (o estado guarda SECRET_KEY e senhas).
}

provider "oci" {
  region = var.region
  # Autenticação: ~/.oci/config (perfil DEFAULT) ou variáveis OCI_*. Veja o README.
}
