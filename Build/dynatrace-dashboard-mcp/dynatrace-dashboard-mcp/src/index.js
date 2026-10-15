import { McpServer } from '@modelcontextprotocol/server';
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import * as z from 'zod/v4';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const execFileAsync = promisify(execFile);
const BIN = process.env.DTCTL_BIN || 'dtctl';
// Evita habilitar acidentalmente um contexto de escrita diferente.
const CONTEXT = process.env.DTCTL_CONTEXT || '';

async function dtctl(...args) {
  const globalArgs = CONTEXT ? ['--context', CONTEXT] : [];
  // Sem shell, para não interpretar comandos ou caracteres da DQL.
  try {
    const { stdout, stderr } = await execFileAsync(
      BIN,
      [...globalArgs, ...args, '--plain', '--no-agent'],
      { timeout: 120_000, maxBuffer: 8 * 1024 * 1024, windowsHide: true }
    );
    return stdout.trim() || stderr.trim() || 'Comando concluído.';
  } catch (err) {
    const message = [err.message, err.stdout, err.stderr].filter(Boolean).join('\n');
    throw new Error(`Falha no dtctl: ${message}`);
  }
}

function result(text, isError = false) {
  return { content: [{ type: 'text', text: String(text) }], ...(isError ? { isError: true } : {}) };
}

function protect(fn) {
  return async (args) => {
    try {
      return result(await fn(args));
    } catch (err) {
      return result(err instanceof Error ? err.message : String(err), true);
    }
  };
}

function ensureDashboard(document) {
  if (!document || typeof document !== 'object' || Array.isArray(document)) {
    throw new Error('Esperava um dashboard JSON retornado por dtctl.');
  }
  if (document.type && document.type !== 'dashboard') {
    throw new Error('O documento não é do tipo dashboard.');
  }
  const c = document.content;
  if (!c || typeof c !== 'object' || Array.isArray(c)
      || !c.tiles || !c.layouts || !Array.isArray(c.variables)) {
    throw new Error('JSON sem content.tiles/layouts/variables. Confira `dtctl get dashboard <id> -o json`.');
  }
  return document;
}

const UNSAFE_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

// Mescla objetos recursivamente; arrays e valores escalares são substituídos (ex.: colorRules).
function deepMerge(base, patch) {
  const out = isPlainObject(base) ? { ...base } : {};
  for (const [key, value] of Object.entries(patch)) {
    if (UNSAFE_KEYS.has(key)) continue;
    out[key] = isPlainObject(value) ? deepMerge(out[key], value) : value;
  }
  return out;
}

async function applyDashboard(payload, confirmed, details = '') {
  const dir = await mkdtemp(join(tmpdir(), 'dynatrace-dashboard-mcp-'));
  const file = join(dir, 'dashboard.json');
  try {
    await writeFile(file, JSON.stringify(payload, null, 2), { mode: 0o600 });
    const preview = await dtctl('apply', '-f', file, '--dry-run');
    if (!confirmed) {
      return `PRÉVIA — nada foi publicado.\n${preview}${details ? `\n\n${details}` : ''}\n\nPara publicar, repita a chamada com confirm=true.`;
    }
    const deployed = await dtctl('apply', '-f', file);
    return `PUBLICADO\n${deployed}`;
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

const layoutSchema = z.object({
  x: z.number().int().min(0).max(23).optional(),
  y: z.number().int().min(0).optional(),
  w: z.number().int().min(1).max(24).optional(),
  h: z.number().int().min(1).max(50).optional(),
});

function buildServer() {
  const server = new McpServer({ name: 'dynatrace-dashboard-local', version: '0.1.0' });

  server.registerTool('list_dashboards', {
    description: 'Lista dashboards do ambiente Dynatrace conectado via dtctl, com IDs e nomes.',
  }, protect(async () => dtctl('get', 'dashboards', '-o', 'json')));

  server.registerTool('get_dashboard', {
    description: 'Lê o JSON COMPLETO de um dashboard pelo ID. Sempre use antes de atualizar.',
    inputSchema: z.object({ dashboardId: z.string().min(1) }),
  }, protect(async ({ dashboardId }) => dtctl('get', 'dashboard', dashboardId, '-o', 'json')));

  server.registerTool('run_dql', {
    description: 'Executa DQL no ambiente conectado para verificar campos e testar queries ANTES de montar tiles. Pode consumir recursos/custos Grail. Evite grandes consultas sem limite.',
    inputSchema: z.object({ dql: z.string().min(1) }),
  }, protect(async ({ dql }) => dtctl('query', dql, '-o', 'json')));

  server.registerTool('create_dashboard', {
    description: 'Cria NOVO dashboard no formato Latest Dynatrace. Recebe content com version, variables, tiles e layouts. Primeiro use confirm=false para prévia; confirm=true publica.',
    inputSchema: z.object({
      name: z.string().min(1),
      content: z.record(z.string(), z.unknown()),
      confirm: z.boolean().default(false),
    }),
  }, protect(async ({ name, content, confirm }) => {
    if (!Number.isInteger(content.version) || !Array.isArray(content.variables)
        || !content.tiles || !content.layouts) {
      throw new Error('content precisa conter version:21, variables:[], tiles:{}, layouts:{}.');
    }
    const dashboard = ensureDashboard({ name, type: 'dashboard', content });
    return applyDashboard(dashboard, confirm);
  }));

  server.registerTool('upsert_dashboard_tile', {
    description: 'Adiciona ou altera um tile em um dashboard EXISTENTE. Baixa sempre o JSON atual e preserva outros tiles, layouts, variáveis e metadados. O ID é opcional para novos tiles. '
      + 'Tiles data aceitam visualizationSettings (ex.: coloring.colorRules, table, singleValue, unitsOverrides) e querySettings. '
      + 'Por padrão (settingsMode=merge) esses objetos são mesclados recursivamente com os atuais; arrays como colorRules são substituídos inteiros. Use settingsMode=replace para sobrescrever. '
      + 'Prévia por padrão (confirm=false), exibindo o tile resultante.',
    inputSchema: z.object({
      dashboardId: z.string().min(1),
      tileId: z.string().regex(/^[a-zA-Z0-9_-]+$/).optional(),
      kind: z.enum(['data', 'markdown']),
      title: z.string().optional(),
      query: z.string().optional(),
      visualization: z.string().optional(),
      visualizationSettings: z.record(z.string(), z.unknown()).optional()
        .describe('Somente tiles data. Ex.: {"coloring":{"colorRules":[{"field":"Uso (%)","comparator":"≥","value":80,"type":"double","colorMode":"custom-color","customColor":{"Default":"var(--dt-colors-charts-status-warning-default, #eea53c)"}}]}}'),
      querySettings: z.record(z.string(), z.unknown()).optional()
        .describe('Somente tiles data. Ex.: {"maxResultRecords":1000,"defaultScanLimitGbytes":500}'),
      settingsMode: z.enum(['merge', 'replace']).default('merge')
        .describe('merge: mescla com as configurações atuais do tile. replace: substitui o objeto inteiro.'),
      markdown: z.string().optional(),
      layout: layoutSchema.optional(),
      confirm: z.boolean().default(false),
    }),
  }, protect(async ({ dashboardId, tileId, kind, title, query, visualization, visualizationSettings, querySettings, settingsMode, markdown, layout, confirm }) => {
    const dashboard = ensureDashboard(JSON.parse(await dtctl('get', 'dashboard', dashboardId, '-o', 'json')));
    if (!dashboard.id || dashboard.id !== dashboardId) {
      throw new Error('O JSON exportado não possui o mesmo ID solicitado. Atualização interrompida.');
    }
    const content = dashboard.content;
    const id = tileId || String(Math.max(0, ...Object.keys(content.tiles).filter(v => /^\d+$/.test(v)).map(Number)) + 1);
    const old = content.tiles[id];
    if (old && old.type !== kind) {
      throw new Error('Mudança de tipo de tile não é suportada pelo MVP. Escolha outro ID.');
    }
    let tile;
    if (kind === 'markdown') {
      if (visualizationSettings !== undefined || querySettings !== undefined) {
        throw new Error('visualizationSettings/querySettings só se aplicam a tiles data.');
      }
      tile = { ...(old || {}), type: 'markdown' };
      if (markdown !== undefined) tile.content = markdown;
      if (typeof tile.content !== 'string') throw new Error('Forneça markdown para tile novo.');
    } else {
      tile = { ...(old || {}), type: 'data' };
      if (title !== undefined) tile.title = title;
      if (query !== undefined) tile.query = query;
      if (visualization !== undefined) tile.visualization = visualization;
      const applySettings = (current, patch) => {
        if (patch === undefined) return current ?? {};
        return settingsMode === 'replace' ? deepMerge({}, patch) : deepMerge(current, patch);
      };
      tile.querySettings = applySettings(tile.querySettings, querySettings);
      tile.visualizationSettings = applySettings(tile.visualizationSettings, visualizationSettings);
      if (!tile.title || !tile.query || !tile.visualization) {
        throw new Error('Um tile data precisa de title, query e visualization.');
      }
    }
    const oldLayout = content.layouts[id];
    const bottom = Math.max(0, ...Object.values(content.layouts)
      .filter(l => l && typeof l.y === 'number' && typeof l.h === 'number')
      .map(l => l.y + l.h));
    const nextLayout = { ...(oldLayout || { x: 0, y: bottom, w: 24, h: kind === 'markdown' ? 2 : 8 }), ...(layout || {}) };
    if (nextLayout.x + nextLayout.w > 24) throw new Error('Layout ultrapassa 24 colunas.');
    content.tiles[id] = tile;
    content.layouts[id] = nextLayout;
    const details = `Tile resultante (${old ? 'alterado' : 'novo'}):\n${JSON.stringify({ tile, layout: nextLayout }, null, 2)}`;
    return `Tile: ${id}\n` + await applyDashboard(dashboard, confirm, details);
  }));

  return server;
}

void serveStdio(buildServer);
console.error('Dynatrace Dashboard MCP iniciado (stdio).');
