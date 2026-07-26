import test from 'node:test';
import assert from 'node:assert/strict';
import {createVoiceServer} from '../src/voice-server.mjs';

test('voice server exposes the Kokoro browser bundle and WASM runtime', async () => {
  const server = await createVoiceServer({port: 0});
  try {
    const address = server.address();
    const origin = `http://127.0.0.1:${address.port}`;
    const bundle = await fetch(`${origin}/vendor/kokoro.web.js`);
    const runtime = await fetch(
      `${origin}/ort/ort-wasm-simd-threaded.wasm`,
    );
    const favicon = await fetch(`${origin}/favicon.ico`);
    assert.equal(bundle.status, 200);
    assert.match(bundle.headers.get('content-type'), /javascript/);
    assert.equal(runtime.status, 200);
    assert.match(runtime.headers.get('content-type'), /application\/wasm/);
    assert.equal(favicon.status, 204);
  } finally {
    server.close();
  }
});
