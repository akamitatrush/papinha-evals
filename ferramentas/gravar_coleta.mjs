/**
 * Etapa 2 — grava a COLETA: o sistema conversando com o @Papinha_facil_bot.
 *
 * Não é encenação. As consultas saem de dados/consultas.jsonl (as que ainda não
 * foram coletadas) e as respostas viram traces novos, no mesmo formato dos
 * outros. O vídeo é o registro do trabalho acontecendo.
 *
 * Reusa o perfil autenticado da etapa 1 — o QR e a tela de login não entram no
 * arquivo. Antes do primeiro quadro esconde a lista de conversas: o vídeo vai
 * para um site público e a agenda do dono da conta não tem o que fazer lá.
 *
 * Toda mensagem é rastreada por `data-mid`. Ler "o último balão da tela" era o
 * bug da primeira versão: quando o envio falhava em silêncio, ela capturava a
 * resposta ANTERIOR e gravava como se fosse nova. Aqui, sem mid maior que o de
 * antes do envio, o trace não é escrito.
 */
import { chromium } from "playwright";
import { readdirSync, renameSync, rmSync, mkdirSync, readFileSync, appendFileSync } from "node:fs";
import { join } from "node:path";

const REPO   = "/home/akametatron/Generic/papinha-evals";
const PERFIL = "/tmp/claude-1000/-home-akametatron-Generic/33f8e222-8f38-4b05-9bca-b0285457373d/scratchpad/tg-perfil";
const SAIDA  = "/tmp/claude-1000/-home-akametatron-Generic/33f8e222-8f38-4b05-9bca-b0285457373d/scratchpad/video-tg";
const EXEC   = "/home/akametatron/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome";
const BOT    = "Papinha_facil_bot";

// q011: pergunta sem idade — exercita F06 (assume idade não informada).
// q032: restrição declarada — F05, um dos modos que ainda não tinha ocorrência.
const ESCOLHIDAS = ["q011", "q032"];

const linhas = (p) =>
  readFileSync(p, "utf8").split("\n").filter((l) => l.trim() && !l.startsWith("//"))
    .map((l) => JSON.parse(l));

const consultas = linhas(`${REPO}/dados/consultas.jsonl`);
const traces = linhas(`${REPO}/dados/traces.jsonl`);
const feitos = new Set(traces.map((t) => t.query_id));
const fila = ESCOLHIDAS.map((id) => consultas.find((c) => c.id === id))
  .filter((c) => c && !feitos.has(c.id));

if (!fila.length) {
  console.log("nada a coletar — as escolhidas já estão em traces.jsonl");
  process.exit(0);
}
let proximo = Math.max(...traces.map((t) => +String(t.id).replace(/\D/g, "") || 0)) + 1;

const pausa = (ms) => new Promise((r) => setTimeout(r, ms));

const MASCARA = `
  #column-left, .sidebar-left, #column-right, .sidebar-right { display:none !important; }
`;

rmSync(SAIDA, { recursive: true, force: true });
mkdirSync(SAIDA, { recursive: true });

const ctx = await chromium.launchPersistentContext(PERFIL, {
  executablePath: EXEC, headless: true, args: ["--no-sandbox"],
  viewport: { width: 1440, height: 810 }, locale: "pt-BR",
  recordVideo: { dir: SAIDA, size: { width: 1440, height: 810 } },
});
const p = ctx.pages()[0] || (await ctx.newPage());

await p.goto(`https://web.telegram.org/k/#@${BOT}`, { waitUntil: "domcontentloaded" });
await p.addStyleTag({ content: MASCARA }).catch(() => {});
await pausa(11000);
await p.addStyleTag({ content: MASCARA }).catch(() => {});
await pausa(2500);

// Dois divs casam com `.input-message-input`: o editável de verdade — que, por
// razões do Telegram, carrega a classe `forwards` — e um espelho de opacidade
// zero usado só para medir altura (`.input-field-input-fake`). O espelho fica
// por cima e engole o clique, então ele é quem precisa sair do caminho.
const CAMPO = '#column-center div.input-message-input[contenteditable="true"]'
            + ':not(.input-field-input-fake)';
await p.waitForSelector(CAMPO, { timeout: 45000 });
await p.addStyleTag({ content: ".input-field-input-fake{pointer-events:none !important}" })
       .catch(() => {});

/** Maior data-mid presente — a régua para saber o que é mensagem nova. */
const maiorMid = () =>
  p.evaluate(() =>
    [...document.querySelectorAll(".bubbles .bubble[data-mid]")]
      .reduce((m, b) => Math.max(m, +b.dataset.mid || 0), 0)
  ).catch(() => 0);

/** Texto do balão recebido mais novo, desde que seu mid passe da régua. */
const respostaApos = (mid) =>
  p.evaluate((corte) => {
    const novos = [...document.querySelectorAll(".bubbles .bubble.is-in[data-mid]")]
      .filter((b) => +b.dataset.mid > corte)
      .sort((a, b) => +a.dataset.mid - +b.dataset.mid);
    if (!novos.length) return "";
    return (novos[novos.length - 1].querySelector(".message")?.innerText || "").trim();
  }, mid).catch(() => "");

const novos = [];
for (const c of fila) {
  const regua = await maiorMid();

  await p.click(CAMPO);
  await p.keyboard.type(c.texto, { delay: 42 });          // digitação visível no vídeo
  await pausa(800);

  // Confere que o texto entrou no campo antes de mandar. Se o foco tiver
  // escapado, a digitação some no vazio e o Enter não envia nada.
  const noCampo = await p.evaluate((s) => document.querySelector(s)?.innerText || "", CAMPO);
  if (!noCampo.includes(c.texto.slice(0, 20))) {
    console.log(`${c.id}: campo vazio depois de digitar — abortado`);
    novos.push({ query_id: c.id, output: "" });
    continue;
  }
  await p.keyboard.press("Enter");

  // 1) confirma que a MINHA mensagem entrou — sem isso nada mais faz sentido
  const enviouAte = Date.now() + 20000;
  let enviou = false;
  while (Date.now() < enviouAte) {
    if ((await maiorMid()) > regua) { enviou = true; break; }
    await pausa(700);
  }
  if (!enviou) {
    console.log(`${c.id}: ENVIO FALHOU — nada gravado`);
    novos.push({ query_id: c.id, output: "" });
    continue;
  }

  // 2) espera a resposta e o texto parar de crescer (o bot escreve em streaming)
  const limite = Date.now() + 100000;
  let ant = "", estavel = 0;
  while (Date.now() < limite && estavel < 4) {
    await pausa(1000);
    const at = await respostaApos(regua);
    if (at && at === ant) estavel++; else { estavel = 0; ant = at; }
  }

  novos.push({
    id: `t${proximo++}`, query_id: c.id, origem: "real",
    idade_meses: c.idade_meses ?? null, restricoes: c.restricoes ?? [],
    input: c.texto, output: await respostaApos(regua), nota: "",
  });
  await pausa(3000);   // deixa a resposta respirar em tela antes da próxima
}

await ctx.close();

const vistos = new Set();
for (const t of novos) {
  if (!t.output) { console.log(`${t.query_id}: SEM RESPOSTA — não gravado`); continue; }
  if (vistos.has(t.output)) { console.log(`${t.query_id}: RESPOSTA DUPLICADA — não gravado`); continue; }
  vistos.add(t.output);
  appendFileSync(`${REPO}/dados/traces.jsonl`, JSON.stringify(t) + "\n");
  console.log(`${t.id} (${t.query_id}) ${t.output.length} chars · ${t.output.slice(0, 70).replace(/\n/g, " ")}…`);
}

const arq = readdirSync(SAIDA).find((f) => f.endsWith(".webm"));
if (arq) renameSync(join(SAIDA, arq), join(SAIDA, "coleta.webm"));
console.log("gravado:", join(SAIDA, "coleta.webm"));
