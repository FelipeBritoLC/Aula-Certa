import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


IDADE_MAIORIDADE = 18


def validar_cpf_formato(value):
    """Valida que o CPF contém 11 dígitos numéricos (com ou sem máscara)."""
    digitos = re.sub(r"\D", "", value or "")
    if len(digitos) != 11:
        raise ValidationError("CPF deve conter 11 dígitos.")


class Aluno(models.Model):
    """
    Task 31762 — Modelagem da Tabela de Alunos e índices de busca.

    Critérios de aceite implementados (US-30321 "Cadastrar aluno"):
    CA-CAD-01: unicidade do CPF por professor, com erro 409/ValidationError
               em caso de duplicidade.
    CA-CAD-02: Nome, CPF e Contato (telefone) são obrigatórios.
    CA-CAD-03: sanitização (trim) do nome para remover espaços redundantes.

    US-30322 "Informar dados complementares do aluno":
    CA-COMP-01: data de nascimento não pode estar no futuro.
    CA-COMP-02: aluno menor de 18 anos exige nome e telefone do responsável.
    CA-COMP-03: dados acadêmicos e do responsável aparecem na ficha do aluno.
    """

    class Situacao(models.TextChoices):
        ATIVO = "ATIVO", "Ativo"
        INATIVO = "INATIVO", "Inativo"

    professor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alunos"
    )

    nome = models.CharField(max_length=150)
    cpf = models.CharField(max_length=14, validators=[validar_cpf_formato])
    telefone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)

    data_nascimento = models.DateField(null=True, blank=True)
    endereco = models.CharField(max_length=255, blank=True)

    disciplina = models.CharField(max_length=100, blank=True)
    serie_nivel = models.CharField(max_length=100, blank=True)
    escola = models.CharField(max_length=150, blank=True)
    observacoes = models.TextField(blank=True)

    responsavel_nome = models.CharField(max_length=150, blank=True)
    responsavel_telefone = models.CharField(max_length=20, blank=True)
    responsavel_email = models.EmailField(blank=True)
    responsavel_parentesco = models.CharField(max_length=50, blank=True)

    valor_hora = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Se vazio, usa o valor-hora padrão do professor.",
    )
    saldo_devedor = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    situacao = models.CharField(
        max_length=10, choices=Situacao.choices, default=Situacao.ATIVO
    )
    data_cadastro = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["professor", "cpf"], name="uniq_cpf_por_professor"
            ),
            models.CheckConstraint(
                check=models.Q(saldo_devedor__gte=0),
                name="aluno_saldo_devedor_nao_negativo",
            ),
            models.CheckConstraint(
                check=models.Q(valor_hora__isnull=True) | models.Q(valor_hora__gt=0),
                name="aluno_valor_hora_nulo_ou_positivo",
            ),
        ]
        indexes = [
            models.Index(fields=["professor", "nome"], name="idx_aluno_professor_nome"),
            models.Index(fields=["professor", "situacao"], name="idx_aluno_professor_situacao"),
        ]

    def __str__(self):
        return self.nome

    def clean(self):
        # CA-CAD-03: sanitização de strings (trim + colapso de espaços)
        if self.nome:
            self.nome = re.sub(r"\s+", " ", self.nome).strip()
        if self.cpf:
            self.cpf = re.sub(r"\D", "", self.cpf)

        # CA-CAD-02: campos obrigatórios
        if not self.nome:
            raise ValidationError({"nome": "O nome é obrigatório."})
        if not self.cpf:
            raise ValidationError({"cpf": "O CPF é obrigatório."})
        if not self.telefone:
            raise ValidationError({"telefone": "O contato (telefone) é obrigatório."})

        # US-30322 — dados complementares
        erros = {}
        if self.responsavel_nome:
            self.responsavel_nome = re.sub(r"\s+", " ", self.responsavel_nome).strip()
        # CA-COMP-01: data de nascimento não pode estar no futuro
        if self.data_nascimento and self.data_nascimento > timezone.localdate():
            erros["data_nascimento"] = "A data de nascimento não pode estar no futuro."
        # CA-COMP-02: aluno menor de idade exige nome e telefone do responsável
        elif self.is_menor_de_idade():
            if not self.responsavel_nome:
                erros["responsavel_nome"] = "Informe o responsável: o aluno é menor de idade."
            if not self.responsavel_telefone:
                erros["responsavel_telefone"] = (
                    "Informe o telefone do responsável: o aluno é menor de idade."
                )
        if erros:
            raise ValidationError(erros)

        # CA-CAD-01: unicidade do CPF por professor
        if self.professor_id and self.cpf:
            duplicado = Aluno.objects.filter(
                professor_id=self.professor_id, cpf=self.cpf
            ).exclude(pk=self.pk)
            if duplicado.exists():
                raise ValidationError(
                    {"cpf": "Já existe um aluno cadastrado com este CPF."}
                )

    def is_ativo(self):
        return self.situacao == self.Situacao.ATIVO

    @property
    def idade(self):
        """Idade em anos completos, ou None se a data de nascimento não foi informada."""
        if not self.data_nascimento:
            return None
        hoje = timezone.localdate()
        nascimento = self.data_nascimento
        fez_aniversario = (hoje.month, hoje.day) >= (nascimento.month, nascimento.day)
        return hoje.year - nascimento.year - (0 if fez_aniversario else 1)

    def is_menor_de_idade(self):
        return self.idade is not None and self.idade < IDADE_MAIORIDADE

    @property
    def tem_responsavel(self):
        return any(
            [
                self.responsavel_nome,
                self.responsavel_telefone,
                self.responsavel_email,
                self.responsavel_parentesco,
            ]
        )

    def aulas_futuras_agendadas(self):
        """
        Task 32577 — aulas ainda AGENDADAS a partir de agora.

        Usado para avisar o professor ao inativar o aluno: essas aulas são
        mantidas (CA-ALT-02), mas novos agendamentos ficam bloqueados
        (CA-AGE-02).
        """
        return self.aulas.filter(status="AGENDADA", data_hora_inicio__gte=timezone.now())
