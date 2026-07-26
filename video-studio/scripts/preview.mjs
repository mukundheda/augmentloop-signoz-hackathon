import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const html = await readFile(path.join(root, 'public', 'frame.html'));
const cues = await readFile(path.join(root, 'timeline', 'cues.json'));
createServer((request, response) => {
  if (request.url?.startsWith('/timeline/cues.json')) {
    response.writeHead(200, {'Content-Type': 'application/json'});
    response.end(cues);
    return;
  }
  response.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'});
  response.end(html);
}).listen(41893, '127.0.0.1', () => {
  console.log('Video preview: http://127.0.0.1:41893/?frame=90&fps=30');
});
