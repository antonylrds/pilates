# Infraestrutura (OpenTofu + Oracle Cloud Always Free)

Provisiona uma VM ARM (`VM.Standard.A1.Flex`, Ubuntu 24.04) que roda, via Docker Compose:
**Caddy** (HTTPS automático) → **API** (FastAPI) → **Postgres 16**. Os arquivos dos alunos ficam num volume Docker.

```
Internet ─443→ Caddy ─→ api:8000 ─→ db:5432 (não exposto)
```

O Tofu cria: VCN, subnet pública, security list (80/443 abertos, SSH só para o seu IP), a VM e um **IP público
reservado** (sobrevive a recriações da VM). O cloud-init instala o Docker e sobe a stack com segredos gerados
pelo próprio Tofu. Os bancos dos estúdios (`pilates_<slug>`) são criados pela aplicação, não pelo Tofu.

## Pré-requisitos

1. Conta Oracle Cloud e [OpenTofu](https://opentofu.org/docs/intro/install/) ≥ 1.8.
2. Autenticação OCI: `oci setup config` (gera `~/.oci/config`) ou variáveis `OCI_*`.
3. Chave SSH: `ssh-keygen -t ed25519`.
4. Um domínio para a API (o Caddy precisa dele para emitir o certificado).
5. A imagem da API publicada em um registry (veja abaixo).

> **Limites do Always Free** mudam. Confira em
> <https://docs.oracle.com/iaas/Content/FreeTier/resourceref.htm> antes de aumentar `ocpus`/`memory_gb`
> (reportado: 2 OCPU / 12 GB, antes 4 / 24). A Oracle pode recolher VMs ociosas: **faça backup** (abaixo).

## Imagem da API

O workflow `.github/workflows/back-image.yml` roda os testes e, a cada push na `main` que mude `back/`, publica
`ghcr.io/<dono>/pilates-api:latest` (e `:<sha>`) em `linux/arm64`. Também dá para disparar manualmente
(*Actions → Run workflow*). Use o nome em minúsculas em `api_image`.

Manualmente, se preferir (a VM é ARM64):

```bash
cd back
docker buildx build --platform linux/arm64 -t ghcr.io/SEU_USUARIO/pilates-api:latest --push .
```

Se o pacote no GHCR for privado, faça `docker login ghcr.io` na VM uma vez (ou torne o pacote público).

## Primeiro deploy

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # edite
tofu init
tofu plan
tofu apply
```

1. Crie o registro DNS **A** de `domain` apontando para o `public_ip` exibido.
2. Aguarde alguns minutos (cloud-init). Acompanhe com `ssh ubuntu@<ip>` e `sudo tail -f /var/log/cloud-init-output.log`.
3. Teste: `curl https://<domain>/health`.
4. Senha do usuário da plataforma: `tofu output -raw platform_admin_password`.

> Se a VM não for criada com `Out of host capacity`, é falta de capacidade A1 na região: tente de novo mais tarde.

## Atualizar a API

O workflow publica a imagem, mas **não faz o deploy**: o SSH da VM só aceita o seu IP (o GitHub Actions não
alcançaria). Depois que o workflow terminar, na VM:

```bash
cd /opt/pilates && docker compose pull api && docker compose up -d api
```

As migrações (`app.cli migrate`) rodam na subida do container.

## Backup (obrigatório antes de usar com dados reais)

O Always Free não garante a VM. Faça `pg_dump` periódico **para fora da VM** (ex.: bucket OCI Object Storage) dos
bancos `pilates_*` e copie o volume `files` (laudos, dados de saúde — LGPD). Ainda não automatizado.

## Segredos e estado

O estado do Tofu contém `SECRET_KEY` e senhas. `terraform.tfstate` e `*.tfvars` estão no `.gitignore`; não os commite.
Para uso em equipe, mova o estado para um backend remoto com [criptografia de estado](https://opentofu.org/docs/language/state/encryption/).

## Alterações que recriam a VM

`lifecycle.ignore_changes` evita que mudar o cloud-init ou a imagem do SO recrie a VM (apagando o disco). Para mudar
a stack, edite `/opt/pilates` na VM ou aplique o `docker compose` manualmente.
