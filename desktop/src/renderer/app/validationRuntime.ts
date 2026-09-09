import {z} from 'zod';

// Run before domain schemas load. Renderer CSP forbids generated code; Zod's
// interpreter keeps validation intact without even attempting the eval probe.
z.config({jitless: true});
