/**
 * Grava o vídeo de demonstração: site -> interface de anotação -> relatório.
 *
 *   npm i playwright && npx playwright install chromium
 *   node ferramentas/gravar_demo.mjs
 *
 * Escreve docs/video/demo.webm. Nada é encenado: os traces carregados são os
 * mesmos de dados/traces.jsonl, coletados do @Papinha_facil_bot, e a rotulagem
 * usa os atalhos de teclado que o anotador humano usa.
 *
 * PLAYWRIGHT_CHROMIUM define um binário específico; sem ela, o Playwright usa
 * o Chromium que ele mesmo instalou.
 */
import { chromium } from "playwright";
import { readdirSync, renameSync, rmSync, mkdirSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const EXEC = process.env.PLAYWRIGHT_CHROMIUM || undefined;
const SAIDA = join(REPO, "docs", "video");
// O Playwright grava com nome aleatório num diretório que ele controla; usar
// docs/video direto significaria apagá-lo antes de cada gravação, levando junto
// o clipe da coleta. Grava aqui e move só o arquivo desta execução.
const TEMP = join(SAIDA, ".bruto");

const pausa = (ms) => new Promise((r) => setTimeout(r, ms));

/** Rola suave até um elemento e espera assentar — scroll instantâneo fica ilegível em vídeo. */
async function rolar(p, seletor, ms = 1400) {
  await p.evaluate((s) => {
    const el = document.querySelector(s);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, seletor);
  await pausa(ms);
}

async function rolarPx(p, px, ms = 1200) {
  await p.evaluate((y) => window.scrollBy({ top: y, behavior: "smooth" }), px);
  await pausa(ms);
}

rmSync(TEMP, { recursive: true, force: true });
mkdirSync(TEMP, { recursive: true });

const navegador = await chromium.launch({ executablePath: EXEC, args: ["--no-sandbox"] });
const ctx = await navegador.newContext({
  viewport: { width: 1440, height: 810 },
  deviceScaleFactor: 2,
  colorScheme: "dark",   // anotador e relatório seguem o esquema do sistema
  recordVideo: { dir: TEMP, size: { width: 1440, height: 810 } },
});
const p = await ctx.newPage();

// ── 1. a interface de anotação, com os traces reais ─────────────────────────
// Sem passeio pelo site: este clipe é sobre avaliar traces. Quem quer ver o
// site já está nele.
await p.goto(`file://${REPO}/anotar.html`);
// O tema escuro do anotador tem um bloco próprio em html[data-tema] — o
// prefers-color-scheme do contexto não cobre tudo.
await p.evaluate(() => document.documentElement.setAttribute("data-tema", "escuro"));
await p.waitForTimeout(1200);
await p.setInputFiles("#arquivo", `${REPO}/dados/traces.jsonl`);
await p.waitForTimeout(2200);

// lê uma resposta do bot com os termos de risco destacados
await rolarPx(p, 420, 2200);
await rolarPx(p, 420, 2000);

// desce até a grade de rotulagem — é onde o trabalho de fato acontece
await rolar(p, "#rotulos", 2000);

// rotula alguns modos usando os atalhos 1–9, como um humano faria
for (const tecla of ["1", "2", "3"]) {
  await p.keyboard.press(tecla);
  await pausa(700);
}
await pausa(900);
await p.click("#proximo");
await pausa(1600);
await p.keyboard.press("1");
await pausa(700);
await p.keyboard.press("4");
await pausa(1400);
await p.click("#proximo");
await pausa(1800);

// ── 2. o relatório ──────────────────────────────────────────────────────────
await p.goto(`file://${REPO}/docs/relatorio-exemplo.html`);
await p.waitForTimeout(2600);            // número herói: precisão dos avaliadores
await rolarPx(p, 620, 2400);
await rolarPx(p, 620, 2400);
await rolarPx(p, 700, 2600);
await pausa(1200);

await ctx.close();
await navegador.close();

const arq = readdirSync(TEMP).find((f) => f.endsWith(".webm"));
renameSync(join(TEMP, arq), join(SAIDA, "demo.webm"));
rmSync(TEMP, { recursive: true, force: true });
console.log("gravado:", join(SAIDA, "demo.webm"));
