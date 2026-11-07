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
uv run python -m app.cli seed-demo --slug demo --reset   # dados de demonstração (opcional)
uv run fastapi dev app/main.py --port 8010  # http://localhost:8010/docs
```

> A porta padrão do projeto é **8010** (a 8000 costuma estar ocupada, ex.: Docker Desktop).
> O front repassa `/api` para ela em desenvolvimento.

- Testes: `uv run pytest`
- Migrar todos os bancos após atualizar o código: `uv run python -m app.cli migrate`
- Nova migração (após alterar models):
  - central: `uv run alembic -n central -x url=sqlite:///./tmp.db revision --autogenerate -m "..."`
  - estúdio: `uv run alembic -n tenant -x url=sqlite:///./tmp.db revision --autogenerate -m "..."`
  - Migrações que transformam dados devem ter um teste com dados reais (veja `tests/test_migrations.py`);
    os demais testes rodam em bancos vazios e não exercitam esse código.
  - SQL manual em migrações: use `bindparam(..., type_=...)` para valores `Decimal`, booleanos etc.
- Postgres: `uv sync --extra postgres` e ajuste `CENTRAL_DATABASE_URL` / `TENANT_DATABASE_URL_TEMPLATE`.
  O banco de cada estúdio (`pilates_<slug>`) é criado automaticamente — o usuário precisa de permissão `CREATEDB`.

## Multitenancy

```
banco central            banco por estúdio (pilates_<slug>)
├── studios              ├── users, teachers, students
└── platform_users       ├── rooms, plans, discounts, subscriptions
                         ├── class_groups (turmas), enrollments (horários padrão)
                         ├── payments (pagamentos de alunos e professores)
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
| Aula | Ocorrência da turma em uma data. Status: `confirmed` (há alunos previstos), `inactive` (nenhum aluno), `cancelled` ou `completed` (finalizada). |
| Finalização | Depois que a aula começa, o professor informa `present`, `absent` ou `rescheduled` para **todos** os alunos (justificativa opcional em falta/reagendamento) e a aula fica `completed`. Só então presenças são registradas e aulas do plano debitadas (falta também debita, configurável: `absence_consumes_credit`). Admin pode reabrir, devolvendo os débitos. |
| Reagendamento | Move o aluno para outra aula (reposição) sem alterar o horário padrão e sem consumir aula; a reposição consome quando a aula de destino for finalizada. Pode ser feito antes da aula ou na finalização. Uma reposição pode ser reagendada de novo; `GET /students/{id}/reschedules` mostra cada aula original e quantas vezes foi reagendada. |
| Renovação | Renovar antes do fim: o plano em uso continua sendo debitado até acabar; o novo fica `queued` e assume em seguida. Quando o último plano com aulas acaba, é criada a notificação `plan_exhausted`; aula registrada sem saldo gera `no_credits`. Nome, preço, desconto e aulas ficam congelados na contratação (histórico em `GET /students/{id}/subscriptions`). |
| Professor | Por aula **concluída**: `pay_per_class` + para cada presente `student_share_percent` (padrão 40%) × preço pago no plano ÷ aulas do plano, nunca abaixo de `min_pay_per_lesson`; se todos faltarem, recebe o mínimo. O valor é **congelado na conclusão** (mudar a remuneração não altera o histórico). Aulas não concluídas não contam. Substituições contam para quem deu a aula. |

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
| `/students/{id}/attendances` | Histórico de aulas (independe do horário atual) |
| `/students/{id}/schedule/history` | Histórico de horários padrão (atuais, futuros, encerrados) |
| `/students/{id}/documents` | Laudos/exames do aluno (PDF, JPG, PNG): enviar (admin), listar, baixar e excluir (admin). Armazenamento local ou S3 (`STORAGE_BACKEND`) |
| `/students/{id}/history` | Registro de alterações: o que mudou, quem e quando |
| `/students/{id}/subscriptions/{sid}/payment` | Marca o plano como pago/pendente (atualiza o pagamento do plano) |
| `/payments` | Pagamentos de alunos (plano) e professores: lista com filtros `kind`, `student_id`, `teacher_id`, `status`, `date_from`/`date_to` (+ `date_field`); `POST /payments/{id}/pay`, `/pending`, `/cancel`; observações via `PATCH` |
| `/services` | Catálogo de serviços avulsos (fisioterapia, RPG…) |
| `/catalog/overview` | Uso de cada plano (em uso, na fila, pendentes) e serviço (contratos, sessões futuras) |
| `/students/{id}/services` | Serviços avulsos do aluno: contratar (sala, profissional, horário, valor editável, recorrência opcional), histórico, observações, cancelar |
| `/service-sessions/{id}` | Sessão de serviço: detalhe, `complete` (presente/falta), `reopen` (admin) |
| `/class-groups` | Turmas (com alunos no detalhe) |
| `/calendar?date_from&date_to&room_id&teacher_id` | Aulas por data/hora (padrão: semana atual) |
| `/lessons/{class_group_id}/{date}` | Detalhe da aula: alunos, professor, dia, hora, status |
| `/lessons/pending` | Aulas que já começaram e aguardam finalização |
| `.../complete`, `.../reopen` | Finaliza a aula (presença/falta/reagendamento + justificativa) / reabre (admin) |
| `.../reschedule`, `.../cancel`, `.../restore` | Reposição antecipada, cancelamento |
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
