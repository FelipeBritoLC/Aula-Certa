# Cobertura de testes — Sprint 02

**Tasks:** 32586 (medir cobertura e identificar lacunas) e 32587 (testes
faltantes) · **User story:** 30358 — Realizar testes da aplicação

## Como medir

```bash
export USE_SQLITE=True SECRET_KEY=dev DEBUG=True
pytest --cov                                              # relatório por arquivo
coverage report --include="agenda/*,financeiro/*" --fail-under=60   # meta da proposta
coverage html                                             # relatório navegável em htmlcov/
```

O `.coveragerc` mede apenas o código da aplicação: testes, migrations,
`apps.py`, `admin.py` e comandos de gerenciamento ficam fora do percentual.

## Meta

Proposta de Projeto, seção 3 (critérios de sucesso): cobertura de testes
automatizados de no mínimo **60% nas regras de negócio dos módulos de
agenda e financeiro**.

## Medição inicial (21/10/2026, antes das tasks 32587)

| Arquivo | Cobertura | Lacuna identificada |
|---|---|---|
| `agenda/views.py` | 74% | Agendamento com erro, registro com erro, registro de falta (sem teste) |
| `alunos/views.py` | 47% | Cadastro pela tela, edição (sem teste) |
| `alunos/forms.py` | 59% | Formulário só era exercitado pelo model |
| `financeiro/views.py` | 61% | Registro de pagamento pela tela, listagem de mensalidades |
| `financeiro/forms.py` | 73% | Formulário de pagamento |
| **Agenda + Financeiro** | **≈ 87%** | Meta já atingida; lacunas concentradas nas views |

## Medição final (após a Sprint 02)

| Arquivo | Cobertura |
|---|---|
| `agenda/models.py` | 99% |
| `agenda/views.py` | 100% |
| `agenda/forms.py` · `agenda/visoes.py` | 100% |
| `alunos/models.py` · `alunos/forms.py` | 100% |
| `alunos/views.py` | 94% |
| `financeiro/models.py` | 96% |
| `financeiro/views.py` · `financeiro/forms.py` | 100% |
| `dashboard/views.py` | 100% |
| **Agenda + Financeiro** | **99,4%** |
| **Total da aplicação** | **98,8%** — 276 testes |

## Testes adicionados na Sprint 02

| Arquivo | O que cobre |
|---|---|
| `alunos/test_edicao.py` | US 30325 — alteração, regras na edição, inativação |
| `alunos/test_dados_complementares.py` | US 30322 — responsável para menor, ficha |
| `alunos/test_views.py` | Cadastro e consulta pela tela |
| `agenda/test_detalhes.py` | US 30339 — detalhes da aula realizada |
| `agenda/test_views.py` | Agendamento, registro e falta pela tela |
| `financeiro/test_views.py` | Pagamento pela tela, isolamento, filtro de inadimplência |
| `tests/test_ciclo_ponta_a_ponta.py` | Task 32589 — ciclo completo do professor |

## Integração contínua

O workflow `.github/workflows/ci.yml` (Task 32588) roda a suíte contra
PostgreSQL 16 a cada push e pull request na `main` e falha se a cobertura
de Agenda + Financeiro ficar abaixo de 60%.
