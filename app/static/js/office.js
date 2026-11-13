/**
 * office.js — AgentOffice 2D Pixel Art Canvas Virtual Office Engine
 * Built with authentic pixel-art assets from pablodelucca/pixel-agents.
 * Real tiled parquet, ceramic, carpets, pixel-art desks, CRT monitors,
 * animated character spritesheets, direct 1-on-1 chat interaction,
 * AND Interactive Office Decoration Mode (Office Designer & Sandbox Editor).
 * @module office
 */

import API from './api.js';

// ── 15 Agent Definitions with Specific Pixel-Art Characters ────────────────

/**
 * @typedef {{
 *   id: string,
 *   name: string,
 *   fullName: string,
 *   zone: 'executive'|'strategy'|'dev'|'qa'|'ciso',
 *   room: string,
 *   x: number,
 *   y: number,
 *   charIndex: number,
 *   icon: string,
 *   color: string,
 *   description: string,
 *   roleBadge: string
 * }} AgentDef
 */

/** @type {AgentDef[]} */
export const AGENTS = [
  // ── Executive Suite (Top-Left) ──
  { id: 'agente_00_ceo',             name: 'CEO',         fullName: 'Director Ejecutivo',                 zone: 'executive', room: 'executive', x: 180, y: 130, charIndex: 0, icon: '👑', color: '#d4aa00', description: 'Capital Allocator & Governor Zero-Touch', roleBadge: 'EXECUTIVE LEAD' },
  { id: 'agente_01_pm',              name: 'PM',          fullName: 'Project Manager',                    zone: 'executive', room: 'executive', x: 380, y: 130, charIndex: 1, icon: '📋', color: '#53d8fb', description: 'Sprint Coordinator & Backlog Master',  roleBadge: 'SCRUM MASTER' },

  // ── Bullpen Ingeniería & UI/UX (Bottom-Left) ──
  { id: 'agente_03_laravel',         name: 'Dev Laravel', fullName: 'Laravel Developer',                  zone: 'dev',       room: 'dev',       x: 100, y: 400, charIndex: 3, icon: '🐘', color: '#ff4f1f', description: 'PHP/Laravel Backend Specialist',         roleBadge: 'BACKEND PHP' },
  { id: 'agente_04_fastapi',         name: 'Dev FastAPI', fullName: 'FastAPI Developer',                  zone: 'dev',       room: 'dev',       x: 230, y: 400, charIndex: 5, icon: '⚡', color: '#00c896', description: 'Python/FastAPI Backend Specialist',      roleBadge: 'BACKEND PYTHON' },
  { id: 'agente_11_ui_ux',           name: 'UI/UX',       fullName: 'Principal UI/UX Designer',           zone: 'dev',       room: 'dev',       x: 165, y: 520, charIndex: 4, icon: '🎨', color: '#bc8cff', description: 'Interface Design & Ergonomics',          roleBadge: 'PRODUCT DESIGN' },

  // ── Estrategia, Docs & Growth (Bottom-Center) ──
  { id: 'agente_02_architect',       name: 'Arquitecto',  fullName: 'Software Architect',                 zone: 'strategy',  room: 'strategy',  x: 410, y: 400, charIndex: 2, icon: '🏛', color: '#8b949e', description: 'System Design & Technical Architecture', roleBadge: 'CHIEF ARCHITECT' },
  { id: 'agente_08_docs',            name: 'Docs & RAG',  fullName: 'Documentation & RAG Specialist',    zone: 'strategy',  room: 'strategy',  x: 550, y: 400, charIndex: 1, icon: '📚', color: '#58a6ff', description: 'Documentation & Knowledge Base RAG',    roleBadge: 'RAG & DOCS' },
  { id: 'agente_09_growth',          name: 'Growth',      fullName: 'Growth Hacker',                      zone: 'strategy',  room: 'strategy',  x: 380, y: 520, charIndex: 5, icon: '📈', color: '#3fb950', description: 'Growth Strategy & Funnel Optimization',roleBadge: 'GROWTH HACKER' },
  { id: 'agente_12_marketing',       name: 'Marketing',   fullName: 'Marketing Strategist',               zone: 'strategy',  room: 'strategy',  x: 480, y: 520, charIndex: 1, icon: '📣', color: '#f5a623', description: 'TOFU Content & Acquisition Strategy',   roleBadge: 'MARKETING LEAD' },
  { id: 'agente_13_sales_analytics', name: 'Sales BI',    fullName: 'Sales & Business Intelligence',      zone: 'strategy',  room: 'strategy',  x: 580, y: 520, charIndex: 2, icon: '💹', color: '#3fb950', description: 'Sales Funnel & Unit Economics Analytics', roleBadge: 'BUSINESS INTEL' },

  // ── Laboratorio QA & CI/CD (Bottom-Right Upper) ──
  { id: 'agente_05_qa_php',          name: 'QA PHP',      fullName: 'QA Engineer PHP',                    zone: 'qa',        room: 'qa',        x: 740, y: 400, charIndex: 0, icon: '🔬', color: '#bc8cff', description: 'PHP Pest Testing & Quality Gate',      roleBadge: 'QA AUTOMATION' },
  { id: 'agente_06_qa_python',       name: 'QA Python',   fullName: 'QA Engineer Python',                 zone: 'qa',        room: 'qa',        x: 835, y: 400, charIndex: 2, icon: '🐍', color: '#ffd700', description: 'Python Pytest & Async Verification',   roleBadge: 'TEST & VERIFY' },
  { id: 'agente_14_qa_ui_ux',        name: 'QA UI/UX',    fullName: 'Lead UI/UX QA Auditor',              zone: 'qa',        room: 'qa',        x: 930, y: 400, charIndex: 4, icon: '🎯', color: '#06b6d4', description: 'Visual Quality & Usability Quality Gate', roleBadge: 'UI/UX AUDITOR' },

  // ── Búnker CISO & Servidores DevOps (Bottom-Right Lower) ──
  { id: 'agente_10_ciso',            name: 'CISO',        fullName: 'Chief Information Security Officer', zone: 'ciso',      room: 'ciso',      x: 770, y: 530, charIndex: 3, icon: '🛡', color: '#f85149', description: 'Cybersecurity & Compliance Gatekeeper', roleBadge: 'SECURITY AUDIT' },
  { id: 'agente_07_devops',          name: 'DevOps',      fullName: 'DevOps Engineer',                    zone: 'ciso',      room: 'ciso',      x: 880, y: 530, charIndex: 5, icon: '⚙', color: '#3fb950', description: 'Docker Infrastructure & CI/CD Pipelines',roleBadge: 'INFRA & CI/CD' },
];

/** Default factory coordinates for agents (used on reset) */
const DEFAULT_AGENT_COORDS = {
  agente_00_ceo:             { x: 180, y: 130 },
  agente_01_pm:              { x: 380, y: 130 },
  agente_03_laravel:         { x: 100, y: 400 },
  agente_04_fastapi:         { x: 230, y: 400 },
  agente_11_ui_ux:           { x: 165, y: 520 },
  agente_02_architect:       { x: 410, y: 400 },
  agente_08_docs:            { x: 550, y: 400 },
  agente_09_growth:          { x: 380, y: 520 },
  agente_12_marketing:       { x: 480, y: 520 },
  agente_13_sales_analytics: { x: 580, y: 520 },
  agente_05_qa_php:          { x: 740, y: 400 },
  agente_06_qa_python:       { x: 835, y: 400 },
  agente_14_qa_ui_ux:        { x: 930, y: 400 },
  agente_10_ciso:            { x: 770, y: 530 },
  agente_07_devops:          { x: 880, y: 530 },
};

// ── Pipeline Stepper Stages ────────────────────────────────────────────────

export const PIPELINE_STEPS = [
  { id: 'step-ceo-charter', agentId: 'agente_00_ceo',       label: '1. CEO Charter',       icon: '👑' },
  { id: 'step-pm',          agentId: 'agente_01_pm',        label: '2. Sprint Backlog',    icon: '📋' },
  { id: 'step-arch',        agentId: 'agente_02_architect', label: '3. Arquitectura',      icon: '🏛' },
  { id: 'step-uiux',        agentId: 'agente_11_ui_ux',     label: '4. UI/UX Design',      icon: '🎨' },
  { id: 'step-uiux-qa',     agentId: 'agente_14_qa_ui_ux',  label: '5. Auditoría UI/UX',   icon: '🎯' },
  { id: 'step-dev-php',     agentId: 'agente_03_laravel',   label: '6. Dev Backend PHP',   icon: '🐘' },
  { id: 'step-dev-py',      agentId: 'agente_04_fastapi',   label: '7. Dev Backend Py',    icon: '⚡' },
  { id: 'step-qa',          agentId: 'agente_05_qa_php',    label: '8. QA & Testing',      icon: '🔬' },
  { id: 'step-ciso',        agentId: 'agente_10_ciso',      label: '9. Auditoría CISO',    icon: '🛡' },
  { id: 'step-devops',      agentId: 'agente_07_devops',    label: '10. Docker Deploy',    icon: '⚙' },
  { id: 'step-docs',        agentId: 'agente_08_docs',      label: '11. Docs & RAG Base',  icon: '📚' },
  { id: 'step-mktg',        agentId: 'agente_12_marketing', label: '12. Marketing TOFU',   icon: '📣' },
  { id: 'step-sales',       agentId: 'agente_13_sales_analytics', label: '13. Sales BI',   icon: '💹' },
  { id: 'step-growth',      agentId: 'agente_09_growth',    label: '14. Growth Strategy',  icon: '📈' },
  { id: 'step-signoff',     agentId: 'agente_00_ceo',       label: '15. CEO Sign-off',     icon: '✅' },
];

// ── Decoration Catalog & Editable Props ────────────────────────────────────

/**
 * @typedef {{
 *   type: string,
 *   label: string,
 *   category: 'furniture'|'tech'|'decor'|'breakroom'|'agents',
 *   w: number,
 *   h: number,
 *   imgKey: string,
 *   icon: string,
 *   description?: string
 * }} CatalogItem
 */

export const DECOR_CATALOG = [
  // 🪑 Mobiliario
  { type: 'desk',             label: 'Escritorio',      category: 'furniture', w: 64, h: 42, imgKey: 'desk',             icon: '🪑', description: 'Puesto de trabajo estándar con madera cálida' },
  { type: 'chairFront',       label: 'Silla Azul',      category: 'furniture', w: 24, h: 32, imgKey: 'chairFront',       icon: '💺', description: 'Silla ergonómica acolchada azul' },
  { type: 'chairBack',        label: 'Silla Espalda',   category: 'furniture', w: 24, h: 32, imgKey: 'chairBack',        icon: '💺', description: 'Silla acolchada vista trasera' },
  { type: 'chairSide',        label: 'Silla Lateral',   category: 'furniture', w: 24, h: 32, imgKey: 'chairSide',        icon: '💺', description: 'Silla acolchada perfil' },
  { type: 'woodenChairFront', label: 'Silla Madera',    category: 'furniture', w: 24, h: 32, imgKey: 'woodenChairFront', icon: '🪑', description: 'Silla rústica de madera noble' },
  { type: 'sofaFront',        label: 'Sofá Frontal',    category: 'furniture', w: 48, h: 32, imgKey: 'sofaFront',        icon: '🛋️', description: 'Sofá lounge ejecutivo' },
  { type: 'sofaSide',         label: 'Sofá Lateral',    category: 'furniture', w: 32, h: 48, imgKey: 'sofaSide',         icon: '🛋️', description: 'Sofá lounge perfil' },
  { type: 'coffeeTable',      label: 'Mesa Centro',     category: 'furniture', w: 32, h: 24, imgKey: 'coffeeTable',      icon: '🪵', description: 'Mesa baja de café' },
  { type: 'smallTable',       label: 'Mesa Auxiliar',   category: 'furniture', w: 32, h: 32, imgKey: 'smallTable',       icon: '🪵', description: 'Mesa auxiliar para lámpara o café' },
  { type: 'bookshelf',        label: 'Estantería',      category: 'furniture', w: 32, h: 44, imgKey: 'bookshelf',        icon: '📚', description: 'Estantería vertical con libros' },
  { type: 'doubleBook',       label: 'Biblioteca Doble',category: 'furniture', w: 48, h: 48, imgKey: 'doubleBook',       icon: '📖', description: 'Gran librería ejecutiva caoba' },
  { type: 'whiteboard',       label: 'Pizarra Scrum',   category: 'furniture', w: 48, h: 44, imgKey: 'whiteboard',       icon: '📊', description: 'Pizarra de arquitectura y sprints' },

  // 💻 Tecnología
  { type: 'pcOn',             label: 'PC Encendido',    category: 'tech',      w: 24, h: 32, imgKey: 'pc1',             icon: '💻', description: 'Monitor CRT retro con pantalla activa' },
  { type: 'pcOff',            label: 'PC Apagado',      category: 'tech',      w: 24, h: 32, imgKey: 'pcOff',           icon: '🖥️', description: 'Monitor en reposo' },
  { type: 'serverRack',       label: 'Rack Servidor',   category: 'tech',      w: 26, h: 68, imgKey: 'serverRack',      icon: '🖲️', description: 'Servidor blade con LEDs animados' },

  // 🪴 Decoración & Arte
  { type: 'plant',            label: 'Planta Maceta',   category: 'decor',     w: 24, h: 36, imgKey: 'plant',           icon: '🪴', description: 'Planta de escritorio en maceta' },
  { type: 'plant2',           label: 'Ficus Verde',     category: 'decor',     w: 24, h: 36, imgKey: 'plant2',          icon: '🌿', description: 'Planta decorativa de suelo' },
  { type: 'largePlant',       label: 'Palmera Grande',  category: 'decor',     w: 32, h: 48, imgKey: 'largePlant',      icon: '🌴', description: 'Palmera tropical de pasillo' },
  { type: 'hangingPlant',     label: 'Planta Colgante', category: 'decor',     w: 24, h: 36, imgKey: 'hangingPlant',    icon: '🌱', description: 'Enredadera de pared' },
  { type: 'cactus',           label: 'Cactus Oficina',  category: 'decor',     w: 24, h: 32, imgKey: 'cactus',          icon: '🌵', description: 'Cactus de bajo mantenimiento' },
  { type: 'largePainting',    label: 'Cuadro Paisaje',  category: 'decor',     w: 48, h: 36, imgKey: 'largePainting',   icon: '🖼️', description: 'Cuadro al óleo para dirección' },
  { type: 'smallPainting',    label: 'Cuadro Abstracto',category: 'decor',     w: 32, h: 32, imgKey: 'smallPainting',   icon: '🎨', description: 'Pintura moderna' },
  { type: 'clock',            label: 'Reloj de Pared',  category: 'decor',     w: 16, h: 16, imgKey: 'clock',           icon: '⏰', description: 'Reloj analógico clásico' },
  { type: 'bin',              label: 'Papelera',        category: 'decor',     w: 16, h: 20, imgKey: 'bin',             icon: '🗑️', description: 'Papelera metálica de oficina' },

  // ☕ Cocina & Mascotas
  { type: 'coffee',           label: 'Cafetera Espresso',category: 'breakroom',w: 16, h: 16, imgKey: 'coffee',          icon: '☕', description: 'Cafetera automática con vapor animado' },
  { type: 'counter',          label: 'Barra Cocina',    category: 'breakroom', w: 180,h: 28, imgKey: 'counter',         icon: '🍽️', description: 'Encimera de cocina para breakroom' },
  { type: 'gitcat',           label: 'GitCat (Gato)',   category: 'breakroom', w: 28, h: 28, imgKey: 'gitcat',          icon: '🐱', description: 'Gato mascota de la oficina' },
  { type: 'claudio',          label: 'Claudio (Perro)', category: 'breakroom', w: 28, h: 28, imgKey: 'claudio',         icon: '🐶', description: 'Perro guardián amigable' },
];

/** Default starting layout props */
const DEFAULT_DECOR_PROPS = [
  // ── Executive Suite (Top-Left) ──
  { id: 'prop-db-1',     type: 'doubleBook',    x: 40,  y: 34,  w: 48, h: 48, rot: 0, imgKey: 'doubleBook',    label: 'Biblioteca Caoba' },
  { id: 'prop-db-2',     type: 'doubleBook',    x: 92,  y: 34,  w: 48, h: 48, rot: 0, imgKey: 'doubleBook',    label: 'Biblioteca Caoba' },
  { id: 'prop-paint-1',  type: 'largePainting', x: 260, y: 32,  w: 48, h: 36, rot: 0, imgKey: 'largePainting', label: 'Cuadro Paisaje' },
  { id: 'prop-clock-1',  type: 'clock',         x: 230, y: 34,  w: 16, h: 16, rot: 0, imgKey: 'clock',         label: 'Reloj Ejecutivo' },
  { id: 'prop-wb-1',     type: 'whiteboard',    x: 450, y: 36,  w: 48, h: 44, rot: 0, imgKey: 'whiteboard',    label: 'Pizarra Roadmap' },
  { id: 'prop-hp-1',     type: 'hangingPlant',  x: 520, y: 28,  w: 24, h: 36, rot: 0, imgKey: 'hangingPlant',  label: 'Enredadera' },

  // ── Breakroom & Cocina (Top-Right) ──
  { id: 'prop-counter',  type: 'counter',       x: 600, y: 76,  w: 180, h: 28, rot: 0, imgKey: 'counter',      label: 'Barra Cocina' },
  { id: 'prop-coffee',   type: 'coffee',        x: 736, y: 60,  w: 16, h: 16, rot: 0, imgKey: 'coffee',        label: 'Cafetera Espresso' },
  { id: 'prop-sofa-1',   type: 'sofaFront',     x: 870, y: 90,  w: 48, h: 32, rot: 0, imgKey: 'sofaFront',     label: 'Sofá Magenta' },
  { id: 'prop-ct-1',     type: 'coffeeTable',   x: 880, y: 130, w: 32, h: 24, rot: 0, imgKey: 'coffeeTable',   label: 'Mesa de Centro' },
  { id: 'prop-plant-1',  type: 'plant2',        x: 950, y: 40,  w: 24, h: 36, rot: 0, imgKey: 'plant2',        label: 'Planta Ficus' },
  { id: 'prop-cat-1',    type: 'gitcat',        x: 830, y: 120, w: 28, h: 28, rot: 0, imgKey: 'gitcat',        label: 'GitCat' },

  // ── Central Hallway Corridor ──
  { id: 'prop-lp-1',     type: 'largePlant',    x: 40,  y: 260, w: 32, h: 48, rot: 0, imgKey: 'largePlant',    label: 'Palmera Pasillo' },
  { id: 'prop-lp-2',     type: 'largePlant',    x: 950, y: 260, w: 32, h: 48, rot: 0, imgKey: 'largePlant',    label: 'Palmera Pasillo' },

  // ── Dev Bullpen (Bottom-Left) ──
  { id: 'prop-cactus-1', type: 'cactus',        x: 36,  y: 336, w: 24, h: 32, rot: 0, imgKey: 'cactus',        label: 'Cactus Dev' },
  { id: 'prop-bin-1',    type: 'bin',           x: 280, y: 560, w: 16, h: 20, rot: 0, imgKey: 'bin',           label: 'Papelera' },

  // ── Strategy & Docs Wing (Bottom-Center) ──
  { id: 'prop-wb-2',     type: 'whiteboard',    x: 480, y: 328, w: 48, h: 44, rot: 0, imgKey: 'whiteboard',    label: 'Pizarra OKRs' },
  { id: 'prop-bs-1',     type: 'bookshelf',     x: 630, y: 328, w: 32, h: 44, rot: 0, imgKey: 'bookshelf',     label: 'Librero Estrategia' },
  { id: 'prop-plant-2',  type: 'plant',         x: 350, y: 340, w: 24, h: 36, rot: 0, imgKey: 'plant',         label: 'Planta Potted' },

  // ── Laboratorio QA & CISO Bunker (Bottom-Right) ──
  { id: 'prop-server-1', type: 'serverRack',    x: 940, y: 480, w: 26, h: 68, rot: 0, imgKey: 'serverRack',    label: 'Rack Servidor 01' },
  { id: 'prop-server-2', type: 'serverRack',    x: 970, y: 480, w: 26, h: 68, rot: 0, imgKey: 'serverRack',    label: 'Rack Servidor 02' },
];

/** @type {Array<Object>} Currently active placed props */
let _decorProps = JSON.parse(JSON.stringify(DEFAULT_DECOR_PROPS));

// ── State Variables ───────────────────────────────────────────────────────

/** @type {Map<string, string>} agentId → visual status ('idle'|'working'|'reviewing'|'blocked'|'success') */
const _agentStates = new Map(AGENTS.map((a) => [a.id, 'idle']));

/** @type {AgentDef|null} */
let _hoveredAgent = null;

/** @type {AgentDef|null} */
let _selectedAgent = null;

/** @type {string|null} */
let _activeProjectId = null;

/** @type {number} */
let _totalTokens = 0;

/** @type {number} */
let _eventCounter = 0;

/** @type {number} */
let _cameraZoom = 1.0;

// ── Edit & Decoration Mode State ──────────────────────────────────────────

let _isEditMode = false;
let _selectedDecorItem = null; // { kind: 'prop'|'agent', item: Object }
let _draggedTarget = null;     // { kind: 'prop'|'agent', item: Object, offsetX: number, offsetY: number }
let _placementItem = null;     // CatalogItem definition when placing new object
let _mouseCanvasPos = { x: 0, y: 0 };
let _activeDecorTab = 'furniture';

// Particle system for coffee steam
const _steamPuffs = [];
for (let i = 0; i < 10; i++) {
  _steamPuffs.push({
    x: 742 + Math.random() * 8,
    y: 90 + Math.random() * 16,
    vy: -0.3 - Math.random() * 0.3,
    vx: (Math.random() - 0.5) * 0.15,
    alpha: Math.random() * 0.5 + 0.3,
    size: Math.random() * 3 + 2,
  });
}

// ── DOM Helper ────────────────────────────────────────────────────────────

const $id = (id) => document.getElementById(id);

function _esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Asset Preloader ───────────────────────────────────────────────────────

/** @type {Record<string, HTMLImageElement>} */
const _img = {};
let _assetsLoaded = false;

const ASSET_URLS = {
  // Furniture
  desk:             '/static/assets/furniture/DESK/DESK_FRONT.png',
  pc1:              '/static/assets/furniture/PC/PC_FRONT_ON_1.png',
  pc2:              '/static/assets/furniture/PC/PC_FRONT_ON_2.png',
  pc3:              '/static/assets/furniture/PC/PC_FRONT_ON_3.png',
  pcOff:            '/static/assets/furniture/PC/PC_FRONT_OFF.png',
  pcSide:           '/static/assets/furniture/PC/PC_SIDE.png',
  chairFront:       '/static/assets/furniture/CUSHIONED_CHAIR/CUSHIONED_CHAIR_FRONT.png',
  chairBack:        '/static/assets/furniture/CUSHIONED_CHAIR/CUSHIONED_CHAIR_BACK.png',
  chairSide:        '/static/assets/furniture/CUSHIONED_CHAIR/CUSHIONED_CHAIR_SIDE.png',
  woodenChairFront: '/static/assets/furniture/WOODEN_CHAIR/WOODEN_CHAIR_FRONT.png',
  woodenChairBack:  '/static/assets/furniture/WOODEN_CHAIR/WOODEN_CHAIR_BACK.png',
  woodenChairSide:  '/static/assets/furniture/WOODEN_CHAIR/WOODEN_CHAIR_SIDE.png',
  sofaFront:        '/static/assets/furniture/SOFA/SOFA_FRONT.png',
  sofaBack:         '/static/assets/furniture/SOFA/SOFA_BACK.png',
  sofaSide:         '/static/assets/furniture/SOFA/SOFA_SIDE.png',
  coffeeTable:      '/static/assets/furniture/COFFEE_TABLE/COFFEE_TABLE.png',
  smallTable:       '/static/assets/furniture/SMALL_TABLE/SMALL_TABLE_FRONT.png',
  coffee:           '/static/assets/furniture/COFFEE/COFFEE.png',
  bookshelf:        '/static/assets/furniture/BOOKSHELF/BOOKSHELF.png',
  doubleBook:       '/static/assets/furniture/DOUBLE_BOOKSHELF/DOUBLE_BOOKSHELF.png',
  whiteboard:       '/static/assets/furniture/WHITEBOARD/WHITEBOARD.png',
  plant:            '/static/assets/furniture/PLANT/PLANT.png',
  plant2:           '/static/assets/furniture/PLANT_2/PLANT_2.png',
  largePlant:       '/static/assets/furniture/LARGE_PLANT/LARGE_PLANT.png',
  hangingPlant:     '/static/assets/furniture/HANGING_PLANT/HANGING_PLANT.png',
  cactus:           '/static/assets/furniture/CACTUS/CACTUS.png',
  clock:            '/static/assets/furniture/CLOCK/CLOCK.png',
  largePainting:    '/static/assets/furniture/LARGE_PAINTING/LARGE_PAINTING.png',
  smallPainting:    '/static/assets/furniture/SMALL_PAINTING/SMALL_PAINTING.png',
  bin:              '/static/assets/furniture/BIN/BIN.png',
  gitcat:           '/static/assets/pets/gitcat/pet.png',
  claudio:          '/static/assets/pets/claudio/pet.png',

  // Characters
  char0:            '/static/assets/characters/char_0.png',
  char1:            '/static/assets/characters/char_1.png',
  char2:            '/static/assets/characters/char_2.png',
  char3:            '/static/assets/characters/char_3.png',
  char4:            '/static/assets/characters/char_4.png',
  char5:            '/static/assets/characters/char_5.png',
};

function _loadAssets() {
  const keys = Object.keys(ASSET_URLS);
  let loadedCount = 0;

  return new Promise((resolve) => {
    keys.forEach((k) => {
      const img = new Image();
      img.src = ASSET_URLS[k];
      img.onload = () => {
        _img[k] = img;
        loadedCount++;
        if (loadedCount === keys.length) {
          _assetsLoaded = true;
          resolve(true);
        }
      };
      img.onerror = () => {
        console.warn(`Asset failed to load: ${ASSET_URLS[k]}`);
        loadedCount++;
        if (loadedCount === keys.length) {
          _assetsLoaded = true;
          resolve(true);
        }
      };
    });
  });
}

// ── Layout Persistence (LocalStorage) ─────────────────────────────────────

const STORAGE_KEY = 'agentoffice_custom_layout_v2';

function _loadSavedLayout() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    if (data.props && Array.isArray(data.props)) {
      _decorProps = data.props;
    }
    if (data.agents && Array.isArray(data.agents)) {
      data.agents.forEach((saved) => {
        const found = AGENTS.find((a) => a.id === saved.id);
        if (found) {
          found.x = saved.x;
          found.y = saved.y;
        }
      });
    }
  } catch (err) {
    console.warn('Could not restore custom layout:', err);
  }
}

function _saveCustomLayout() {
  const data = {
    props: _decorProps,
    agents: AGENTS.map((a) => ({ id: a.id, x: a.x, y: a.y })),
    savedAt: new Date().toISOString(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  appendActivityLog({
    level: 'success',
    source: 'DECORACIÓN',
    message: '¡Diseño y distribución de la oficina guardados con éxito!',
  });
  _updateSelectionInfo('¡Diseño guardado en tu navegador! ✓');
}

function _resetCustomLayout() {
  localStorage.removeItem(STORAGE_KEY);
  _decorProps = JSON.parse(JSON.stringify(DEFAULT_DECOR_PROPS));
  AGENTS.forEach((a) => {
    const def = DEFAULT_AGENT_COORDS[a.id];
    if (def) {
      a.x = def.x;
      a.y = def.y;
    }
  });
  _selectedDecorItem = null;
  _placementItem = null;
  appendActivityLog({
    level: 'info',
    source: 'DECORACIÓN',
    message: 'Oficina restablecida a los valores de diseño originales de fábrica.',
  });
  _updateSelectionInfo('Oficina restablecida a valores de fábrica.');
}

// ── Canvas Engine Core & Event Handlers ───────────────────────────────────

/** @type {HTMLCanvasElement|null} */
let _canvas = null;

/** @type {CanvasRenderingContext2D|null} */
let _ctx = null;

let _lastTime = 0;

function _initCanvasEngine() {
  _canvas = /** @type {HTMLCanvasElement} */ ($id('office-canvas'));
  if (!_canvas) return;

  _ctx = _canvas.getContext('2d');
  if (!_ctx) return;

  _ctx.imageSmoothingEnabled = false;

  _loadSavedLayout();

  _canvas.addEventListener('mousemove', _onCanvasMouseMove);
  _canvas.addEventListener('mousedown', _onCanvasMouseDown);
  window.addEventListener('mouseup', _onCanvasMouseUp);
  _canvas.addEventListener('mouseleave', _onCanvasMouseLeave);
  _canvas.addEventListener('click', _onCanvasClick);
  window.addEventListener('keydown', _onGlobalKeyDown);

  _loadAssets().then(() => {
    _lastTime = performance.now();
    requestAnimationFrame(_renderLoop);
  });
}

function _getCanvasCoords(e) {
  if (!_canvas) return { x: 0, y: 0 };
  const rect = _canvas.getBoundingClientRect();
  const scaleX = _canvas.width / rect.width;
  const scaleY = _canvas.height / rect.height;
  return {
    x: (e.clientX - rect.left) * scaleX,
    y: (e.clientY - rect.top) * scaleY,
  };
}

function _hitTestAgent(px, py) {
  for (const agent of AGENTS) {
    const minX = agent.x - 32;
    const maxX = agent.x + 32;
    const minY = agent.y - 42;
    const maxY = agent.y + 24;
    if (px >= minX && px <= maxX && py >= minY && py <= maxY) {
      return agent;
    }
  }
  return null;
}

function _hitTestProp(px, py) {
  // Check in reverse order so topmost props are selected first
  for (let i = _decorProps.length - 1; i >= 0; i--) {
    const p = _decorProps[i];
    if (px >= p.x && px <= p.x + p.w && py >= p.y && py <= p.y + p.h) {
      return p;
    }
  }
  return null;
}

function _onCanvasMouseMove(e) {
  const { x, y } = _getCanvasCoords(e);
  _mouseCanvasPos = { x, y };

  if (_isEditMode) {
    // ── Edit Mode Mouse Move ──
    if (_draggedTarget) {
      // Snapping to 8px grid
      const rawX = x - _draggedTarget.offsetX;
      const rawY = y - _draggedTarget.offsetY;
      const snapX = Math.round(rawX / 8) * 8;
      const snapY = Math.round(rawY / 8) * 8;

      if (_draggedTarget.kind === 'prop') {
        const p = _draggedTarget.item;
        p.x = Math.max(24, Math.min(1000 - p.w, snapX));
        p.y = Math.max(28, Math.min(612 - p.h, snapY));
      } else if (_draggedTarget.kind === 'agent') {
        const a = _draggedTarget.item;
        a.x = Math.max(48, Math.min(976, snapX));
        a.y = Math.max(64, Math.min(580, snapY));
      }
      if (_canvas) _canvas.style.cursor = 'grabbing';
      return;
    }

    if (_placementItem) {
      if (_canvas) _canvas.style.cursor = 'crosshair';
      return;
    }

    const hitP = _hitTestProp(x, y);
    const hitA = _hitTestAgent(x, y);
    if (_canvas) {
      _canvas.style.cursor = (hitP || hitA) ? 'grab' : 'default';
    }
    return;
  }

  // ── Normal Mode Mouse Move (Tooltip & Hover) ──
  const found = _hitTestAgent(x, y);

  if (found !== _hoveredAgent) {
    _hoveredAgent = found;
    if (_canvas) {
      _canvas.style.cursor = found ? 'pointer' : 'default';
    }

    const tooltip = $id('canvas-agent-tooltip');
    if (tooltip) {
      if (found) {
        tooltip.innerHTML = `💬 <strong>${_esc(found.name)}</strong>: ${_esc(found.fullName)} <span style="color:#06b6d4">(Clic para Chat Directo)</span>`;
        tooltip.classList.remove('hidden');
        const rect = _canvas.getBoundingClientRect();
        const screenX = (found.x / _canvas.width) * rect.width;
        const screenY = ((found.y - 48) / _canvas.height) * rect.height;
        tooltip.style.left = `${screenX}px`;
        tooltip.style.top = `${screenY}px`;
        tooltip.style.transform = 'translate(-50%, -100%)';
      } else {
        tooltip.classList.add('hidden');
      }
    }
  }
}

function _onCanvasMouseDown(e) {
  if (!_isEditMode) return;
  const { x, y } = _getCanvasCoords(e);

  // If user is currently placing an item picked from the catalog
  if (_placementItem) {
    const snapX = Math.round((x - _placementItem.w / 2) / 8) * 8;
    const snapY = Math.round((y - _placementItem.h / 2) / 8) * 8;
    const newProp = {
      id: `prop-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
      type: _placementItem.type,
      x: Math.max(24, Math.min(1000 - _placementItem.w, snapX)),
      y: Math.max(28, Math.min(612 - _placementItem.h, snapY)),
      w: _placementItem.w,
      h: _placementItem.h,
      rot: 0,
      imgKey: _placementItem.imgKey,
      label: _placementItem.label,
    };
    _decorProps.push(newProp);
    _selectedDecorItem = { kind: 'prop', item: newProp };
    _updateSelectionInfo(`Colocado: ${newProp.label} (R: Rotar | Supr: Eliminar)`);
    if (!e.shiftKey) {
      _placementItem = null;
      document.querySelectorAll('.decor-item-card').forEach((c) => c.classList.remove('selected'));
    }
    return;
  }

  // Check hit on props first (topmost first)
  const hitP = _hitTestProp(x, y);
  if (hitP) {
    _selectedDecorItem = { kind: 'prop', item: hitP };
    _draggedTarget = {
      kind: 'prop',
      item: hitP,
      offsetX: x - hitP.x,
      offsetY: y - hitP.y,
    };
    _updateSelectionInfo(`Seleccionado: ${hitP.label} [R: Rotar | Supr: Borrar]`);
    return;
  }

  // Check hit on agents
  const hitA = _hitTestAgent(x, y);
  if (hitA) {
    _selectedDecorItem = { kind: 'agent', item: hitA };
    _draggedTarget = {
      kind: 'agent',
      item: hitA,
      offsetX: x - hitA.x,
      offsetY: y - hitA.y,
    };
    _updateSelectionInfo(`Puesto de Agente: ${hitA.name} (${hitA.fullName}) — Arrastra para mover`);
    return;
  }

  // Click on empty space
  _selectedDecorItem = null;
  _updateSelectionInfo('Ningún elemento seleccionado');
}

function _onCanvasMouseUp() {
  if (_draggedTarget) {
    _draggedTarget = null;
    if (_canvas && _isEditMode) _canvas.style.cursor = 'grab';
  }
}

function _onCanvasMouseLeave() {
  _hoveredAgent = null;
  if (!_isEditMode) {
    if (_canvas) _canvas.style.cursor = 'default';
    const tooltip = $id('canvas-agent-tooltip');
    if (tooltip) tooltip.classList.add('hidden');
  }
}

function _onCanvasClick(e) {
  if (_isEditMode) return; // In edit mode, interaction is handled in mousedown/up
  const { x, y } = _getCanvasCoords(e);
  const clickedAgent = _hitTestAgent(x, y);
  if (clickedAgent) {
    _onAgentClick(clickedAgent);
  }
}

function _onAgentClick(agent) {
  _selectedAgent = agent;
  document.dispatchEvent(
    new CustomEvent('agent:selected', {
      detail: { agent, projectId: _activeProjectId },
    })
  );
}

export function selectAgent(agent) {
  _onAgentClick(agent);
}

function _onGlobalKeyDown(e) {
  if (!_isEditMode) return;

  // Key R: Rotate selected item
  if (e.key === 'r' || e.key === 'R') {
    if (_selectedDecorItem && _selectedDecorItem.kind === 'prop') {
      const p = _selectedDecorItem.item;
      // Sofa flip
      if (p.type === 'sofaFront') {
        p.type = 'sofaSide';
        p.imgKey = 'sofaSide';
        const tmp = p.w; p.w = p.h; p.h = tmp;
      } else if (p.type === 'sofaSide') {
        p.type = 'sofaFront';
        p.imgKey = 'sofaFront';
        const tmp = p.w; p.w = p.h; p.h = tmp;
      } else if (p.type === 'chairFront') {
        p.type = 'chairSide';
        p.imgKey = 'chairSide';
      } else if (p.type === 'chairSide') {
        p.type = 'chairBack';
        p.imgKey = 'chairBack';
      } else if (p.type === 'chairBack') {
        p.type = 'chairFront';
        p.imgKey = 'chairFront';
      } else {
        p.rot = (p.rot + 90) % 360;
      }
      _updateSelectionInfo(`Rotado: ${p.label}`);
    }
  }

  // Key Delete or Backspace: Remove selected prop
  if (e.key === 'Delete' || e.key === 'Backspace') {
    // Avoid deleting if user is typing in a textarea or input
    if (['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName || '')) return;

    if (_selectedDecorItem && _selectedDecorItem.kind === 'prop') {
      const p = _selectedDecorItem.item;
      _decorProps = _decorProps.filter((item) => item.id !== p.id);
      _updateSelectionInfo(`Eliminado: ${p.label}`);
      _selectedDecorItem = null;
    }
  }

  // Key Escape: Cancel placement or deselect
  if (e.key === 'Escape') {
    _placementItem = null;
    _selectedDecorItem = null;
    document.querySelectorAll('.decor-item-card').forEach((c) => c.classList.remove('selected'));
    _updateSelectionInfo('Ningún elemento seleccionado');
  }
}

// ── Master Render Loop ────────────────────────────────────────────────────

function _renderLoop(currentTime) {
  const dt = (currentTime - _lastTime) / 1000;
  _lastTime = currentTime;

  if (_ctx && _canvas && _assetsLoaded) {
    _renderOffice(_ctx, currentTime / 1000, dt);
  }

  requestAnimationFrame(_renderLoop);
}

function _renderOffice(ctx, time, dt) {
  ctx.save();
  ctx.imageSmoothingEnabled = false;

  // Clear canvas background
  ctx.fillStyle = '#080c14';
  ctx.fillRect(0, 0, 1024, 640);

  // 1. Tiled Rich Pixel-Art Floors (Warm Parquet, Indigo Velvet, Ceramic, Tech, Steel)
  _drawTiledFloors(ctx);

  // 2. Real Pixel-Art Walls & Room Borders
  _drawWallsAndDividers(ctx);

  // 3. Central Hallway Circulation Runner & Plants
  _drawHallwayRunner(ctx, time);

  // 4. Room Props & Furniture (Editable & Draggable)
  _drawRoomDecor(ctx, time, dt);

  // 5. The 15 Agent Workstations (Desks, PCs, Animated Character Sprites)
  _drawAgentWorkstations(ctx, time);

  // 6. Room Title Signs & Ambient Radial Spotlight Glow
  _drawRoomSignage(ctx);
  _drawAmbientLighting(ctx);

  // 7. Edit Mode Guides, Selection Boxes & Placement Ghost
  if (_isEditMode) {
    _drawEditModeOverlay(ctx, time);
  }

  ctx.restore();
}

// ── 1. Warm & Rich Procedural Pixel-Art Floors ────────────────────────────

function _drawTiledFloors(ctx) {
  // A. Executive Suite (x: 20..560, y: 24..240) — Royal Midnight Indigo Carpet with Brass/Gold Trim
  _drawPlushCarpet(ctx, 20, 24, 540, 216, '#151d30', 'rgba(56, 85, 140, 0.15)', '#d97706');

  // B. Breakroom & Kitchen (x: 576..1004, y: 24..240) — Slate & Cream Ceramic Checkered Tiles
  _drawCeramicTiles(ctx, 576, 24, 428, 216);

  // C. Central Hallway (x: 20..1004, y: 244..316) — Warm Rich Oak Parquet
  _drawWoodParquet(ctx, 20, 244, 984, 72);

  // D. Dev Bullpen (x: 20..330, y: 320..616) — Warm Rich Oak Parquet
  _drawWoodParquet(ctx, 20, 320, 310, 296);

  // E. Strategy & Growth Wing (x: 336..680, y: 320..616) — Warm Parquet with Velvet Emerald Rug
  _drawWoodParquet(ctx, 336, 320, 344, 296);
  _drawPlushCarpet(ctx, 356, 340, 304, 256, '#0f2f2d', 'rgba(20, 184, 166, 0.14)', '#0d9488');

  // F. Laboratorio QA (x: 686..1004, y: 320..460) — Deep Cyber-Slate Tiles with Cyan Rivets
  _drawTechTiles(ctx, 686, 320, 318, 140);

  // G. Búnker CISO & Servidores (x: 686..1004, y: 466..616) — Titanium Steel Panels with Hazard Trim
  _drawSteelFloor(ctx, 686, 466, 318, 150);
}

/** Rich warm oak wood parquet with horizontal planks, natural tones, and staggered nail seams */
function _drawWoodParquet(ctx, x, y, w, h) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();

  const plankColors = ['#452a17', '#382010', '#4e301b', '#3d2413', '#492c18'];
  const plankH = 16;

  for (let py = y, row = 0; py < y + h; py += plankH, row++) {
    const curH = Math.min(plankH, y + h - py);
    // Plank base tone
    ctx.fillStyle = plankColors[row % plankColors.length];
    ctx.fillRect(x, py, w, curH);

    // Dark bottom groove
    ctx.fillStyle = '#261509';
    ctx.fillRect(x, py + curH - 1, w, 1);

    // Soft top grain highlight
    ctx.fillStyle = 'rgba(255, 255, 255, 0.04)';
    ctx.fillRect(x, py, w, 1);

    // Staggered vertical plank joints every 48px
    const stagger = (row * 24) % 48;
    for (let vx = x + stagger; vx < x + w; vx += 48) {
      ctx.fillStyle = '#221208';
      ctx.fillRect(vx, py, 1, curH - 1);

      // Micro nail dots near joint ends
      ctx.fillStyle = '#170c05';
      if (curH >= 6) {
        ctx.fillRect(vx - 2, py + 3, 1, 1);
        ctx.fillRect(vx - 2, py + curH - 4, 1, 1);
      }
    }
  }

  ctx.restore();
}

/** Executive velvet carpet with micro-weave texture and golden/cyan brass border */
function _drawPlushCarpet(ctx, x, y, w, h, baseCol, weaveCol, borderCol) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();

  // Solid base
  ctx.fillStyle = baseCol;
  ctx.fillRect(x, y, w, h);

  // Micro-weave subtle texture (diamond waffle)
  ctx.fillStyle = weaveCol;
  for (let py = y + 4; py < y + h - 4; py += 12) {
    for (let px = x + 4; px < x + w - 4; px += 12) {
      ctx.fillRect(px, py, 2, 2);
      ctx.fillRect(px + 6, py + 6, 2, 2);
    }
  }

  // Luxury Perimeter Border
  ctx.strokeStyle = borderCol;
  ctx.lineWidth = 3;
  ctx.strokeRect(x + 4, y + 4, w - 8, h - 8);

  ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 7, y + 7, w - 14, h - 14);

  // Brass corner ornaments
  ctx.fillStyle = borderCol;
  ctx.fillRect(x + 2, y + 2, 6, 6);
  ctx.fillRect(x + w - 8, y + 2, 6, 6);
  ctx.fillRect(x + 2, y + h - 8, 6, 6);
  ctx.fillRect(x + w - 8, y + h - 8, 6, 6);

  ctx.restore();
}

/** Checkered slate & cream ceramic tiles with bevel depth for the kitchen / breakroom */
function _drawCeramicTiles(ctx, x, y, w, h) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();

  ctx.fillStyle = '#2b394e'; // Grout background
  ctx.fillRect(x, y, w, h);

  const tileSize = 20;
  for (let py = y; py < y + h; py += tileSize) {
    for (let px = x; px < x + w; px += tileSize) {
      const isAlt = (Math.floor((px - x) / tileSize) + Math.floor((py - y) / tileSize)) % 2 === 0;
      const tw = Math.min(tileSize - 2, x + w - px - 2);
      const th = Math.min(tileSize - 2, y + h - py - 2);
      if (tw > 0 && th > 0) {
        ctx.fillStyle = isAlt ? '#53657d' : '#647791';
        ctx.fillRect(px + 1, py + 1, tw, th);

        // Tactile bevel top-left highlight
        ctx.fillStyle = 'rgba(255, 255, 255, 0.12)';
        ctx.fillRect(px + 1, py + 1, tw, 1);
        ctx.fillRect(px + 1, py + 1, 1, th);
      }
    }
  }

  ctx.restore();
}

/** Tech cyber tiles with cyan rivets for the QA lab */
function _drawTechTiles(ctx, x, y, w, h) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();

  ctx.fillStyle = '#0a131f';
  ctx.fillRect(x, y, w, h);

  const size = 28;
  for (let py = y; py < y + h; py += size) {
    for (let px = x; px < x + w; px += size) {
      const tw = Math.min(size - 2, x + w - px - 2);
      const th = Math.min(size - 2, y + h - py - 2);
      if (tw > 0 && th > 0) {
        ctx.fillStyle = '#111e2e';
        ctx.fillRect(px + 1, py + 1, tw, th);

        ctx.fillStyle = 'rgba(6, 182, 212, 0.35)';
        ctx.fillRect(px + 3, py + 3, 2, 2);
      }
    }
  }

  ctx.restore();
}

/** Industrial steel plates with hazard perimeter stripes for CISO Bunker */
function _drawSteelFloor(ctx, x, y, w, h) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();

  ctx.fillStyle = '#0e121b';
  ctx.fillRect(x, y, w, h);

  const size = 32;
  for (let py = y; py < y + h; py += size) {
    for (let px = x; px < x + w; px += size) {
      const tw = Math.min(size - 2, x + w - px - 2);
      const th = Math.min(size - 2, y + h - py - 2);
      if (tw > 0 && th > 0) {
        ctx.fillStyle = '#161c28';
        ctx.fillRect(px + 1, py + 1, tw, th);

        // Corner steel bolts
        ctx.fillStyle = '#222d3d';
        ctx.fillRect(px + 2, py + 2, 2, 2);
        ctx.fillRect(px + tw - 2, py + th - 2, 2, 2);
      }
    }
  }

  // Industrial hazard striping along bottom border
  ctx.fillStyle = '#f59e0b';
  for (let hx = x; hx < x + w; hx += 16) {
    ctx.fillRect(hx, y + h - 5, 8, 5);
  }

  ctx.restore();
}

// ── 2. Walls & Dividers ───────────────────────────────────────────────────

function _drawWallsAndDividers(ctx) {
  ctx.strokeStyle = '#181008';
  ctx.lineWidth = 6;
  ctx.strokeRect(17, 21, 990, 598);

  ctx.fillStyle = '#1c120a';

  // Vertical wall between Executive and Breakroom
  ctx.fillRect(560, 24, 16, 216);

  // Horizontal wall above central corridor
  ctx.fillRect(20, 240, 984, 6);

  // Horizontal wall below central corridor
  ctx.fillRect(20, 316, 984, 6);

  // Vertical divider between Dev Bullpen and Strategy
  ctx.fillRect(330, 320, 6, 296);

  // Vertical divider between Strategy and QA/CISO
  ctx.fillRect(680, 320, 6, 296);

  // Horizontal divider between QA Lab and CISO Bunker
  ctx.fillRect(686, 460, 318, 6);
}

// ── 3. Central Hallway Circulation ────────────────────────────────────────

function _drawHallwayRunner(ctx, time) {
  // Red & Gold carpet runner along the center of the hallway
  ctx.fillStyle = '#7c2d12';
  ctx.fillRect(100, 264, 824, 32);

  ctx.strokeStyle = '#d97706';
  ctx.lineWidth = 1.5;
  ctx.strokeRect(102, 266, 820, 28);

  // Corridor transit label
  ctx.font = '700 9px "Fira Code", monospace';
  ctx.fillStyle = '#f59e0b';
  ctx.textAlign = 'center';
  ctx.fillText('═══ PASILLO CENTRAL DE CIRCULACIÓN ═══', 512, 284);
}

// ── 4. Room Props & Furniture (Editable & Draggable) ───────────────────────

function _drawRoomDecor(ctx, time, dt) {
  for (let i = 0; i < _decorProps.length; i++) {
    const p = _decorProps[i];

    // Special procedural props
    if (p.type === 'counter') {
      ctx.fillStyle = '#475569';
      ctx.fillRect(p.x, p.y + 4, p.w, p.h - 4);
      ctx.fillStyle = '#94a3b8';
      ctx.fillRect(p.x, p.y, p.w, 4);
      continue;
    }

    if (p.type === 'serverRack') {
      _drawAnimatedServerRack(ctx, p.x, p.y, time, i);
      continue;
    }

    if (p.type === 'gitcat' || p.type === 'claudio') {
      const petImg = _img[p.imgKey];
      if (petImg) {
        const frame = Math.floor(time * 2 + i) % 3;
        ctx.drawImage(petImg, frame * 32, 0, 32, 32, p.x, p.y, p.w, p.h);
      }
      continue;
    }

    // Standard pixel-art image props
    const img = _img[p.imgKey];
    if (img) {
      if (p.rot) {
        ctx.save();
        ctx.translate(p.x + p.w / 2, p.y + p.h / 2);
        ctx.rotate((p.rot * Math.PI) / 180);
        ctx.drawImage(img, -p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      } else {
        ctx.drawImage(img, p.x, p.y, p.w, p.h);
      }
    } else {
      // Fallback
      ctx.fillStyle = '#475569';
      ctx.fillRect(p.x, p.y, p.w, p.h);
    }

    // If this prop is a coffee machine, emit steam particles
    if (p.type === 'coffee') {
      _drawCoffeeSteam(ctx, p.x + 5, p.y, dt);
    }
  }
}

function _drawCoffeeSteam(ctx, cx, cy, dt) {
  ctx.fillStyle = 'rgba(255, 255, 255, 0.45)';
  for (const p of _steamPuffs) {
    p.y += p.vy;
    p.x += p.vx;
    p.alpha -= dt * 0.35;
    if (p.alpha <= 0 || p.y < cy - 18) {
      p.x = cx + Math.random() * 6;
      p.y = cy;
      p.alpha = Math.random() * 0.5 + 0.3;
    }
    ctx.save();
    ctx.globalAlpha = Math.max(0, p.alpha);
    ctx.fillRect(Math.floor(p.x), Math.floor(p.y), p.size, p.size);
    ctx.restore();
  }
}

function _drawAnimatedServerRack(ctx, x, y, time, offset) {
  ctx.fillStyle = '#0a0e17';
  ctx.fillRect(x, y, 26, 68);
  ctx.strokeStyle = '#334155';
  ctx.lineWidth = 1;
  ctx.strokeRect(x, y, 26, 68);

  for (let b = 0; b < 6; b++) {
    const by = y + 4 + b * 10;
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(x + 2, by, 22, 8);

    const blink1 = Math.floor(time * 4 + b + offset) % 2 === 0;
    const blink2 = Math.floor(time * 6 + b * 2 + offset) % 3 === 0;
    ctx.fillStyle = blink1 ? '#22c55e' : '#14532d';
    ctx.fillRect(x + 4, by + 3, 2, 2);
    ctx.fillStyle = blink2 ? '#06b6d4' : '#155e75';
    ctx.fillRect(x + 8, by + 3, 2, 2);
  }
}

// ── 5. Agent Workstations & Pixel-Art Characters ──────────────────────────

function _drawAgentWorkstations(ctx, time) {
  for (let i = 0; i < AGENTS.length; i++) {
    const agent = AGENTS[i];
    const isHovered = !_isEditMode && _hoveredAgent === agent;
    const isSelected = !_isEditMode && _selectedAgent === agent;
    const isEditSelected = _isEditMode && _selectedDecorItem?.item === agent;
    const status = _agentStates.get(agent.id) || 'idle';

    const ax = Math.floor(agent.x);
    const ay = Math.floor(agent.y);

    // A. Real Pixel-Art Desk (64x42 px)
    const deskW = 64;
    const deskH = 42;
    const deskX = ax - deskW / 2;
    const deskY = ay - 6;

    if (_img.desk) {
      ctx.drawImage(_img.desk, deskX, deskY, deskW, deskH);
    } else {
      ctx.fillStyle = '#5c381e';
      ctx.fillRect(deskX, deskY, deskW, deskH);
    }

    // B. Real Pixel-Art PC Monitor with Cycling Glow
    const pcFrame = Math.floor(time * 3 + i) % 3;
    let pcImg = _img.pc1;
    if (pcFrame === 1) pcImg = _img.pc2;
    if (pcFrame === 2) pcImg = _img.pc3;
    if (status === 'blocked') pcImg = _img.pcOff;

    if (pcImg) {
      ctx.drawImage(pcImg, ax - 12, deskY - 14, 24, 32);
    }

    // C. Office Chair behind the desk
    if (_img.chairBack) {
      ctx.drawImage(_img.chairBack, ax - 12, ay - 24, 24, 32);
    }

    // D. Authentic Pixel-Art Character Sprite
    _drawAgentCharacter(ctx, ax, ay, agent, status, time, i);

    // E. Floating Cyber-Pill Badge
    _drawCyberPill(ctx, ax, ay - 44, agent, status, isHovered, isSelected || isEditSelected);

    // F. Highlight Ring
    if (isHovered || isSelected || isEditSelected) {
      ctx.strokeStyle = isEditSelected ? '#f59e0b' : (isSelected ? '#22c55e' : '#06b6d4');
      ctx.lineWidth = isEditSelected ? 2 : 1.5;
      ctx.strokeRect(ax - 34, ay - 50, 68, 70);
    }
  }
}

function _drawAgentCharacter(ctx, x, y, agent, status, time, idx) {
  const charKey = `char${agent.charIndex % 6}`;
  const charImg = _img[charKey];

  const bob = status === 'working'
    ? Math.floor(Math.sin(time * 8 + idx) * 1.5)
    : Math.floor(Math.sin(time * 2.5 + idx) * 1.0);

  if (charImg) {
    let sx = 16;
    let sy = 0;
    if (status === 'working') {
      const typingFrame = Math.floor(time * 6 + idx) % 2 === 0 ? 3 : 4;
      sx = typingFrame * 16;
      sy = 64;
    }

    ctx.drawImage(
      charImg,
      sx, sy, 16, 32,
      x - 12, y - 28 + bob, 24, 42
    );
  } else {
    ctx.fillStyle = agent.color;
    ctx.fillRect(x - 8, y - 18 + bob, 16, 16);
  }
}

function _drawCyberPill(ctx, x, y, agent, status, isHovered, isSelected) {
  const label = isHovered ? 'CHAT 💬' : (status === 'working' ? 'TRABAJANDO' : 'LIBRE');
  const name = agent.name;
  const text = `${name} • ${label}`;

  ctx.font = '600 9px "Fira Code", monospace';
  const textW = ctx.measureText(text).width;
  const pillW = textW + 18;
  const pillH = 15;
  const px = Math.floor(x - pillW / 2);
  const py = Math.floor(y);

  ctx.fillStyle = isSelected ? '#164e63' : (isHovered ? '#0f172a' : '#080c14');
  ctx.beginPath();
  ctx.roundRect(px, py, pillW, pillH, 4);
  ctx.fill();

  ctx.strokeStyle = isSelected ? '#22c55e' : (isHovered ? '#06b6d4' : '#1e293b');
  ctx.lineWidth = 1;
  ctx.stroke();

  let dotColor = '#22c55e';
  if (status === 'working') dotColor = '#06b6d4';
  if (status === 'reviewing') dotColor = '#f59e0b';
  if (status === 'blocked') dotColor = '#ef4444';

  ctx.fillStyle = dotColor;
  ctx.beginPath();
  ctx.arc(px + 7, py + pillH / 2, 3, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = isHovered ? '#38bdf8' : '#f8fafc';
  ctx.textAlign = 'left';
  ctx.fillText(text, px + 14, py + 11);
}

// ── 6. Room Signage & Ambient Lighting ────────────────────────────────────

function _drawRoomSignage(ctx) {
  const rooms = [
    { title: '🏛️ DIRECCIÓN EJECUTIVA & REUNIONES', x: 30,  y: 34 },
    { title: '☕ BREAKROOM & COCINA',             x: 590, y: 34 },
    { title: '💻 BULLPEN INGENIERÍA & UI/UX',     x: 30,  y: 330 },
    { title: '📈 ESTRATEGIA, DOCS & GROWTH',      x: 350, y: 330 },
    { title: '🔬 LABORATORIO QA & CI/CD',         x: 700, y: 330 },
    { title: '🛡️ BÚNKER CISO & SERVIDORES',       x: 700, y: 476 },
  ];

  ctx.font = '700 9px "Fira Code", monospace';
  ctx.textAlign = 'left';

  for (const r of rooms) {
    const w = ctx.measureText(r.title).width + 14;
    ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
    ctx.fillRect(r.x, r.y - 11, w, 15);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 1;
    ctx.strokeRect(r.x, r.y - 11, w, 15);
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(r.title, r.x + 6, r.y);
  }
}

function _drawAmbientLighting(ctx) {
  const lights = [
    { x: 180, y: 130, r: 90 },
    { x: 380, y: 130, r: 90 },
    { x: 165, y: 460, r: 120 },
    { x: 500, y: 460, r: 140 },
    { x: 840, y: 460, r: 140 },
  ];

  ctx.save();
  ctx.globalCompositeOperation = 'screen';
  for (const l of lights) {
    const grad = ctx.createRadialGradient(l.x, l.y, 10, l.x, l.y, l.r);
    grad.addColorStop(0, 'rgba(254, 240, 138, 0.05)');
    grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(l.x, l.y, l.r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

// ── 7. Edit & Decoration Mode Overlays ────────────────────────────────────

function _drawEditModeOverlay(ctx, time) {
  // A. Subtle snap alignment dot grid across the office
  ctx.fillStyle = 'rgba(255, 255, 255, 0.06)';
  for (let gy = 32; gy < 616; gy += 16) {
    for (let gx = 24; gx < 1000; gx += 16) {
      ctx.fillRect(gx, gy, 1, 1);
    }
  }

  // B. Draw selection bounding box and action handles for selected item
  if (_selectedDecorItem) {
    let bx = 0;
    let by = 0;
    let bw = 0;
    let bh = 0;

    if (_selectedDecorItem.kind === 'prop') {
      const p = _selectedDecorItem.item;
      bx = p.x;
      by = p.y;
      bw = p.w;
      bh = p.h;
    } else if (_selectedDecorItem.kind === 'agent') {
      const a = _selectedDecorItem.item;
      bx = a.x - 32;
      by = a.y - 42;
      bw = 64;
      bh = 66;
    }

    ctx.save();
    // Glowing animated border
    ctx.strokeStyle = '#06b6d4';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);
    ctx.lineDashOffset = -time * 8;
    ctx.strokeRect(bx - 2, by - 2, bw + 4, bh + 4);
    ctx.setLineDash([]);

    // Corner handles
    ctx.fillStyle = '#22c55e';
    ctx.fillRect(bx - 4, by - 4, 5, 5);
    ctx.fillRect(bx + bw - 1, by - 4, 5, 5);
    ctx.fillRect(bx - 4, by + bh - 1, 5, 5);
    ctx.fillRect(bx + bw - 1, by + bh - 1, 5, 5);

    // Floating action hint
    const hintText = _selectedDecorItem.kind === 'prop' ? 'R: Rotar • Supr: Borrar' : 'Arrastra para mover';
    ctx.font = '700 8px "Fira Code", monospace';
    const hw = ctx.measureText(hintText).width + 8;
    ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
    ctx.fillRect(bx, by - 14, hw, 11);
    ctx.fillStyle = '#38bdf8';
    ctx.fillText(hintText, bx + 4, by - 5);

    ctx.restore();
  }

  // C. Placement ghost preview under cursor
  if (_placementItem) {
    const rawX = _mouseCanvasPos.x - _placementItem.w / 2;
    const rawY = _mouseCanvasPos.y - _placementItem.h / 2;
    const snapX = Math.round(rawX / 8) * 8;
    const snapY = Math.round(rawY / 8) * 8;

    ctx.save();
    ctx.globalAlpha = 0.75;

    const ghostImg = _img[_placementItem.imgKey];
    if (ghostImg) {
      ctx.drawImage(ghostImg, snapX, snapY, _placementItem.w, _placementItem.h);
    } else {
      ctx.fillStyle = '#06b6d4';
      ctx.fillRect(snapX, snapY, _placementItem.w, _placementItem.h);
    }

    // Ghost green bounding box
    ctx.strokeStyle = '#22c55e';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(snapX, snapY, _placementItem.w, _placementItem.h);

    ctx.font = '700 8px "Fira Code", monospace';
    ctx.fillStyle = '#22c55e';
    ctx.fillText(`Clic para colocar ${_placementItem.label}`, snapX, snapY - 4);

    ctx.restore();
  }
}

// ── Edit & Decoration Mode UI Integration ─────────────────────────────────

function _initDecorationUI() {
  const toggleBtnDock = $id('dock-btn-decor');
  const toggleBtnCam = $id('cam-edit-mode');
  const closeBtn = $id('btn-close-decor');
  const saveBtn = $id('btn-save-layout');
  const resetBtn = $id('btn-reset-layout');

  const toggleHandler = () => _toggleEditMode();

  toggleBtnDock?.addEventListener('click', toggleHandler);
  toggleBtnCam?.addEventListener('click', toggleHandler);
  closeBtn?.addEventListener('click', () => _toggleEditMode(false));

  saveBtn?.addEventListener('click', () => _saveCustomLayout());
  resetBtn?.addEventListener('click', () => {
    if (confirm('¿Restablecer el diseño y la posición de todos los agentes a los valores iniciales?')) {
      _resetCustomLayout();
    }
  });

  // Tab navigation
  document.querySelectorAll('.decor-tab-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.decor-tab-btn').forEach((b) => b.classList.remove('active'));
      const target = /** @type {HTMLElement} */ (e.currentTarget);
      target.classList.add('active');
      _activeDecorTab = target.dataset.cat || 'furniture';
      _renderDecorTrayItems();
    });
  });

  _renderDecorTrayItems();
}

function _toggleEditMode(forceState) {
  _isEditMode = forceState !== undefined ? forceState : !_isEditMode;

  const tray = $id('decor-tray');
  const banner = $id('canvas-edit-banner');
  const btnDock = $id('dock-btn-decor');
  const btnCam = $id('cam-edit-mode');

  if (_isEditMode) {
    tray?.classList.remove('hidden');
    banner?.classList.remove('hidden');
    btnDock?.classList.add('edit-btn-active');
    btnCam?.classList.add('edit-btn-active');
    _placementItem = null;
    _selectedDecorItem = null;
    _updateSelectionInfo('Modo diseño activo. Selecciona un elemento del catálogo o arrastra muebles existentes.');
  } else {
    tray?.classList.add('hidden');
    banner?.classList.add('hidden');
    btnDock?.classList.remove('edit-btn-active');
    btnCam?.classList.remove('edit-btn-active');
    _placementItem = null;
    _selectedDecorItem = null;
    if (_canvas) _canvas.style.cursor = 'default';
  }
}

function _renderDecorTrayItems() {
  const container = $id('decor-items-container');
  if (!container) return;
  container.innerHTML = '';

  if (_activeDecorTab === 'agents') {
    const info = document.createElement('div');
    info.className = 'decor-agents-info';
    info.innerHTML = `
      <strong>👤 Reubicar Puestos de Agentes</strong><br>
      Puedes hacer <strong>clic y arrastrar</strong> a cualquiera de los <strong>15 agentes</strong> directamente sobre la oficina para mover su escritorio a la posición que desees.<br>
      <span style="color:#06b6d4;font-size:10px;">¡El PC, el asiento y el avatar del agente se moverán juntos en tiempo real!</span>
    `;
    container.appendChild(info);
    return;
  }

  const filtered = DECOR_CATALOG.filter((item) => item.category === _activeDecorTab);

  filtered.forEach((item) => {
    const card = document.createElement('div');
    card.className = 'decor-item-card';
    card.title = item.description || item.label;
    card.innerHTML = `
      <div class="decor-item-icon">${item.icon}</div>
      <div class="decor-item-name">${item.label}</div>
      <div class="decor-item-size">${item.w}×${item.h}px</div>
    `;

    card.addEventListener('click', () => {
      document.querySelectorAll('.decor-item-card').forEach((c) => c.classList.remove('selected'));
      card.classList.add('selected');
      _placementItem = item;
      _updateSelectionInfo(`Colocando: ${item.label} — Haz clic en el canvas para posicionarlo`);
    });

    container.appendChild(card);
  });
}

function _updateSelectionInfo(msg) {
  const el = $id('decor-selection-info');
  if (el) el.textContent = msg;
}

// ── Pipeline Stepper ──────────────────────────────────────────────────────

function _initPipelineStepper() {
  const track = $id('pipeline-stepper-track');
  if (!track) return;
  track.innerHTML = '';

  PIPELINE_STEPS.forEach((step) => {
    const node = document.createElement('div');
    node.className = 'stepper-node pending';
    node.id = `stepper-node-${step.id}`;
    node.setAttribute('role', 'listitem');
    node.innerHTML = `
      <span class="stepper-node-icon" aria-hidden="true">${step.icon}</span>
      <span class="stepper-node-label">${step.label}</span>
      <span class="stepper-node-state" id="stepper-state-${step.id}">PENDIENTE</span>
    `;
    track.appendChild(node);
  });
}

export function updatePipelineStep(agentId, state) {
  const step = PIPELINE_STEPS.find((s) => s.agentId === agentId);
  if (!step) return;

  const node = $id(`stepper-node-${step.id}`);
  const stateLabel = $id(`stepper-state-${step.id}`);
  const activeStatus = $id('stepper-active-status');

  if (node && stateLabel) {
    node.classList.remove('active', 'done');
    if (state === 'active') {
      node.classList.add('active');
      stateLabel.textContent = 'EJECUTANDO...';
      if (activeStatus) activeStatus.textContent = step.label.toUpperCase();
    } else if (state === 'done') {
      node.classList.add('done');
      stateLabel.textContent = 'COMPLETADO ✓';
    } else {
      stateLabel.textContent = 'PENDIENTE';
    }
  }
}

// ── Agent Status & Telemetry ──────────────────────────────────────────────

export function updateAgentStatus(agentId, status) {
  _agentStates.set(agentId, status);
}

export function updateTelemetry(telemetry) {
  if (telemetry.total_tokens !== undefined) {
    _totalTokens = telemetry.total_tokens;
    const el = $id('kpi-tokens-val');
    if (el) el.textContent = _totalTokens.toLocaleString();
  }
  if (telemetry.estimated_cost_usd !== undefined) {
    const el = $id('kpi-cost-val');
    if (el) el.textContent = `$${telemetry.estimated_cost_usd.toFixed(3)}`;
  }
  if (telemetry.tasks_ratio !== undefined) {
    const el = $id('kpi-tasks-val');
    if (el) el.textContent = telemetry.tasks_ratio;
  }
}

// ── Activity Log Streamer ─────────────────────────────────────────────────

export function appendActivityLog(entry) {
  const list = $id('activity-list');
  if (!list) return;

  _eventCounter++;
  const counterEl = $id('activity-counter');
  if (counterEl) counterEl.textContent = `${_eventCounter}`;

  const row = document.createElement('div');
  row.className = `activity-entry ${entry.level ?? 'info'}`;
  const time = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  row.innerHTML = `
    <span class="activity-time">[${time}]</span>
    <span class="activity-source">${_esc(entry.source ?? 'SYSTEM')}</span>
    <span class="activity-msg">${_esc(entry.message)}</span>
  `;

  list.appendChild(row);
  const terminal = $id('activity-terminal');
  if (terminal) terminal.scrollTop = terminal.scrollHeight;
}

// ── Camera Zoom Controls ──────────────────────────────────────────────────

function _initCameraControls() {
  const stage = $id('office-stage');

  const applyZoom = () => {
    if (stage) {
      stage.style.transform = `scale(${_cameraZoom})`;
      stage.style.transformOrigin = 'center center';
      stage.style.transition = 'transform 0.15s ease-out';
    }
  };

  $id('cam-zoom-in')?.addEventListener('click', () => {
    _cameraZoom = Math.min(1.4, Math.round((_cameraZoom + 0.1) * 10) / 10);
    applyZoom();
  });

  $id('cam-zoom-out')?.addEventListener('click', () => {
    _cameraZoom = Math.max(0.7, Math.round((_cameraZoom - 0.1) * 10) / 10);
    applyZoom();
  });

  $id('cam-reset')?.addEventListener('click', () => {
    _cameraZoom = 1.0;
    applyZoom();
  });
}

// ── Master Initializer ────────────────────────────────────────────────────

export function initOffice() {
  _initCanvasEngine();
  _initCameraControls();
  _initDecorationUI();
  _initPipelineStepper();
  _loadProjectList();
  _setupHUDControls();
  _pollLiveTelemetry();
  setInterval(_pollLiveTelemetry, 4000);
}

async function _pollLiveTelemetry() {
  try {
    const res = await fetch('/api/v1/telemetry/kpis');
    if (!res.ok) return;
    const data = await res.json();
    const tokensEl = $id('kpi-tokens-val');
    if (tokensEl) tokensEl.textContent = data.total_tokens.toLocaleString();
    const costEl = $id('kpi-cost-val');
    if (costEl) costEl.textContent = `$${data.estimated_cost_usd.toFixed(2)}`;
    const healthEl = $id('kpi-health-val');
    if (healthEl) healthEl.textContent = `${data.health_score}%`;
    const tasksEl = $id('kpi-tasks-val');
    if (tasksEl) tasksEl.textContent = `${data.agents_ready}/${data.agents_total}`;
  } catch (e) {
    // Graceful fallback
  }
}

function _resetPipelineStepper() {
  PIPELINE_STEPS.forEach((step) => {
    const node = $id(`stepper-node-${step.id}`);
    const stateLabel = $id(`stepper-state-${step.id}`);
    if (node && stateLabel) {
      node.classList.remove('active', 'done');
      stateLabel.textContent = 'PENDIENTE';
    }
  });
  const activeStatus = $id('stepper-active-status');
  if (activeStatus) activeStatus.textContent = 'ESPERANDO';
}

async function _syncPipelineWithProject(statusData) {
  if (!statusData) return;
  const history = statusData.execution_history || [];
  const completedAgents = new Set(history.map((h) => h.agent_id));

  let deliverables = {};
  try {
    deliverables = await API.getProjectDeliverables(statusData.project_id);
  } catch (_) {}

  PIPELINE_STEPS.forEach((step) => {
    const node = $id(`stepper-node-${step.id}`);
    const stateLabel = $id(`stepper-state-${step.id}`);
    if (!node || !stateLabel) return;

    let isDone = completedAgents.has(step.agentId);
    if (!isDone) {
      if (step.id === 'step-ceo-charter' && (deliverables.ceo_charter || deliverables.pre_sdd_doc)) isDone = true;
      if (step.id === 'step-uiux' && deliverables.ui_ux_spec) isDone = true;
      if (step.id === 'step-uiux-qa' && deliverables.ui_ux_spec) isDone = true;
      if (step.id === 'step-mktg' && deliverables.marketing_spec) isDone = true;
      if (step.id === 'step-sales' && deliverables.sales_analytics_spec) isDone = true;
      if (step.id === 'step-signoff' && deliverables.ceo_signoff) isDone = true;
    }
    if (statusData.pasos_completados >= 15) {
      isDone = true;
    }

    node.classList.remove('active', 'done');
    if (isDone) {
      node.classList.add('done');
      stateLabel.textContent = 'COMPLETADO ✓';
    } else {
      stateLabel.textContent = 'PENDIENTE';
    }
  });

  const activeStatus = $id('stepper-active-status');
  if (activeStatus) {
    activeStatus.textContent = statusData.pasos_completados
      ? `LISTO (${statusData.pasos_completados} PASOS)`
      : 'LISTO';
  }
}

/** @type {Array<Object>} */
let _cachedProjectList = [];

function _updateProjectTrigger(pid) {
  const triggerText = $id('project-trigger-text');
  const triggerDot = $id('project-trigger-dot');
  if (!triggerText || !triggerDot) return;

  if (!pid) {
    triggerText.textContent = '— NINGUNO —';
    triggerText.className = 'truncate text-[11px] font-bold text-slate-400';
    triggerDot.className = 'w-2 h-2 rounded-full bg-slate-500 flex-shrink-0';
    return;
  }

  const proj = _cachedProjectList.find((p) => (p.project_id || p.id) === pid);
  const name = proj?.project_name || (pid === 'proj_88c9fd46' ? 'validator-hq-saas' : pid);

  triggerText.textContent = name;
  triggerText.className = 'truncate text-[11px] font-bold text-slate-100';
  triggerDot.className = 'w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)] flex-shrink-0';
}

function _renderProjectOverlayList() {
  const listContainer = $id('project-overlay-list');
  const countBadge = $id('project-overlay-count');
  if (!listContainer) return;

  if (countBadge) countBadge.textContent = String(_cachedProjectList.length);
  listContainer.innerHTML = '';

  if (_cachedProjectList.length === 0) {
    listContainer.innerHTML = '<div class="p-3 text-center text-slate-500 text-[11px]">No se encontraron proyectos activos.</div>';
    return;
  }

  _cachedProjectList.forEach((proj) => {
    const pid = proj.project_id || proj.id;
    const name = proj.project_name || (pid === 'proj_88c9fd46' ? 'validator-hq-saas' : pid);
    const status = proj.current_status || 'IDLE';
    const isActive = pid === _activeProjectId;
    const totalTokens = ((proj.total_tokens_in || 0) + (proj.total_tokens_out || 0)).toLocaleString();

    const card = document.createElement('div');
    card.className = `project-card p-2.5 rounded border cursor-pointer transition-all flex flex-col gap-1 ${
      isActive
        ? 'active border-cyan-400 bg-[#09283e]'
        : 'border-[#1e293b] bg-[#0c1425] hover:bg-[#121f3a]'
    }`;
    card.style.backgroundColor = isActive ? '#09283e' : '#0c1425';
    card.style.border = isActive ? '1px solid #06b6d4' : '1px solid #1e293b';

    card.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-1.5 min-w-0 max-w-[240px]">
          <span class="text-xs flex-shrink-0">${pid.startsWith('bf_') ? '🛡️' : '🚀'}</span>
          <span class="font-bold text-slate-100 text-xs truncate" title="${_esc(name)}">${_esc(name)}</span>
        </div>
        ${
          isActive
            ? '<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-700 flex-shrink-0">ACTIVO ✓</span>'
            : '<span class="text-[9px] text-slate-400 hover:text-cyan-300 flex-shrink-0 font-sans">Seleccionar</span>'
        }
      </div>
      <div class="flex items-center justify-between text-[10px] font-mono">
        <span class="text-cyan-400 font-semibold">${_esc(pid)}</span>
        <span class="text-amber-300 font-medium">${_esc(status)}</span>
      </div>
      <div class="flex items-center justify-between text-[9px] text-slate-400 pt-1 border-t border-[#1e293b]">
        <span>Pasos: ${proj.steps_completed ?? 0}</span>
        <span>${totalTokens} tokens</span>
      </div>
    `;

    card.addEventListener('click', () => {
      _selectProject(pid);
      $id('project-dropdown-overlay')?.classList.add('hidden');
    });

    listContainer.appendChild(card);
  });
}

async function _selectProject(pid) {
  _activeProjectId = pid || null;
  window._activeProjectId = _activeProjectId;
  document.dispatchEvent(new CustomEvent('project:selected', { detail: { projectId: _activeProjectId } }));

  _updateProjectTrigger(_activeProjectId);
  _renderProjectOverlayList();

  const nativeSelect = /** @type {HTMLSelectElement|null} */ ($id('project-select'));
  if (nativeSelect) nativeSelect.value = _activeProjectId || '';

  if (!_activeProjectId) {
    _resetPipelineStepper();
    appendActivityLog({ level: 'info', source: 'PROJECT', message: 'Ningún proyecto seleccionado.' });
    return;
  }

  appendActivityLog({ level: 'info', source: 'PROJECT', message: `Proyecto activo: ${_activeProjectId}` });

  try {
    const statusData = await API.getProjectStatus(_activeProjectId);
    await _syncPipelineWithProject(statusData);
  } catch (err) {
    console.warn('Error loading project status for pipeline:', err);
  }

  ['dash-interaction-project-select', 'thoughts-project-select', 'artifacts-project-select'].forEach((id) => {
    const el = /** @type {HTMLSelectElement|null} */ ($id(id));
    if (el && el.value !== _activeProjectId) {
      if (Array.from(el.options).some((o) => o.value === _activeProjectId)) {
        el.value = _activeProjectId;
        el.dispatchEvent(new Event('change'));
      }
    }
  });
}

async function _loadProjectList() {
  const select = /** @type {HTMLSelectElement|null} */ ($id('project-select'));

  try {
    const res = await API.listProjects();
    _cachedProjectList = Array.isArray(res) ? res : (res?.projects || []);
    const prevVal = _activeProjectId || select?.value;

    if (select) {
      select.innerHTML = '<option value="">— NINGUNO —</option>';
      _cachedProjectList.forEach((proj) => {
        const pid = proj.project_id || proj.id;
        if (!pid) return;
        const opt = document.createElement('option');
        opt.value = pid;
        const name = proj.project_name || (pid === 'proj_88c9fd46' ? 'validator-hq-saas' : null);
        const label = name ? `${name} (${pid})` : pid;
        const status = proj.current_status ? ` • ${proj.current_status}` : '';
        opt.textContent = `${label}${status}`;
        select.appendChild(opt);
      });
    }

    _renderProjectOverlayList();

    if (prevVal && _cachedProjectList.some((p) => (p.project_id || p.id) === prevVal)) {
      _selectProject(prevVal);
    } else if (_cachedProjectList.length > 0) {
      const defaultPid = _cachedProjectList[0].project_id || _cachedProjectList[0].id;
      _selectProject(defaultPid);
    } else {
      _selectProject(null);
    }
  } catch (e) {
    console.warn('Error loading projects:', e);
  }
}

function _setupHUDControls() {
  document.querySelectorAll('.mode-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.mode-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      const mode = /** @type {HTMLElement} */ (btn).dataset.mode;
      const gf = $id('greenfield-controls');
      const bf = $id('brownfield-controls');
      if (mode === 'brownfield') {
        gf?.classList.remove('active');
        bf?.classList.add('active');
      } else {
        bf?.classList.remove('active');
        gf?.classList.add('active');
      }
    });
  });

  // Project Dropdown Trigger & Overlay Event Listeners
  const triggerBtn = $id('project-dropdown-trigger');
  const dropdownOverlay = $id('project-dropdown-overlay');

  triggerBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdownOverlay?.classList.toggle('hidden');
    const isExpanded = !dropdownOverlay?.classList.contains('hidden');
    triggerBtn.setAttribute('aria-expanded', String(isExpanded));
  });

  $id('btn-project-deselect')?.addEventListener('click', () => {
    _selectProject(null);
    dropdownOverlay?.classList.add('hidden');
    triggerBtn?.setAttribute('aria-expanded', 'false');
  });

  document.addEventListener('click', (e) => {
    const container = $id('project-dropdown-container');
    if (container && !container.contains(/** @type {Node} */ (e.target))) {
      dropdownOverlay?.classList.add('hidden');
      triggerBtn?.setAttribute('aria-expanded', 'false');
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && dropdownOverlay && !dropdownOverlay.classList.contains('hidden')) {
      dropdownOverlay.classList.add('hidden');
      triggerBtn?.setAttribute('aria-expanded', 'false');
    }
  });

  if (window.location.search.includes('show_dropdown=1')) {
    setTimeout(() => {
      dropdownOverlay?.classList.remove('hidden');
      triggerBtn?.setAttribute('aria-expanded', 'true');
    }, 400);
  }

  $id('project-select')?.addEventListener('change', (e) => {
    const val = /** @type {HTMLSelectElement} */ (e.target).value;
    _selectProject(val);
  });

  $id('btn-refresh-projects')?.addEventListener('click', _loadProjectList);

  $id('btn-resume')?.addEventListener('click', async () => {
    if (!_activeProjectId) {
      appendActivityLog({ level: 'warn', source: 'RESUME', message: 'Selecciona un proyecto primero para reanudar.' });
      return;
    }
    const btn = /** @type {HTMLButtonElement|null} */ ($id('btn-resume'));
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⏳ REANUDANDO...';
    }
    appendActivityLog({ level: 'info', source: 'RESUME', message: `Reanudando proyecto ${_activeProjectId}...` });
    try {
      const res = await API.resumeProject(_activeProjectId);
      appendActivityLog({ level: 'success', source: 'RESUME', message: `Proyecto ${_activeProjectId} reanudado: ${res.status || 'OK'}` });
      await _selectProject(_activeProjectId);
    } catch (err) {
      appendActivityLog({ level: 'error', source: 'RESUME', message: `Error al reanudar proyecto: ${err.message}` });
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '⏭ REANUDAR';
      }
    }
  });

  $id('btn-launch')?.addEventListener('click', async () => {
    const input = /** @type {HTMLInputElement|null} */ ($id('idea-input'));
    if (!input || !input.value.trim()) return;
    const idea = input.value.trim();
    appendActivityLog({ level: 'info', source: 'LAUNCH', message: `Lanzando proyecto con idea: "${idea.slice(0, 40)}..."` });
    try {
      const res = await API.createProject(idea);
      if (res && res.project_id) {
        _activeProjectId = res.project_id;
        await _loadProjectList();
        const sel = /** @type {HTMLSelectElement|null} */ ($id('project-select'));
        if (sel) sel.value = res.project_id;
        appendActivityLog({ level: 'success', source: 'PIPELINE', message: `Proyecto creado con éxito: ${res.project_id}` });
      }
    } catch (err) {
      appendActivityLog({ level: 'error', source: 'LAUNCH', message: `Error al crear proyecto: ${err.message}` });
    }
  });

  $id('btn-audit')?.addEventListener('click', async () => {
    const repoInput = /** @type {HTMLInputElement|null} */ ($id('repo-url-input'));
    const depthSelect = /** @type {HTMLSelectElement|null} */ ($id('audit-depth'));
    const auditBtn = /** @type {HTMLButtonElement|null} */ ($id('btn-audit'));

    if (!repoInput || !repoInput.value.trim()) {
      appendActivityLog({ level: 'warn', source: 'BROWNFIELD', message: 'Por favor, introduce una URL de repositorio GitHub válida.' });
      return;
    }

    const repoUrl = repoInput.value.trim();
    const depth = depthSelect ? depthSelect.value : 'deep';
    const depthLabel = depth === 'surface' ? '⚡ RÁPIDO' : '🔬 PROFUNDO';

    appendActivityLog({
      level: 'info',
      source: 'BROWNFIELD',
      message: `Iniciando auditoría ${depthLabel} en: ${repoUrl}`
    });

    if (auditBtn) {
      auditBtn.disabled = true;
      auditBtn.textContent = '⏳ AUDITANDO...';
    }

    try {
      const res = await API.startBrownfieldAudit(repoUrl, 'main', depth);
      if (res && res.project_id) {
        _activeProjectId = res.project_id;
        await _loadProjectList();
        const sel = /** @type {HTMLSelectElement|null} */ ($id('project-select'));
        if (sel) sel.value = res.project_id;

        const health = res.health_score ?? 'N/A';
        const critCount = res.critical_findings ? res.critical_findings.length : 0;
        const warnCount = res.warnings ? res.warnings.length : 0;
        appendActivityLog({
          level: 'success',
          source: 'BROWNFIELD',
          message: `Auditoría completada (${depthLabel}). ID: ${res.project_id} | Salud: ${health}/100 | Críticos: ${critCount} | Advertencias: ${warnCount}`
        });
      } else {
        appendActivityLog({ level: 'success', source: 'BROWNFIELD', message: 'Auditoría completada exitosamente.' });
      }
    } catch (err) {
      appendActivityLog({ level: 'error', source: 'BROWNFIELD', message: `Error en auditoría GitHub: ${err.message}` });
    } finally {
      if (auditBtn) {
        auditBtn.disabled = false;
        auditBtn.textContent = '🔍 AUDITAR';
      }
    }
  });
}
