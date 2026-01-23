# Production Deployment for Barsukas

## Server Info

- User: greenland
- Port: 5555
- Repo: /home/greenland/ROOT
- Venv: /home/greenland/ROOT/venv
- Database: Supabase (PostgreSQL)

## Initial Setup

1. Copy the systemd service file:
   ```bash
   sudo cp /home/greenland/ROOT/prod/barsukas.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable barsukas.service
   ```

2. Start the service:
   ```bash
   sudo systemctl start barsukas.service
   ```

## Deployment

To deploy updates (as greenland user):
```bash
/home/greenland/ROOT/prod/deploy.sh
```

This will:
- Pull latest code from git
- Install/update Python dependencies
- Restart the service

## Managing the Service

```bash
# Check status
systemctl status barsukas.service

# View logs (follow)
journalctl -u barsukas.service -f

# View recent logs
journalctl -u barsukas.service -n 50

# Restart
sudo systemctl restart barsukas.service

# Stop
sudo systemctl stop barsukas.service
```

## Configuration

The service runs with `--persona=prod` which:
- Uses PostgreSQL backend (Supabase)
- Listens on port 5555
- Binds to all interfaces (0.0.0.0)

## Centralized Config

See also: ~/repo/prodconfig/ for shared deployment scripts and service files for all services on this server.
