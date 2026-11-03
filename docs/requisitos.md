# Requisitos do sistema — Gestão de Estúdio de Pilates

> **Fonte da verdade** para back, front e mobile. Humanos e agentes devem consultar este
> documento antes de implementar ou alterar funcionalidades, e atualizá-lo quando um requisito mudar.
>
> - **Requisitos (RF/RN):** definidos pelo dono do produto.
> - **Decisões (D):** escolhas de implementação feitas para cobrir pontos não especificados.
>   Podem ser revistas; ao mudar uma, atualize esta seção e o código.

## 1. Visão geral

Sistema para gerenciar estúdios de pilates, composto por três partes no mesmo repositório:

| Parte | Pasta | Stack |
|-------|-------|-------|
| API | `back/` | Python + FastAPI |
| Painel web | `front/` | React |
| App | `mobile/` | React Native |

O contrato entre elas é a API REST do back (`packages/api-client`, gerado do OpenAPI).

## 2. Glossário

| Termo | Significado | Nome no código |
|-------|-------------|----------------|
| Estúdio | Cliente do sistema (tenant), com base de dados própria | `Studio` |
| Sala | Espaço físico onde ocorrem as aulas | `Room` |
| Turma | Horário semanal fixo: dia da semana + hora + sala + professor | `ClassGroup` |
| Aula | Ocorrência de uma turma em uma data específica | `Lesson` |
| Aluno | Pessoa que frequenta o estúdio | `Student` |
| Professor | Quem ministra as turmas | `Teacher` |
| Plano | Pacote com frequência semanal, quantidade de aulas e preço | `Plan` |
| Desconto | Redução aplicável ao preço de um plano | `Discount` |
| Plano do aluno | Vínculo de um aluno a um plano (contratação/renovação) | `Subscription` |
| Turmas padrão | Turmas fixas que o aluno frequenta toda semana | `Enrollment` |
| Chamada | Registro de presença, falta ou reagendamento de um aluno em uma aula | `Attendance` |
| Reposição | Aula para a qual o aluno foi reagendado | `Attendance.is_makeup` |

## 3. Requisitos funcionais

### Multitenancy
- **RF-01** O sistema funciona no modelo multitenant: **cada estúdio tem uma base de dados separada**.

### Entidades
- **RF-02** O sistema possui as entidades: **Estúdio, Salas, Turmas, Alunos, Professores e Plano**.

### Turmas e horários
- **RF-03** As aulas acontecem de **segunda a sexta, das 6h às 19h**.
- **RF-04** Cada turma tem **duração de 1 hora** e **ocupa uma sala**.
- **RF-05** **Duas turmas não podem estar na mesma sala no mesmo horário.**
- **RF-06** Cada turma tem **um professor**.

### Alunos
- **RF-07** Alunos possuem **turmas padrão de acordo com o plano** (1, 2 ou 3 vezes por semana).
- **RF-08** Deve ser possível **alterar os horários padrão** do aluno.
- **RF-09** Deve ser possível visualizar os dados do aluno: **nome, telefones, e-mails, observações, turmas e plano**.
- **RF-10** Cada aluno tem **um plano vinculado**.

### Chamada e reagendamento
- **RF-11** Deve haver uma **chamada** que identifique **presença, falta ou reagendamento** da aula.
- **RF-12** **Reagendar uma aula não altera os horários padrão do aluno.**

### Planos e renovação
- **RF-13** Cada plano dá acesso a um **número X de aulas**.
- **RF-14** Quando as aulas do plano se esgotarem, deve haver uma **notificação informando que o aluno deve renovar**.
- **RF-15** Os planos têm **preços**, com possibilidade de **cadastrar descontos**.

### Calendário e aulas
- **RF-16** Deve haver um **calendário** para visualizar as turmas **por data e hora**.
- **RF-17** Nos detalhes de cada turma/aula deve ser possível ver **alunos, professor, dia e hora**.
- **RF-18** Cada aula tem um **estado**:
  - **Confirmada** — há alunos ativos;
  - **Inativa** — sem alunos;
  - **Cancelada** — cancelamento por parte do professor.

### Professores
- **RF-19** Deve haver um **controle das aulas dadas pelo professor** e de **quais alunos estiveram presentes**.
- **RF-20** Com base nesse controle, o sistema deve **calcular quanto o professor deve receber**.

## 4. Regras de negócio derivadas

- **RN-01** Uma turma é única por **sala + dia da semana + hora** entre as turmas ativas (RF-05).
- **RN-02** Um professor não pode ter duas turmas no mesmo dia e horário (consequência de RF-06/RF-04).
- **RN-03** O número de turmas padrão de um aluno não pode exceder as aulas por semana do plano (RF-07).
- **RN-04** Um aluno não pode estar em duas turmas no mesmo dia e horário.
- **RN-05** A lotação de uma turma não pode exceder a capacidade da sala.
- **RN-06** O estado da aula é calculado: cancelada se cancelada; senão confirmada se houver ao menos
  um aluno previsto (fixos não reagendados + reposições); senão inativa (RF-18).

## 5. Decisões de implementação

| ID | Decisão | Motivo / alternativa |
|----|---------|----------------------|
| D-01 | Um **banco central** guarda o cadastro dos estúdios; cada estúdio tem um banco próprio (SQLite em dev, `pilates_<slug>` no Postgres). O token de login carrega o estúdio. | Implementa RF-01. |
| D-02 | Um **usuário da plataforma** cria os estúdios; cada estúdio tem usuários **admin** e **professor**. | Necessário para cadastrar tenants. |
| D-03 | "Das 6h às 19h" = o estúdio **fecha às 19h**; última turma começa às **18h**. Horários configuráveis por estúdio (`open_hour`, `close_hour`). | Alternativa: última turma às 19h (`close_hour = 20`). |
| D-04 | A **aula** só é gravada no banco quando há chamada, reposição, cancelamento ou substituição; antes disso é calculada a partir da turma. | Evita gerar aulas em lote. |
| D-05 | **Presença consome** 1 aula do plano. **Falta também consome** (configurável por estúdio: `absence_consumes_credit`). **Reagendar não consome**; a reposição consome quando houver chamada. | Prática comum em estúdios. |
| D-06 | Notificações: `plan_exhausted` quando a última aula do plano é usada; `no_credits` quando uma aula é registrada sem saldo. Renovar = vincular um novo plano ao aluno. | Implementa RF-14. |
| D-07 | O plano não tem validade por data: termina quando as aulas acabam. | Não especificado. |
| D-08 | **Pagamento do professor** = `pay_per_class` × aulas dadas + `pay_per_student` × alunos presentes, configurável por professor. "Aula dada" = não cancelada e com ao menos um aluno presente. Usa os valores atuais do professor. | Cobre os dois modelos comuns (fixo por aula / por aluno). |
| D-09 | É possível definir um **professor substituto** em uma aula específica; a aula conta para quem a deu. | Complementa RF-19/RF-20. |
| D-10 | Professor (usuário) consulta tudo, mas só faz chamada, reagendamento e cancelamento **nas próprias aulas** e vê apenas o próprio relatório de pagamento. | Controle de acesso. |
| D-11 | Descontos são **percentuais ou de valor fixo**, gerais ou restritos a um plano. Preço e quantidade de aulas são **congelados** quando o plano é vinculado ao aluno. | Implementa RF-15. |
| D-12 | Alterar horários padrão vale **a partir de uma data**, preservando o histórico. | Implementa RF-08. |
| D-13 | Exclusões de cadastros são lógicas (inativação). | Preserva histórico. |
| D-14 | Datas e horas são do **horário local do estúdio**, sem fuso. Valores monetários trafegam como string (`"320.00"`). | Simplicidade / precisão. |

## 6. Fora do escopo (por enquanto)

- Cobrança e financeiro de mensalidades (pagamentos, inadimplência).
- Validade de planos por data.
- Feriados e fechamentos pontuais do estúdio.
- Área do aluno (login do aluno no app).
- Envio de notificações por e-mail/push (hoje são registros consultáveis na API).

## 7. Onde está implementado (back)

| Requisito | Endpoint(s) |
|-----------|-------------|
| RF-01 | `POST /api/v1/platform/studios`, `POST /api/v1/auth/login` |
| RF-02 | `/rooms`, `/class-groups`, `/students`, `/teachers`, `/plans`, `/studio` |
| RF-03 a RF-06 | `POST /class-groups`, `PATCH /studio` |
| RF-07, RF-08 | `PUT /students/{id}/schedule` |
| RF-09, RF-10 | `GET /students/{id}`, `/students/{id}/subscriptions` |
| RF-11, RF-12 | `POST /lessons/{class_group_id}/{date}/attendance`, `.../reschedule` |
| RF-13, RF-14 | `/plans`, `GET /notifications` |
| RF-15 | `/discounts`, `GET /plans/{id}/price` |
| RF-16 a RF-18 | `GET /calendar`, `GET /lessons/{class_group_id}/{date}`, `.../cancel` |
| RF-19, RF-20 | `GET /reports/teacher-payments` |

Detalhes técnicos: [back/README.md](../back/README.md). Documentação interativa: `http://localhost:8010/docs`.
