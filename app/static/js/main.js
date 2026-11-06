/**
 * main.js — AgentOffice 2.0 Entry Point
 * Bootstraps the office map and side panel modules.
 * ES modules are automatically deferred — DOM is ready when this runs.
 * @module main
 */

import { initOffice } from './office.js';
import { initPanel  } from './panel.js';

initOffice();
initPanel();
