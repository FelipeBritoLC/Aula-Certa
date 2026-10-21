/**
 * Testes unitários de static/js/contador-caracteres.js
 * (US 30338 — Task 31621, CA-REG-01: mínimo de 50 caracteres no conteúdo
 * da aula realizada, com contador e botão Concluir bloqueado).
 */
const { configurarContador, iniciar } = require("../static/js/contador-caracteres.js");

function montarFormulario({ valor = "", minimo = 50, comBotao = true } = {}) {
  document.body.innerHTML = `
    <textarea id="id_conteudo" data-contador-minimo="${minimo}"
              data-contador-alvo="conteudo-contador" data-contador-botao="btn-concluir">${valor}</textarea>
    <div id="conteudo-contador">0/50 caracteres</div>
    ${comBotao ? '<button id="btn-concluir" disabled>Concluir</button>' : ""}`;
  return {
    campo: document.getElementById("id_conteudo"),
    contador: document.getElementById("conteudo-contador"),
    botao: document.getElementById("btn-concluir"),
  };
}

function digitar(campo, texto) {
  campo.value = texto;
  campo.dispatchEvent(new Event("input"));
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("configurarContador", () => {
  test("mostra a contagem inicial e mantém o botão bloqueado", () => {
    const { campo, contador, botao } = montarFormulario();
    configurarContador(campo, contador, botao, 50);
    expect(contador.textContent).toBe("0/50 caracteres");
    expect(contador.classList.contains("text-danger")).toBe(true);
    expect(botao.disabled).toBe(true);
  });

  test("atualiza a contagem enquanto o professor digita", () => {
    const { campo, contador, botao } = montarFormulario();
    configurarContador(campo, contador, botao, 50);
    digitar(campo, "Revisão de frações");
    expect(contador.textContent).toBe("18/50 caracteres");
    expect(botao.disabled).toBe(true);
  });

  test("libera o botão ao atingir exatamente o mínimo", () => {
    const { campo, contador, botao } = montarFormulario();
    configurarContador(campo, contador, botao, 50);
    digitar(campo, "a".repeat(49));
    expect(botao.disabled).toBe(true);
    digitar(campo, "a".repeat(50));
    expect(botao.disabled).toBe(false);
    expect(contador.classList.contains("text-success")).toBe(true);
    expect(contador.classList.contains("text-danger")).toBe(false);
  });

  test("ignora espaços nas pontas, como o servidor", () => {
    const { campo, contador, botao } = montarFormulario();
    configurarContador(campo, contador, botao, 50);
    digitar(campo, `   ${"a".repeat(45)}        `);
    expect(contador.textContent).toBe("45/50 caracteres");
    expect(botao.disabled).toBe(true);
  });

  test("volta a bloquear se o texto for apagado", () => {
    const { campo, contador, botao } = montarFormulario();
    configurarContador(campo, contador, botao, 50);
    digitar(campo, "a".repeat(60));
    digitar(campo, "a".repeat(10));
    expect(botao.disabled).toBe(true);
    expect(contador.classList.contains("text-danger")).toBe(true);
  });

  test("considera texto já preenchido (ex.: formulário devolvido com erro)", () => {
    const { campo, contador, botao } = montarFormulario({ valor: "b".repeat(70) });
    const atualizar = configurarContador(campo, contador, botao, 50);
    expect(contador.textContent).toBe("70/50 caracteres");
    expect(botao.disabled).toBe(false);
    expect(atualizar()).toBe(true);
  });

  test("funciona sem botão associado", () => {
    const { campo, contador } = montarFormulario({ comBotao: false });
    configurarContador(campo, contador, null, 5);
    digitar(campo, "abcdef");
    expect(contador.textContent).toBe("6/5 caracteres");
  });
});

describe("iniciar", () => {
  test("liga os campos marcados com data-contador-minimo", () => {
    const { campo, contador, botao } = montarFormulario();
    expect(iniciar(document)).toBe(1);
    digitar(campo, "c".repeat(50));
    expect(contador.textContent).toBe("50/50 caracteres");
    expect(botao.disabled).toBe(false);
  });

  test("ignora campo com mínimo inválido ou sem contador", () => {
    const { campo, contador } = montarFormulario({ minimo: "abc" });
    iniciar(document);
    digitar(campo, "texto");
    expect(contador.textContent).toBe("0/50 caracteres");
  });

  test("não faz nada em páginas sem campos marcados", () => {
    document.body.innerHTML = "<form></form>";
    expect(iniciar(document)).toBe(0);
  });
});
