module.exports = {
  apps: [
    {
      name:        'vault-api',
      script:      './server/server.js',
      cwd:         __dirname,
      watch:       false,
      env: {
        NODE_ENV:    'production',
        PORT:        '3001',
        HOST:        '127.0.0.1',
        VAULT_DIR:   'd:/hackathon0/hackathon/AI_Employee_Vault',
        UI_PASSWORD: 'change-me',
        JWT_SECRET:  'change-me-jwt-secret',
      },
    },
  ],
};
