import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DIST_PATH = path.join(__dirname, 'dist');

const API_TARGET = { host: '127.0.0.1', port: 3001 };

const server = http.createServer((req, res) => {
    // /api/* -> bridge on :3001. Without this, API calls fall through to the
    // SPA fallback and return index.html — Safari then throws "The string did
    // not match the expected pattern" when the app tries res.json() on HTML.
    if (req.url.startsWith('/api/')) {
        const proxied = http.request(
            { ...API_TARGET, path: req.url, method: req.method, headers: { ...req.headers, host: `${API_TARGET.host}:${API_TARGET.port}` } },
            (upstream) => {
                res.writeHead(upstream.statusCode || 502, upstream.headers);
                upstream.pipe(res);
            },
        );
        proxied.setTimeout(600000, () => proxied.destroy(new Error('upstream timeout')));
        proxied.on('error', () => {
            res.writeHead(502, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'API_UNAVAILABLE', message: 'bridge on :3001 not reachable' }));
        });
        req.pipe(proxied);
        return;
    }
    let filePath = path.join(DIST_PATH, req.url === '/' ? 'index.html' : req.url);
    
    // Basic Security: Ensure the file is within the DIST_PATH
    if (!filePath.startsWith(DIST_PATH)) {
        res.statusCode = 403;
        res.end('Forbidden');
        return;
    }

    fs.readFile(filePath, (err, data) => {
        if (err) {
            // Fallback to index.html for SPA routing
            fs.readFile(path.join(DIST_PATH, 'index.html'), (err2, data2) => {
                if (err2) {
                    res.statusCode = 404;
                    res.end('Not Found');
                } else {
                    res.writeHead(200, { 'Content-Type': 'text/html' });
                    res.end(data2);
                }
            });
        } else {
            const ext = path.extname(filePath);
            const contentTypes = {
                '.html': 'text/html',
                '.js': 'text/javascript',
                '.css': 'text/css',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.svg': 'image/svg+xml'
            };
            res.writeHead(200, { 'Content-Type': contentTypes[ext] || 'application/octet-stream' });
            res.end(data);
        }
    });
});

server.listen(5173, '0.0.0.0', () => {
    console.log('✅ Zero-Dep Production Server active at http://localhost:5173');
});
