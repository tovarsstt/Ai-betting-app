module.exports = {
    apps: [
        {
            name: "god-engine-math",
            script: "v11_quant_engine.py",
            interpreter: "python3",
            env: {
                PORT: 8001
            }
        },
        {
            name: "god-engine-osint",
            script: "scripts/sentiment_scraper.py",
            interpreter: "python3",
            env: {
                PORT: 8002
            }
        },
        {
            name: "god-engine-vanguard",
            script: "scripts/sentiment_vanguard.py",
            interpreter: "python3",
            env: {
                PORT: 8003
            }
        },
        {
            name: "god-engine-bridge",
            script: "server.js",
            node_args: "--import tsx",
            env: {
                NODE_ENV: "production",
                PORT: 3001
            }
        },
        {
            name: "god-engine-panic",
            script: "scripts/panic_switch.py",
            interpreter: "python3",
            env: {
                PYTHONUNBUFFERED: "1"
            }
        }
    ]
};
