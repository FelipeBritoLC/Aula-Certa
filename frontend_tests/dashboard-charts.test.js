/**
 * Testes unitários de static/js/dashboard-charts.js
 * (US 30355 — Tasks 31773/31774: gráficos de indicadores do painel).
 *
 * O script roda como no navegador: o HTML do painel é montado no jsdom, a
 * biblioteca Chart.js e a API de estatísticas são simuladas, e o arquivo é
 * carregado sem nenhuma alteração.
 */
const path = require("path");

const SCRIPT = path.resolve(__dirname, "../static/js/dashboard-charts.js");

const DADOS_COM_MENSALIDADES = {
  competencia: "2026-10",
  total_mensalidades: 5,
  faturamento_gerado: "1500.00",
  valor_total_pago: "900.00",
  valor_pendente: "600.00",
  total_pendentes: 3,
  total_vencidas: 1,
  indice_inadimplencia: "40.0",
};

let graficos;

function montarPainel({ competencia = "2026-10" } = {}) {
  document.body.innerHTML = `
    <section id="dashboard-charts" data-estatisticas-url="/api/dashboard/estatisticas/" aria-busy="false">
      <input type="month" id="dashboard-competencia" value="${competencia}">
      <p id="dashboard-charts-feedback"></p>
      <div id="dashboard-charts-error" hidden></div>
      <div id="dashboard-charts-empty" hidden></div>
      <div id="dashboard-charts-content" hidden>
        <canvas id="dashboard-financeiro-chart"></canvas>
        <canvas id="dashboard-mensalidades-chart"></canvas>
      </div>
      <p id="dashboard-charts-summary"></p>
    </section>`;
}

function respostaDaApi(dados, ok = true) {
  return Promise.resolve({ ok, json: () => Promise.resolve(dados) });
}

function carregarScript() {
  jest.isolateModules(() => require(SCRIPT));
}

const esperar = () => new Promise((resolver) => setTimeout(resolver, 0));
const el = (id) => document.getElementById(id);

beforeEach(() => {
  graficos = [];
  global.Chart = jest.fn(function (canvas, config) {
    this.canvas = canvas;
    this.config = config;
    this.destroy = jest.fn();
    graficos.push(this);
  });
  global.fetch = jest.fn(() => respostaDaApi(DADOS_COM_MENSALIDADES));
});

afterEach(() => {
  delete global.Chart;
  delete global.fetch;
  document.body.innerHTML = "";
});

describe("carregamento inicial", () => {
  test("consulta a API da competência selecionada", async () => {
    montarPainel({ competencia: "2026-09" });
    carregarScript();
    await esperar();

    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, opcoes] = fetch.mock.calls[0];
    expect(url).toBe("/api/dashboard/estatisticas/?competencia=2026-09");
    expect(opcoes.credentials).toBe("same-origin");
    expect(opcoes.headers.Accept).toBe("application/json");
  });

  test("não faz nada em páginas sem o painel", () => {
    document.body.innerHTML = "<main>Outra página</main>";
    expect(() => carregarScript()).not.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });

  test("marca o painel como ocupado enquanto carrega", () => {
    global.fetch = jest.fn(() => new Promise(() => {}));
    montarPainel();
    carregarScript();
    expect(el("dashboard-charts").getAttribute("aria-busy")).toBe("true");
    expect(el("dashboard-charts-feedback").dataset.state).toBe("loading");
  });
});

describe("competência com mensalidades", () => {
  test("monta o gráfico de barras com faturamento, recebido e pendente", async () => {
    montarPainel();
    carregarScript();
    await esperar();

    const barras = graficos[0];
    expect(barras.canvas).toBe(el("dashboard-financeiro-chart"));
    expect(barras.config.type).toBe("bar");
    expect(barras.config.data.labels).toEqual(["Faturamento", "Recebido", "Pendente"]);
    expect(barras.config.data.datasets[0].data).toEqual([1500, 900, 600]);
  });

  test("monta a rosca com mensalidades pagas, pendentes no prazo e vencidas", async () => {
    montarPainel();
    carregarScript();
    await esperar();

    const rosca = graficos[1];
    expect(rosca.canvas).toBe(el("dashboard-mensalidades-chart"));
    expect(rosca.config.type).toBe("doughnut");
    // 5 mensalidades, 3 pendentes (1 delas vencida) => 2 pagas, 2 no prazo, 1 vencida
    expect(rosca.config.data.datasets[0].data).toEqual([2, 2, 1]);
  });

  test("nunca exibe quantidades negativas na rosca", async () => {
    global.fetch = jest.fn(() =>
      respostaDaApi({ ...DADOS_COM_MENSALIDADES, total_mensalidades: 2, total_pendentes: 3, total_vencidas: 4 })
    );
    montarPainel();
    carregarScript();
    await esperar();
    expect(graficos[1].config.data.datasets[0].data).toEqual([0, 0, 4]);
  });

  test("exibe os gráficos e o resumo acessível em português", async () => {
    montarPainel();
    carregarScript();
    await esperar();

    expect(el("dashboard-charts-content").hidden).toBe(false);
    expect(el("dashboard-charts-empty").hidden).toBe(true);
    expect(el("dashboard-charts-error").hidden).toBe(true);
    expect(el("dashboard-charts").getAttribute("aria-busy")).toBe("false");
    expect(el("dashboard-charts-feedback").dataset.state).toBe("success");
    expect(el("dashboard-charts-feedback").textContent).toBe("Dados de outubro de 2026 atualizados.");

    const resumo = el("dashboard-charts-summary").textContent;
    expect(resumo).toMatch(/faturamento foi R\$\s1\.500,00/);
    expect(resumo).toMatch(/R\$\s900,00 recebidos e R\$\s600,00 pendentes/);
    expect(resumo).toContain("Há 2 mensalidades pagas, 2 pendentes e 1 vencidas.");
  });

  test("formata valores dos eixos e das dicas em reais", async () => {
    montarPainel();
    carregarScript();
    await esperar();

    const opcoesBarras = graficos[0].config.options;
    expect(opcoesBarras.plugins.tooltip.callbacks.label({ parsed: { y: 1234.5 } })).toMatch(/^R\$\s1\.234,50$/);
    expect(opcoesBarras.scales.y.ticks.callback(2000)).toMatch(/^R\$\s2\.000,00$/);

    const dicaRosca = graficos[1].config.options.plugins.tooltip.callbacks.label;
    expect(dicaRosca({ label: "Pagas", parsed: 1200 })).toBe("Pagas: 1.200");
  });
});

describe("competência sem dados", () => {
  test("mostra o estado vazio e não cria gráficos", async () => {
    global.fetch = jest.fn(() =>
      respostaDaApi({ ...DADOS_COM_MENSALIDADES, competencia: "2020-01", total_mensalidades: 0 })
    );
    montarPainel({ competencia: "2020-01" });
    carregarScript();
    await esperar();

    expect(Chart).not.toHaveBeenCalled();
    expect(el("dashboard-charts-empty").hidden).toBe(false);
    expect(el("dashboard-charts-content").hidden).toBe(true);
    expect(el("dashboard-charts-feedback").dataset.state).toBe("empty");
    expect(el("dashboard-charts-summary").textContent).toBe(
      "Não existem dados financeiros para janeiro de 2020."
    );
  });
});

describe("erros", () => {
  test("mostra a mensagem de erro devolvida pela API", async () => {
    global.fetch = jest.fn(() => respostaDaApi({ erro: "Competência deve estar no formato YYYY-MM." }, false));
    montarPainel();
    carregarScript();
    await esperar();

    expect(el("dashboard-charts-error").hidden).toBe(false);
    expect(el("dashboard-charts-error").textContent).toBe("Competência deve estar no formato YYYY-MM.");
    expect(el("dashboard-charts-content").hidden).toBe(true);
    expect(el("dashboard-charts-feedback").dataset.state).toBe("error");
  });

  test("usa mensagem padrão quando a API falha sem explicar", async () => {
    global.fetch = jest.fn(() => respostaDaApi({}, false));
    montarPainel();
    carregarScript();
    await esperar();
    expect(el("dashboard-charts-error").textContent).toBe("Não foi possível consultar os indicadores.");
  });

  test("trata falha de rede", async () => {
    global.fetch = jest.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    montarPainel();
    carregarScript();
    await esperar();
    expect(el("dashboard-charts-error").textContent).toBe("Failed to fetch");
  });

  test("trata falha sem mensagem", async () => {
    global.fetch = jest.fn(() => Promise.reject(new Error("")));
    montarPainel();
    carregarScript();
    await esperar();
    expect(el("dashboard-charts-error").textContent).toBe("Não foi possível carregar os indicadores.");
  });

  test("pede uma competência quando o campo está vazio", async () => {
    montarPainel({ competencia: "" });
    carregarScript();
    await esperar();
    expect(fetch).not.toHaveBeenCalled();
    expect(el("dashboard-charts-error").textContent).toBe("Selecione uma competência válida.");
  });

  test("avisa quando a biblioteca de gráficos não carregou", async () => {
    delete global.Chart;
    montarPainel();
    carregarScript();
    await esperar();
    expect(fetch).not.toHaveBeenCalled();
    expect(el("dashboard-charts-error").textContent).toBe("A biblioteca de gráficos não pôde ser carregada.");
  });
});

describe("troca de competência", () => {
  test("recarrega os dados e substitui os gráficos anteriores", async () => {
    montarPainel();
    carregarScript();
    await esperar();
    const [barrasAntigas, roscaAntiga] = graficos;

    const campo = el("dashboard-competencia");
    campo.value = "2026-08";
    campo.dispatchEvent(new Event("change"));
    await esperar();

    expect(fetch).toHaveBeenLastCalledWith(
      "/api/dashboard/estatisticas/?competencia=2026-08",
      expect.any(Object)
    );
    expect(barrasAntigas.destroy).toHaveBeenCalled();
    expect(roscaAntiga.destroy).toHaveBeenCalled();
    expect(graficos).toHaveLength(4);
  });

  test("ao trocar rápido, cancela a consulta anterior sem exibir erro", async () => {
    let sinalDaPrimeira;
    global.fetch = jest
      .fn()
      .mockImplementationOnce((url, { signal }) => {
        sinalDaPrimeira = signal;
        return new Promise((_, rejeitar) => {
          signal.addEventListener("abort", () => {
            const erro = new Error("The operation was aborted.");
            erro.name = "AbortError";
            rejeitar(erro);
          });
        });
      })
      .mockImplementation(() => respostaDaApi(DADOS_COM_MENSALIDADES));

    montarPainel();
    carregarScript();
    const campo = el("dashboard-competencia");
    campo.value = "2026-11";
    campo.dispatchEvent(new Event("change"));
    await esperar();

    expect(sinalDaPrimeira.aborted).toBe(true);
    expect(el("dashboard-charts-error").hidden).toBe(true);
    expect(el("dashboard-charts-feedback").dataset.state).toBe("success");
  });

  test("um erro depois de gráficos exibidos limpa os gráficos", async () => {
    montarPainel();
    carregarScript();
    await esperar();
    const [barras] = graficos;

    global.fetch.mockImplementation(() => respostaDaApi({ erro: "Falhou" }, false));
    const campo = el("dashboard-competencia");
    campo.value = "2026-07";
    campo.dispatchEvent(new Event("change"));
    await esperar();

    expect(barras.destroy).toHaveBeenCalled();
    expect(el("dashboard-charts-content").hidden).toBe(true);
    expect(el("dashboard-charts-summary").textContent).toBe("Falhou");
  });
});
