# Ciclo de teste funcional ponta a ponta — Sprint 02

**Task:** 32589 · **User story:** 30358 — Realizar testes da aplicação
**Versão do sistema:** `main` após a Sprint 02 (21/10/2026)

## Objetivo

Validar, do ponto de vista do professor, o fluxo completo que as Sprints 01
e 02 entregam: cadastro do aluno, agenda, registro pedagógico da aula,
controle financeiro e indicadores. O roteiro encadeia as user stories
30321, 30322, 30323, 30325, 30332, 30333, 30337, 30338, 30339, 30344,
30350 e 30355.

O mesmo roteiro está automatizado em `tests/test_ciclo_ponta_a_ponta.py`
(um passo do teste para cada passo abaixo) e roda no CI a cada push.

## Pré-condições

- Usuário professor com acesso ao Django Admin (no Render é criado pelo
  `create_default_superuser`; localmente, `python manage.py createsuperuser`).
- Nenhum aluno com o CPF `529.982.247-25` cadastrado para esse professor.
- O lançamento de mensalidades ainda é feito pelo Django Admin: a tela
  própria e a geração automática a partir do contrato são da Sprint 03
  (US 30346 e 30327).

## Roteiro

| # | Ação | Resultado esperado |
|---|------|--------------------|
| 1 | Acessar `/login/` e entrar com o professor. | Painel de indicadores é exibido. |
| 2 | **Alunos → Cadastrar**: Pedro Henrique Lima, CPF 529.982.247-25, telefone 83991112222, nascimento há 13 anos, Matemática, 8º ano, Escola Municipal Centro, **sem responsável**. Salvar. Depois preencher responsável Ana Lima, 83993334444, Mãe, e salvar de novo. | 1ª tentativa: erro "o aluno é menor de idade" nos campos do responsável. 2ª: aluno cadastrado e ficha aberta. |
| 3 | Na lista de alunos, buscar "pedro". Abrir a ficha. | Aluno aparece no filtro. Ficha mostra dados acadêmicos (escola, série) e o card do responsável. |
| 4 | **Agenda → Agendar aula** para Pedro daqui a 2 dias às 15:00, 60 min, presencial, "Casa do aluno". Repetir o mesmo agendamento. | 1º: aula criada. 2º: erro "Conflito de horário detectado". |
| 5 | Na página da aula, **Editar informações**: 16:00, 90 min, online, "Google Meet". | Aula atualizada com o novo horário, duração e modalidade. |
| 6 | **Agenda** na visão **semanal**, navegando até a semana da aula. | A aula de Pedro aparece no dia correto, com indicação de status. |
| 7 | Na aula, **Registrar como realizada**: conteúdo com 50+ caracteres, material "Lista de exercícios 2", avaliação "Bom", recomendação "Revisar MMC". | Botão Concluir só habilita com 50+ caracteres. Aula muda para Realizada e exibe os detalhes. |
| 8 | Na aula realizada, **Editar detalhes**: avaliação "Ótimo", material "Lista de exercícios 2 e jogo de frações". Abrir a ficha do aluno. | Detalhes atualizados. Ficha mostra o histórico com conteúdo, "Desempenho: Ótimo", material e recomendações. |
| 9 | No **Django Admin → Mensalidades → Adicionar**: (a) competência = 1º dia do mês atual, R$ 400,00, vencimento daqui a 10 dias; (b) competência = 1º dia do mês anterior, R$ 350,00, vencimento há 20 dias. | Duas mensalidades pendentes lançadas. |
| 10 | **Financeiro** (inadimplentes). | Pedro aparece como inadimplente pela mensalidade vencida há 20 dias. |
| 11 | Em **Mensalidades**, pagar R$ 150,00 da mensalidade atual (Pix); depois os R$ 250,00 restantes; depois R$ 350,00 da antiga (dinheiro). | Após o 1º pagamento: pendente com saldo R$ 250,00. Ao final: as duas pagas e a lista de inadimplentes vazia. |
| 12 | Abrir o **Painel**. | 1 aluno ativo, faturamento do mês R$ 400,00, valor pendente R$ 0,00, nenhum inadimplente. |
| 13 | **Editar aluno** → situação Inativo → Salvar. Tentar **Agendar aula**. | Aviso "Novos agendamentos para este aluno estão bloqueados". Pedro não aparece na lista de alunos do agendamento. |
| 14 | **Sair**. Tentar abrir o painel. | Redireciona para o login. |

## Execuções

| Data | Ambiente | Executor | Resultado |
|------|----------|----------|-----------|
| 21/10/2026 | Automatizado (`tests/test_ciclo_ponta_a_ponta.py`, SQLite) | Suíte de testes | ✅ 14/14 passos aprovados |
| | Homologação (Render) | | ☐ pendente |

Para registrar a execução manual na homologação, percorra os passos acima,
preencha a linha da tabela e anote aqui qualquer divergência encontrada
(passo, o que aconteceu, print).

## Divergências encontradas

Nenhuma na execução automatizada. Durante a preparação do ciclo foram
encontrados e corrigidos três defeitos (commits da Sprint 02):

1. Editar um aluno apagava o endereço, porque o campo não era exibido no formulário.
2. O filtro `min_dias` da tela de inadimplentes gerava erro 500 com valor não numérico.
3. Era possível registrar falta em uma aula já realizada.
