// Loaded into HyperFrames' Node by render.py (NODE_OPTIONS=--import), nowhere else.
//
// A png-sequence render makes HyperFrames capture every frame with Chrome's slow PNG encoder (optimizeForSpeed:
// false). The fast one writes the same pixels with less compression: measured on 30 frames of a reel (1 browser,
// GTX 1650 laptop) 1246 -> 816 ms a frame, every frame bit-identical in RGB and alpha, files ~20% bigger.
// HyperFrames 0.8.34 internals: puppeteer-core's Connection._rawSend carries every protocol message. If that ever
// moves, nothing breaks: the render just runs at the old speed (the message below says so).
import { createRequire } from 'node:module';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const entry = process.argv[1] || '';
if (/[\\/]hyperframes([\\/]|\.mjs$|$)/.test(entry)) {
  try {
    const req = createRequire(entry);
    const file = path.join(path.dirname(req.resolve('puppeteer-core')), 'cdp', 'Connection.js');
    const { Connection } = await import(pathToFileURL(file).href);
    const send = Connection.prototype._rawSend;
    if (typeof send !== 'function') throw new Error('no Connection._rawSend');
    Connection.prototype._rawSend = function (callbacks, method, params, sessionId, options) {
      if (method === 'Page.captureScreenshot' && params && params.format === 'png' && !params.optimizeForSpeed) {
        params = { ...params, optimizeForSpeed: true };
      }
      return send.call(this, callbacks, method, params, sessionId, options);
    };
    console.error('[fastpng] fast lossless PNG capture on');
  } catch (e) {
    console.error(`[fastpng] not applied (${e && e.message}): normal PNG capture`);
  }
}
