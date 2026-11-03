# Pilates Studio API

API multitenant em **FastAPI + SQLAlchemy 2 + Alembic** para gestão de estúdios de pilates.
Cada estúdio tem **seu próprio banco de dados**; um banco central guarda apenas o cadastro dos estúdios.

## Rodando

Requer apenas o [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env                       # ajuste SECRET_KEY etc.
uv run python -m app.cli init              # banco central + usuário da plataforma
uv run python -m app.cli create-studio --name "Studio Demo" --slug demo \
    --admin-email admin@demo.com --admin-password admin123
uv run fastapi dev app/main.py             # http://localhost:8000/docs
```

- Testes: `uv run pytest`
- Migrar todos os bancos após atualizar o código: `uv run python -m app.cli migrate`
- Nova migração (após alterar models):
  - central: `uv run alembic -n central -x url=sqlite:///./tmp.db revision --autogenerate -m "..."`
  - estúdio: `uv run alembic -n tenant -x url=sqlite:///./tmp.db revision --autogenerate -m "..."`
- Postgres: `uv sync --extra postgres` e ajuste `CENTRAL_DATABASE_URL` / `TENANT_DATABASE_URL_TEMPLATE`.
  O banco de cada estúdio (`pilates_<slug>`) é criado automaticamente — o usuário precisa de permissão `CREATEDB`.

## Multitenancy

```
banco central            banco por estúdio (pilates_<slug>)
├── studios              ├── users, teachers, students
└── platform_users       ├── rooms, plans, discounts, subscriptions
                         ├── class_groups (turmas), enrollments (horários padrão)
                         ├── lessons (aulas), attendances (chamada)
                         └── notifications
```

- `POST /api/v1/platform/studios` (token da plataforma) cria o estúdio, provisiona o banco e o primeiro admin.
- `POST /api/v1/auth/login` com `{studio, email, password}` devolve um token que carrega o estúdio;
  todas as demais rotas usam o banco desse estúdio automaticamente.
- No Swagger (*Authorize*), use `client_id` = slug do estúdio.

Papéis no estúdio: **admin** (tudo) e **teacher** (consulta tudo; faz chamada, reagendamento,
cancelamento e substituição apenas nas próprias aulas; vê apenas o próprio relatório de pagamento).

## Regras de negócio

| Tema | Regra |
|------|-------|
| Funcionamento | Segunda a sexta. Turmas de 1h começando entre `open_hour` (6h) e `close_hour - 1` (18h). Configurável em `PATCH /studio`. |
| Turma | Dia da semana + hora + sala + professor + capacidade (≤ capacidade da sala). Uma sala ou professor não pode ter duas turmas no mesmo horário. |
| Plano | 1, 2 ou 3 aulas/semana, quantidade total de aulas e preço. Descontos percentuais ou fixos, gerais ou por plano. Preço e aulas são congelados ao vincular ao aluno. |
| Horário padrão | O aluno escolhe até N turmas (N = aulas/semana do plano), sem dois horários iguais e respeitando a lotação. `PUT /students/{id}/schedule` altera a partir de uma data, sem mexer no histórico. |
| Aula | Ocorrência da turma em uma data. Status: `confirmed` (há alunos previstos), `inactive` (nenhum aluno) ou `cancelled`. |
| Chamada | `present` ou `absent`. Presença consome 1 aula do plano; falta também consome (configurável: `absence_consumes_credit`). Corrigir a chamada devolve o crédito quando aplicável. |
| Reagendamento | Move o aluno para outra aula (reposição) sem alterar o horário padrão e sem consumir aula; a reposição consome quando houver chamada. Pode ser desfeito. |
| Renovação | Quando as aulas do plano acabam é criada a notificação `plan_exhausted`; aula registrada sem saldo gera `no_credits`. |
| Professor | Recebe `pay_per_class` por aula dada (não cancelada, com ≥ 1 presente) + `pay_per_student` por aluno presente. Substituições contam para quem deu a aula. |

## Rotas principais (`/api/v1`)

| Rota | Descrição |
|------|-----------|
| `/platform/auth/login`, `/platform/studios` | Gestão de estúdios |
| `/auth/login`, `/auth/me`, `/auth/me/password` | Autenticação no estúdio |
| `/studio` | Dados e configurações do estúdio |
| `/users` | Usuários do estúdio (admin/professor) |
| `/rooms`, `/teachers`, `/plans`, `/discounts` | Cadastros; `GET /plans/{id}/price?discount_id=` simula preço |
| `/students` | Cadastro (pode já incluir plano e turmas), ficha completa em `GET /students/{id}` |
| `/students/{id}/subscriptions` | Vincular/renovar/cancelar plano |
| `/students/{id}/schedule` | Ver/alterar turmas padrão |
| `/students/{id}/attendances` | Histórico de presenças |
| `/class-groups` | Turmas (com alunos no detalhe) |
| `/calendar?date_from&date_to&room_id&teacher_id` | Aulas por data/hora (padrão: semana atual) |
| `/lessons/{class_group_id}/{date}` | Detalhe da aula: alunos, professor, dia, hora, status |
| `.../attendance`, `.../reschedule`, `.../cancel`, `.../restore` | Chamada, reposição, cancelamento |
| `/notifications` | Avisos de renovação |
| `/reports/teacher-payments?date_from&date_to` | Aulas dadas, alunos presentes e valor por professor |

## Convenções

- Datas/horas sem fuso, no horário local do estúdio.
- Valores monetários trafegam como string (`"320.00"`).
- Registros duplicados retornam **409**; exclusões de cadastros são lógicas (inativação).

## Estrutura

```
app/
  core/        configuração e segurança (JWT, argon2)
  db/          engines por tenant, provisionamento e migrações
  models/      central.py (estúdios) e tenant/ (dados de cada estúdio)
  schemas/     entrada/saída Pydantic
  services/    regras: agenda, chamada/reposição, créditos, relatórios
  api/         dependências (resolução do tenant, permissões) e rotas
  cli.py       init / migrate / create-studio
migrations/    central/ e tenant/ (Alembic)
tests/         pytest (bancos SQLite temporários por teste)
```
