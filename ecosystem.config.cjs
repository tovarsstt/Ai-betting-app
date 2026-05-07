module.exports = {
    apps: [
        {
            name: "god-engine-math",
            script: "scripts/math_engine.py",
            interpreter: "/usr/local/bin/python3.12",
            env: {
                PORT: 8001,
                PYTHONUNBUFFERED: "1"
            }
        },
        {
            name: "god-engine-osint",
            script: "scripts/v13_sentinel.py",
            interpreter: "/usr/local/bin/python3.12",
            env: {
                PYTHONUNBUFFERED: "1"
            }
        },
        {
            name: "god-engine-bridge",
            script: "server.ts",
            interpreter: "node",
            node_args: "--import tsx",
            env: {
                NODE_ENV: "production",
                PORT: 3001
            }
        }
    ]
};
