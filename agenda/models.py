from datetime import timedelta

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
from django.utils import timezone

from alunos.models import Aluno


class Aula(models.Model):
    """
    US-30332 "Criar agendamento de aula" e US-30338 "Registrar aula realizada".

    Critérios de aceite implementados:
    CA-AGE-01: impede persistência de registros que colidam com o intervalo
               start_time/end_time de uma aula já existente do mesmo professor.
    CA-AGE-02: vinculação obrigatória a um aluno com status = 'ATIVO'.
    CA-AGE-03: impedimento de agendamentos retroativos à data/hora atual.
    CA-REG-01: conteúdo pedagógico com mínimo de 50 caracteres para marcar
               a aula como realizada.
    CA-REG-02: ao registrar a aula, status muda para 'REALIZADA' e o
               timestamp é gravado em data_registro.

    US-30333 "Definir informações da aula agendada":
    CA-DEF-01: modalidade, duração, horário e local podem ser definidos/
               editados enquanto o status for 'AGENDADA'.
    CA-DEF-02: alterar duração ou horário reaplica a validação de conflito
               (CA-AGE-01).
    CA-DEF-03: aulas REALIZADA, CANCELADA ou FALTA não podem ter essas
               informações alteradas.

    US-30339 "Informar detalhes da aula realizada":
    CA-DET-01: material utilizado, avaliação de desempenho e recomendações
               são opcionais e podem ser informados ao registrar a aula ou
               depois, pela tela de detalhes.
    CA-DET-02: esses detalhes só podem ser informados em aulas REALIZADA.
    CA-DET-03: os detalhes aparecem na página da aula e no histórico da
               ficha do aluno.
    """

    # Campos que compõem as "informações da aula" (CA-DEF-01/03).
    CAMPOS_EDITAVEIS = ("data_hora_inicio", "duracao_minutos", "modalidade", "local")

    class Modalidade(models.TextChoices):
        PRESENCIAL = "PRESENCIAL", "Presencial"
        ONLINE = "ONLINE", "Online"

    class Status(models.TextChoices):
        AGENDADA = "AGENDADA", "Agendada"
        REALIZADA = "REALIZADA", "Realizada"
        CANCELADA = "CANCELADA", "Cancelada"
        FALTA = "FALTA", "Falta"

    class Avaliacao(models.TextChoices):
        INSATISFATORIO = "INSATISFATORIO", "Insatisfatório"
        REGULAR = "REGULAR", "Regular"
        BOM = "BOM", "Bom"
        OTIMO = "OTIMO", "Ótimo"

    # US-30339: detalhes complementares, só para aulas REALIZADAS (CA-DET-02).
    CAMPOS_DETALHES = ("material_utilizado", "avaliacao_desempenho", "recomendacoes")

    professor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="aulas"
    )
    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name="aulas")

    data_hora_inicio = models.DateTimeField()
    duracao_minutos = models.PositiveIntegerField(default=60)
    modalidade = models.CharField(
        max_length=12, choices=Modalidade.choices, default=Modalidade.PRESENCIAL
    )
    local = models.CharField(
        max_length=150, blank=True,
        help_text="Endereço (aula presencial) ou link/plataforma (aula online).",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.AGENDADA
    )

    conteudo_trabalhado = models.TextField(blank=True)
    observacoes = models.TextField(blank=True)
    tipo_falta = models.CharField(
        max_length=20, blank=True,
        help_text="JUSTIFICADA ou NAO_JUSTIFICADA, quando status = FALTA.",
    )

    # US-30339 / Task 32581 — detalhes complementares da aula realizada
    material_utilizado = models.TextField(
        blank=True, help_text="Livros, listas de exercícios, links ou recursos usados na aula."
    )
    avaliacao_desempenho = models.CharField(
        max_length=15, choices=Avaliacao.choices, blank=True,
        help_text="Avaliação do desempenho do aluno nesta aula.",
    )
    recomendacoes = models.TextField(
        blank=True, help_text="Tarefas, revisões ou orientações para as próximas aulas."
    )

    motivo_cancelamento = models.CharField(max_length=255, blank=True)
    data_registro = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["data_hora_inicio"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(duracao_minutos__gt=0),
                name="aula_duracao_positiva",
            ),
        ]
        indexes = [
            models.Index(fields=["professor", "data_hora_inicio"], name="idx_aula_professor_data"),
            models.Index(fields=["aluno", "status"], name="idx_aula_aluno_status"),
        ]

    def __str__(self):
        return f"{self.aluno} — {self.data_hora_inicio:%d/%m/%Y %H:%M}"

    @property
    def data_hora_fim(self):
        return self.data_hora_inicio + timedelta(minutes=self.duracao_minutos)

    @property
    def pode_editar(self):
        """CA-DEF-03: somente aulas agendadas têm as informações editáveis."""
        return self.status == self.Status.AGENDADA

    @staticmethod
    def _ate_o_minuto(valor):
        """Os formulários trabalham com precisão de minuto; compara assim."""
        return valor.replace(second=0, microsecond=0) if valor else valor

    def clean(self):
        erros = {}

        # Estado persistido, para saber o que está mudando numa edição.
        original = None
        if not self._state.adding and self.pk:
            original = Aula.objects.filter(pk=self.pk).first()

        horario_alterado = original is None or (
            self._ate_o_minuto(original.data_hora_inicio)
            != self._ate_o_minuto(self.data_hora_inicio)
        )

        # CA-DEF-03: aulas já realizadas/canceladas/com falta não são editáveis
        if original is not None and original.status != self.Status.AGENDADA:
            alterados = [
                campo for campo in self.CAMPOS_EDITAVEIS
                if campo != "data_hora_inicio"
                and getattr(original, campo) != getattr(self, campo)
            ]
            if horario_alterado:
                alterados.append("data_hora_inicio")
            if alterados:
                erros[NON_FIELD_ERRORS] = [
                    "Somente aulas com status Agendada podem ser editadas."
                ]

        # CA-AGE-03: sem horário retroativo — ao criar, ou ao mudar o horário
        # de uma aula agendada (editar só a modalidade de uma aula que já
        # passou, sem mexer no horário, continua permitido).
        if (
            self.status == self.Status.AGENDADA
            and self.data_hora_inicio
            and horario_alterado
            and self.data_hora_inicio < timezone.now()
        ):
            erros["data_hora_inicio"] = "Não é possível agendar uma aula em data/hora retroativa."

        # CA-AGE-02: só se agenda aula nova para aluno ATIVO. Inativar um aluno
        # não pode travar as aulas que ele já tinha (CA-ALT-02): editar ou
        # registrar uma aula existente continua válido.
        if self._state.adding and self.aluno_id and not self.aluno.is_ativo():
            erros["aluno"] = "Só é possível agendar aulas para alunos com situação ATIVO."

        # CA-AGE-01 / CA-DEF-02: conflito de horário para o mesmo professor
        if self.professor_id and self.data_hora_inicio and self.duracao_minutos:
            conflitantes = Aula.objects.filter(
                professor_id=self.professor_id,
                status__in=[self.Status.AGENDADA, self.Status.REALIZADA],
                data_hora_inicio__lt=self.data_hora_fim,
            ).exclude(pk=self.pk)
            for outra in conflitantes:
                if outra.data_hora_fim > self.data_hora_inicio:
                    erros["data_hora_inicio"] = (
                        "Erro: Conflito de horário detectado com outra aula já agendada."
                    )
                    break

        # CA-REG-01: mínimo de 50 caracteres para marcar como REALIZADA
        if self.status == self.Status.REALIZADA:
            conteudo = (self.conteudo_trabalhado or "").strip()
            if len(conteudo) < 50:
                erros["conteudo_trabalhado"] = (
                    "O conteúdo ministrado deve ter pelo menos 50 caracteres."
                )

        # CA-DET-02: detalhes complementares só em aulas realizadas
        if self.status != self.Status.REALIZADA and self.tem_detalhes:
            erros.setdefault(NON_FIELD_ERRORS, []).append(
                "Material, avaliação e recomendações só podem ser informados em aulas realizadas."
            )

        if erros:
            raise ValidationError(erros)

    @property
    def tem_detalhes(self):
        return any(getattr(self, campo) for campo in self.CAMPOS_DETALHES)

    def registrar_como_realizada(
        self,
        conteudo_trabalhado,
        observacoes="",
        material_utilizado="",
        avaliacao_desempenho="",
        recomendacoes="",
    ):
        """Task 31621 — Registrar aula realizada (CA-REG-02)."""
        if self.status != self.Status.AGENDADA:
            raise ValidationError(
                {"status": "Somente aulas agendadas podem ser registradas como realizadas."}
            )

        conteudo_trabalhado = (conteudo_trabalhado or "").strip()
        if len(conteudo_trabalhado) < 50:
            raise ValidationError(
                {
                    "conteudo_trabalhado": (
                        "O conteúdo ministrado deve ter pelo menos 50 caracteres."
                    )
                }
            )

        self.status = self.Status.REALIZADA
        self.conteudo_trabalhado = conteudo_trabalhado
        self.observacoes = (observacoes or "").strip()
        self.material_utilizado = (material_utilizado or "").strip()
        self.avaliacao_desempenho = avaliacao_desempenho or ""
        self.recomendacoes = (recomendacoes or "").strip()
        self.data_registro = timezone.now()
        self.full_clean()
        self.save(
            update_fields=[
                "status",
                "conteudo_trabalhado",
                "observacoes",
                *self.CAMPOS_DETALHES,
                "data_registro",
                "updated_at",
            ]
        )
        return self

    def registrar_falta(self, justificada, observacoes=""):
        """US-30340 — Registrar falta do aluno."""
        if self.status != self.Status.AGENDADA:
            raise ValidationError(
                {"status": "Somente aulas agendadas podem ter falta registrada."}
            )
        self.status = self.Status.FALTA
        self.tipo_falta = "JUSTIFICADA" if justificada else "NAO_JUSTIFICADA"
        self.observacoes = observacoes
        self.data_registro = timezone.now()
        self.save()
        return self
