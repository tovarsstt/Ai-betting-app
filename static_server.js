import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DIST_PATH = path.join(__dirname, 'dist');

const server = http.createServer((req, res) => {
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
