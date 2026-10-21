"""
Configuração compartilhada dos testes (US-30358).

As fixtures abaixo valem para qualquer arquivo de teste; os módulos que
definem fixtures com o mesmo nome continuam usando as suas.
"""
import pytest
from django.contrib.auth.models import User


@pytest.fixture(autouse=True)
def _hasher_de_senha_rapido(settings):
    """O hasher padrão (PBKDF2) é lento de propósito; nos testes não precisa ser."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def professor(db):
    return User.objects.create_user(username="prof1", password="senha123")


@pytest.fixture
def outro_professor(db):
    return User.objects.create_user(username="prof2", password="senha123")


@pytest.fixture
def logado(client, professor):
    client.force_login(professor)
    return client
