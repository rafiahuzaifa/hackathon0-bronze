// PM2 Ecosystem Configuration for AI Employee Orchestrator
// Usage:
//   pm2 start ecosystem.config.js
//   pm2 logs orchestrator
//   pm2 stop orchestrator
//   pm2 restart orchestrator

module.exports = {
  apps: [
    {
      name: "orchestrator",
      script: "orchestrator.py",
      interpreter: "python",
      args: "--interval 60",
      cwd: "d:/hackathon0/hackathon/AI_Employee_Vault",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1",
        // Set your Anthropic API key here for Claude integration:
        // ANTHROPIC_API_KEY: "sk-ant-...",
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "d:/hackathon0/hackathon/AI_Employee_Vault/pm2-error.log",
      out_file: "d:/hackathon0/hackathon/AI_Employee_Vault/pm2-out.log",
      merge_logs: true,
    },
    {
      name: "orchestrator-simulate",
      script: "orchestrator.py",
      interpreter: "python",
      args: "--simulate --interval 60",
      cwd: "d:/hackathon0/hackathon/AI_Employee_Vault",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1",
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "d:/hackathon0/hackathon/AI_Employee_Vault/pm2-sim-error.log",
      out_file: "d:/hackathon0/hackathon/AI_Employee_Vault/pm2-sim-out.log",
      merge_logs: true,
    },
  ],
};
