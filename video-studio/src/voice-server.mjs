import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';

const contentTypes = new Map([
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.mjs', 'text/javascript; charset=utf-8'],
  ['.wasm', 'application/wasm'],
]);

export const createVoiceServer = async ({port = 41903} = {}) => {
  const root = process.cwd();
  const routes = new Map([
    [
      '/vendor/kokoro.web.js',
      path.join(root, 'node_modules', 'kokoro-js', 'dist', 'kokoro.web.js'),
    ],
  ]);

  const server = createServer(async (request, response) => {
    try {
      const pathname = new URL(request.url, 'http://localhost').pathname;
      if (pathname === '/favicon.ico') {
        response.writeHead(204);
        response.end();
        return;
      }
      let filePath = routes.get(pathname);
      if (pathname.startsWith('/ort/')) {
        filePath = path.join(
          root,
          'node_modules',
          'onnxruntime-web',
          'dist',
          path.basename(pathname),
        );
      }
      if (pathname === '/voice.html') {
        filePath = path.join(root, 'public', 'voice.html');
      }
      if (!filePath) {
        response.writeHead(404);
        response.end('Not found');
        return;
      }
      const body = await readFile(filePath);
      response.writeHead(200, {
        'Content-Type':
          contentTypes.get(path.extname(filePath)) ??
          'application/octet-stream',
        'Cross-Origin-Opener-Policy': 'same-origin',
        'Cross-Origin-Embedder-Policy': 'require-corp',
      });
      response.end(body);
    } catch (error) {
      response.writeHead(500);
      response.end(error.message);
    }
  });

  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', resolve);
  });
  return server;
};
