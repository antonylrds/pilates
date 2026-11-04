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
- **RF-30** Deve haver um **modal de cadastro do aluno**, com definição do **plano**, se o plano **já foi pago** e,
  conforme o plano, das **turmas padrão**. O **mesmo modal** é usado para **editar** o aluno.
- **RF-31** O **histórico de aulas** do aluno fica **separado das turmas padrão**: se o aluno mudar de horário,
  as aulas anteriores e os horários anteriores continuam no histórico.
- **RF-32** Alterações no cadastro do aluno (dados, horário, plano, pagamento) devem deixar um **registro do que
  mudou, por quem e em que data**.

### Serviços avulsos
- **RF-33** Os alunos podem contratar **serviços avulsos** (ex.: fisioterapia, RPG), **cadastrados à parte**.
- **RF-34** Por padrão o serviço é **sem recorrência**, mas deve ser possível contratá-lo **com recorrência**.
- **RF-35** Os serviços têm um **valor definido** no cadastro, que pode ser **alterado na contratação**.
- **RF-36** Deve haver **histórico de serviços avulsos** do aluno e **observações** sobre cada serviço contratado.
- **RF-37** Serviços avulsos **ocupam salas** (não podem coincidir com turmas ou outros serviços na mesma sala e
  horário) e aparecem no **calendário**.
- **RF-38** Serviços avulsos também devem ser **finalizados**; só sessões finalizadas são contabilizadas.
- **RF-39** Os profissionais recebem pelos serviços com base em uma **porcentagem** do valor da sessão.

### Chamada e reagendamento
- **RF-11** Deve haver uma **chamada** que identifique **presença, falta ou reagendamento** da aula.
- **RF-12** **Reagendar uma aula não altera os horários padrão do aluno.**
- **RF-29** Deve ser possível **acompanhar quantas vezes uma aula específica** de um aluno foi **reagendada**.
- **RF-41** No modal da turma deve ser possível **adicionar alunos de forma fixa** (recorrente) ou **não recorrente**
  (reagendamento para uma data da turma).
- **RF-42** Deve existir plano **sem recorrência** (inclusive de **R$ 0**): o aluno não tem turmas padrão e é
  **incluído nas aulas como avulso**, uma data por vez, usando as aulas do plano.
- **RF-43** Nos **detalhes da aula** (agenda) deve ser possível **incluir alunos** e **alterar o professor**.
  Se o aluno **não tiver aulas disponíveis**, o sistema informa e **impede** a inclusão.
- **RF-44** Deve haver uma tela de **caixa** com **todos os recebimentos** do estúdio, o **faturamento do mês**
  e o **desconto do pagamento dos professores**.

### Planos e renovação
- **RF-13** Cada plano dá acesso a um **número X de aulas**.
- **RF-14** Quando as aulas do plano se esgotarem, deve haver uma **notificação informando que o aluno deve renovar**.
- **RF-15** Os planos têm **preços**, com possibilidade de **cadastrar descontos**.
- **RF-40** Deve haver uma **tela de controle dos planos**, compartilhada com os **serviços avulsos**.
- **RF-27** Deve ser possível visualizar o **histórico de planos** de cada aluno, com os **valores congelados**
  da contratação.
- **RF-28** Se o aluno **renovar antes do fim do plano**, o plano em uso **continua sendo contado até que todas
  as suas aulas sejam dadas**; só então o novo plano passa a ser contado.

### Calendário e aulas
- **RF-16** Deve haver um **calendário** para visualizar as turmas **por data e hora**.
- **RF-17** Nos detalhes de cada turma/aula deve ser possível ver **alunos, professor, dia e hora**.
- **RF-18** Cada aula tem um **estado**:
  - **Confirmada** — há alunos ativos;
  - **Inativa** — sem alunos;
  - **Cancelada** — cancelamento por parte do professor;
  - **Concluída** — aula finalizada pelo professor (RF-21).

### Finalização de aulas
- **RF-21** Deve haver uma **tela para finalizar as aulas** conforme forem sendo concluídas. Nela o professor
  marca, para cada aluno, **presença, falta ou reagendamento**.
- **RF-22** Em caso de **falta** ou **reagendamento**, deve ser possível informar uma **justificativa**.
- **RF-23** Ao final, a aula fica com o estado **Concluída** e passa a ser **contabilizada**.
- **RF-24** Aulas **não concluídas não são contabilizadas** em cálculos de **pagamento** ou de **presenças**.

### Professores
- **RF-19** Deve haver um **controle das aulas dadas pelo professor** e de **quais alunos estiveram presentes**.
- **RF-20** Com base nesse controle, o sistema deve **calcular quanto o professor deve receber**.
- **RF-25** Cada professor pode ter um **valor mínimo por aula**, configurado individualmente, que garante
  recebimento **mesmo quando todos os alunos faltam**.
- **RF-26** O valor de cada **aluno presente** é **40% do valor do plano dividido pelo número de aulas** que o
  plano dá direito.

## 4. Regras de negócio derivadas

- **RN-01** Uma turma é única por **sala + dia da semana + hora** entre as turmas ativas (RF-05).
- **RN-02** Um professor não pode ter duas turmas no mesmo dia e horário (consequência de RF-06/RF-04).
- **RN-03** O número de turmas padrão de um aluno não pode exceder as aulas por semana do plano (RF-07).
- **RN-04** Um aluno não pode estar em duas turmas no mesmo dia e horário.
- **RN-05** A lotação de uma turma não pode exceder a capacidade da sala.
- **RN-06** O estado da aula é calculado: cancelada se cancelada; senão concluída se finalizada; senão
  confirmada se houver ao menos um aluno previsto (fixos não reagendados + reposições); senão inativa (RF-18).
- **RN-07** Uma aula só pode ser finalizada **depois de começar**, se não estiver cancelada, e informando o
  resultado de **todos** os alunos previstos (finalização atômica: tudo ou nada).
- **RN-08** Presenças, faltas e o débito de aulas do plano só são registrados **na finalização** (RF-24).
- **RN-09** Aula concluída não pode ser cancelada nem ter reagendamentos desfeitos; o **admin** pode **reabrir**
  uma aula concluída, o que devolve as aulas debitadas e remove a aula dos cálculos.

## 5. Decisões de implementação

| ID | Decisão | Motivo / alternativa |
|----|---------|----------------------|
| D-01 | Um **banco central** guarda o cadastro dos estúdios; cada estúdio tem um banco próprio (SQLite em dev, `pilates_<slug>` no Postgres). O token de login carrega o estúdio. | Implementa RF-01. |
| D-02 | Um **usuário da plataforma** cria os estúdios; cada estúdio tem usuários **admin** e **professor**. | Necessário para cadastrar tenants. |
| D-03 | "Das 6h às 19h" = o estúdio **fecha às 19h**; última turma começa às **18h**. Horários configuráveis por estúdio (`open_hour`, `close_hour`). | Alternativa: última turma às 19h (`close_hour = 20`). |
| D-04 | A **aula** só é gravada no banco quando há chamada, reposição, cancelamento ou substituição; antes disso é calculada a partir da turma. | Evita gerar aulas em lote. |
| D-05 | Na finalização, **presença consome** 1 aula do plano e **falta também consome** (configurável por estúdio: `absence_consumes_credit`). **Reagendar não consome**; a reposição consome quando a aula de destino for finalizada. | Prática comum em estúdios. |
| D-06 | Notificações: `plan_exhausted` quando a última aula do plano é usada; `no_credits` quando uma aula é registrada sem saldo. Renovar = vincular um novo plano ao aluno. | Implementa RF-14. |
| D-07 | O plano não tem validade por data: termina quando as aulas acabam. | Não especificado. |
| D-08 | **Pagamento do professor**, por aula **concluída**: `pay_per_class` + soma do valor de cada aluno presente (D-18), **nunca abaixo de `min_pay_per_lesson`**. Se todos faltarem, paga apenas o mínimo; sem mínimo, a aula **aparece no relatório com R$ 0** e conta como aula dada (sem presença). Valores configuráveis por professor e **congelados na conclusão** de cada aula: alterar a remuneração só afeta aulas concluídas depois. Reabrir a aula descarta o valor congelado; trocar o professor de uma aula concluída exige reabri-la. | Cobre os modelos comuns (fixo por aula / por aluno / garantia mínima). Implementa RF-20 e RF-25. |
| D-09 | É possível definir um **professor substituto** em uma aula específica; a aula conta para quem a deu. | Complementa RF-19/RF-20. |
| D-10 | Professor (usuário) consulta tudo, mas só faz chamada, reagendamento e cancelamento **nas próprias aulas** e vê apenas o próprio relatório de pagamento. | Controle de acesso. |
| D-11 | Descontos são **percentuais ou de valor fixo**, gerais ou restritos a um plano. Preço e quantidade de aulas são **congelados** quando o plano é vinculado ao aluno. | Implementa RF-15. |
| D-12 | Alterar horários padrão vale **a partir de uma data**, preservando o histórico. | Implementa RF-08. |
| D-13 | Exclusões de cadastros são lógicas (inativação). | Preserva histórico. |
| D-14 | Datas e horas são do **horário local do estúdio**, sem fuso. Valores monetários trafegam como string (`"320.00"`). | Simplicidade / precisão. |
| D-15 | **Reagendar** pode ser feito **antes da aula** (aluno avisa; pelo painel da agenda) ou **na finalização**. Em ambos os casos é obrigatório escolher a aula de reposição, que ainda não pode ter começado. | Implementa RF-11/RF-21. |
| D-16 | A justificativa é **opcional** (até 500 caracteres) e fica no histórico do aluno. | RF-22 diz "deve ser possível". |
| D-18 | Valor do aluno presente = `student_share_percent` (padrão **40%**, configurável por professor) × **preço pago** no plano do aluno (já com desconto) ÷ **aulas do plano**. Usa o plano debitado naquela aula (congelado na conclusão). Presença **sem aula disponível** no plano gera R$ 0. Faltas não geram valor por aluno. Aulas concluídas antes desta regra mantêm o valor calculado na regra anterior. | Implementa RF-26. Alternativa: usar o preço cheio do plano, sem desconto. |
| D-19 | Na contratação ficam congelados **nome do plano, nome do desconto, preço, desconto, valor pago, aulas e frequência**. O histórico mostra também valor por aula (pago ÷ aulas), aulas usadas e período de uso (1ª e última aula debitada). Situações: **em uso**, **aguardando** (renovação antecipada), **encerrado**, **cancelado**. | Implementa RF-27. |
| D-20 | Com vários planos ativos, as aulas são debitadas do **mais antigo** (data de contratação) até acabar. O aviso de renovação só é gerado quando acaba o último plano com aulas. A ficha mostra o plano **em uso** e os planos aguardando. O limite de turmas padrão usa a **maior frequência** entre os planos ativos, para permitir ajustar o horário ao renovar para um plano maior. | Implementa RF-28. |
| D-21 | Uma aula do horário padrão reagendada forma uma **cadeia**: original → reposição → (reagendada de novo) → …. A contagem é o número de reagendamentos desde a aula original. Aparece em cada reposição (detalhes da aula e finalização), nas reposições agendadas e no card **Reagendamentos** da ficha, com cada passo, justificativa e situação atual. Desfazer um reagendamento remove o passo da cadeia. Não há limite de reagendamentos. | Implementa RF-29. |
| D-22 | Pagamento do plano: `is_paid` + `paid_at` (padrão: hoje). Pode ser marcado no cadastro, na renovação ou depois, na edição. É só um controle de "pago/pendente" (sem valores parciais, formas de pagamento ou cobrança). | Implementa RF-30. |
| D-23 | Na edição, a troca de turmas padrão vale **a partir de uma data** (padrão: hoje); o horário anterior termina na véspera. "Histórico de horários" lista os horários atuais, futuros e encerrados; "Histórico de aulas" lista as chamadas, que não mudam com o horário. | Implementa RF-31. |
| D-24 | Registro de alterações (`audit_logs`) por aluno: ação, descrição legível, campos alterados (antes/depois), **usuário** (nome gravado) e **data/hora local**. Registra cadastro, edição de dados (só campos que mudaram), troca de horário, plano contratado/cancelado, pagamento e inativação/reativação. Trocar o plano em si é feito por "Renovar plano". | Implementa RF-32. |
| D-25 | **Serviço avulso**: catálogo (nome, descrição, valor padrão por sessão). A **contratação** congela nome, valor de tabela e **valor combinado por sessão** (editável só na contratação). Recorrência: **sem** (1 sessão, padrão), **semanal**, **quinzenal** ou **mensal** com N sessões (2–52, padrão 4); as datas são geradas. Cancelar a contratação cancela as sessões agendadas de hoje em diante. Observações e pagamento (pago/pendente) podem ser alterados depois; tudo vai para o registro de alterações. Serviços **não** usam aulas do plano. | Implementa RF-33 a RF-36. |
| D-26 | Na contratação o serviço recebe **sala, profissional e horário** (sessões de 1h, seg–sex, no horário do estúdio), herdados por todas as sessões. Sala e profissional não podem ter **turma** (aula não cancelada) nem **outra sessão** no mesmo dia/hora; criar ou mover turmas também respeita as sessões futuras. As sessões aparecem no **calendário** (cor própria) e em **Finalizar aulas**. | Implementa RF-37. |
| D-27 | Sessão de serviço: **agendada → presente/falta** (finalização pelo profissional da sessão ou admin, depois do início; justificativa opcional na falta) ou **cancelada**. Admin pode reabrir. Presente gera ao profissional `service_share_percent` (padrão **40%**, por profissional, separado do % das aulas) × valor combinado da sessão; falta gera R$ 0. O valor é **congelado na finalização**. O mínimo por aula vale só para aulas de pilates. O relatório de professores soma aulas + serviços. | Implementa RF-38 e RF-39. |
| D-28 | Tela **Planos e serviços** com abas **Planos**, **Descontos** e **Serviços avulsos**: cadastro, edição, desativação/reativação e uso atual (alunos com o plano em uso, na fila, pagamentos pendentes; contratações e sessões futuras de cada serviço). Descontos podem ter nome, tipo, valor e plano alterados. Toda alteração vale só para novas contratações (valores congelados). | Implementa RF-40. |
| D-29 | Modal da turma com abas **Turma** e **Alunos**. **Fixo**: adiciona a turma ao horário padrão do aluno a partir de uma data (limite do plano e lotação valem); remover tira a turma a partir de uma data, preservando o histórico. **Avulso**: reagenda uma **aula futura do aluno** (origem, de `GET /students/{id}/upcoming-lessons`) para uma data desta turma com vaga — é uma reposição, conta como reagendamento e não altera o horário padrão. | Implementa RF-41. |
| D-17 | A tela de finalização lista as aulas que **já começaram** nos últimos 30 dias, têm alunos e não foram concluídas/canceladas. Professor vê apenas as próprias. | Implementa RF-21. |
| D-31 | Plano com `sessions_per_week = 0` = **sem recorrência**: não permite turmas padrão. **Aula avulsa** = registro de presença fora do horário padrão **sem aula de origem** (`is_makeup = true`, `makeup_from` vazio; exposto como `is_drop_in`). Só em aula que ainda não começou, com vaga e sem conflito de horário; o aluno precisa ter saldo (aulas restantes menos avulsas já marcadas e não concluídas, inclusive as que foram reagendadas). A aula do plano é debitada na conclusão, como qualquer presença; pode ser reagendada e removida enquanto pendente. Vale para qualquer plano, não só os sem recorrência. | Implementa RF-42. |
| D-32 | Detalhes da aula: **incluir aluno** (antes da aula começar) como **aula avulsa** (exige `drop_in_available > 0` = aulas restantes menos avulsas já marcadas) ou como **reposição** de uma aula futura do aluno (exige aulas restantes > 0). **Alterar professor** (admin) vale só para aquela data (substituto), não em aulas concluídas ou canceladas, e é recusado se o professor já der outra aula ou atender um serviço no mesmo dia e horário. | Implementa RF-43. |
| D-33 | **Caixa** (só admin), por mês: recebimentos = planos e serviços **pagos**, pela **data do pagamento** (`paid_at`), com valor de tabela, desconto e valor recebido (serviço = valor por sessão × sessões contratadas). Pagamento dos professores = relatório de pagamento (D-08) das aulas/sessões **finalizadas no mês**. Resultado = faturamento − professores. **A receber** = planos e serviços não pagos e não cancelados, de qualquer data (planos gratuitos ficam de fora). Estornos/reembolsos não são controlados. | Implementa RF-44. |
| D-30 | Datas são exibidas e digitadas sempre como **dd/mm/aaaa** (componente `DateInput` no front), independente do idioma do navegador/SO — o `<input type="date">` nativo segue a localidade do sistema. A API continua trocando datas em ISO (`aaaa-mm-dd`). | Vale também para o mobile. |

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
| RF-11, RF-12 | `POST /lessons/{class_group_id}/{date}/complete`, `.../reschedule` |
| RF-21 a RF-24 | `GET /lessons/pending`, `POST /lessons/{class_group_id}/{date}/complete`, `.../reopen` |
| RF-13, RF-14 | `/plans`, `GET /notifications` |
| RF-15 | `/discounts`, `GET /plans/{id}/price` |
| RF-16 a RF-18 | `GET /calendar`, `GET /lessons/{class_group_id}/{date}`, `.../cancel` |
| RF-19, RF-20 | `GET /reports/teacher-payments` |
| RF-41 | `PUT /students/{id}/schedule`, `GET /students/{id}/upcoming-lessons`, `POST /lessons/{class_group_id}/{date}/reschedule` |
| RF-42 | `POST /plans` (`sessions_per_week: 0`), `POST /lessons/{class_group_id}/{date}/drop-in`, `DELETE /lessons/{class_group_id}/{date}/drop-in/{student_id}` |
| RF-43 | `GET /students/{id}` (`drop_in_available`), `POST /lessons/{class_group_id}/{date}/drop-in`, `PATCH /lessons/{class_group_id}/{date}` (`teacher_id`) |
| RF-44 | `GET /reports/cash` |
| RF-40 | `/plans`, `/discounts`, `/services`, `GET /catalog/overview` |
| RF-33 a RF-36 | `/services`, `GET/POST /students/{id}/services`, `PATCH .../services/{cid}`, `.../cancel`, `.../sessions/{sid}` |
| RF-37 a RF-39 | `GET /calendar` (`kind = service`), `GET /lessons/pending`, `GET /service-sessions/{id}`, `.../complete`, `.../reopen`, `GET /reports/teacher-payments` (`services`) |
| RF-30 | `POST /students`, `PATCH /students/{id}`, `PUT /students/{id}/schedule`, `PATCH /students/{id}/subscriptions/{sid}/payment` |
| RF-31 | `GET /students/{id}/schedule/history`, `GET /students/{id}/attendances` |
| RF-32 | `GET /students/{id}/history` |
| RF-29 | `GET /students/{id}/reschedules`, `reschedule_count` / `original_lesson` em `GET /lessons/{class_group_id}/{date}` |
| RF-27, RF-28 | `GET/POST /students/{id}/subscriptions`, `GET /students/{id}` (`subscription`, `queued_subscriptions`) |
| RF-25, RF-26 | `PATCH /teachers/{id}` (`min_pay_per_lesson`, `student_share_percent`), `GET /reports/teacher-payments` |

Detalhes técnicos: [back/README.md](../back/README.md). Documentação interativa: `http://localhost:8010/docs`.
